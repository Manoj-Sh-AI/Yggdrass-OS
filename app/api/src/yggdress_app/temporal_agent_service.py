"""Temporal-backed local execution service and repeat-safe application outbox."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import AsyncExitStack
from datetime import timedelta
from threading import Event, Thread

from fastapi import HTTPException
from temporalio.client import Client, WorkflowExecutionStatus
from temporalio.common import WorkflowIDReusePolicy
from temporalio.exceptions import WorkflowAlreadyStartedError
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from .agent_execution_store import ExecutionStore
from .agent_models import AgentError
from .receivers import payload_fingerprint
from .temporal_agent_activities import AgentActivities
from .temporal_agent_workflow import AgentExecution


class TemporalAgentService:
    def __init__(
        self,
        runner,
        address="127.0.0.1:7233",
        namespace="default",
        queue="yggdras-agents-v1",
        local=None,
        calls=None,
    ):
        self.runner, self.address, self.namespace, self.queue = runner, address, namespace, queue
        self.store = ExecutionStore(runner.store)
        self.activities = AgentActivities(runner)
        self.loop = self.wake = self.closing = self.client = None
        self.ready, self.stopped = Event(), Event()
        self.available = False
        self.issue = "Execution service is connecting. Saved requests remain queued."
        self.thread = None
        self.local = local
        self.calls = calls
        self.failure_stage = ""
        self.failure_type = ""

    def status(self):
        return {
            "provider": "temporal",
            "ready": self.available,
            "connection_issue": self.issue,
            "failure_stage": self.failure_stage,
            "failure_type": self.failure_type,
        }

    def notify(self):
        if self.loop and not self.loop.is_closed() and self.wake:
            try:
                self.loop.call_soon_threadsafe(self.wake.set)
            except RuntimeError:
                pass  # Core CRUD must survive a concurrently stopping executor.

    def start(self):
        self.thread = Thread(target=self._thread, daemon=True, name="yggdras-temporal")
        self.thread.start()
        self.ready.wait(30)

    def stop(self):
        self.stopped.set()
        if self.loop and not self.loop.is_closed() and self.closing:
            self.loop.call_soon_threadsafe(self.closing.set)
        if self.thread:
            self.thread.join(timeout=12)

    def _thread(self):
        asyncio.run(self.run())

    async def run(self, client=None):
        server = None
        try:
            if client is None and self.local:
                self.failure_stage = "binary_verification"
                import hashlib
                from pathlib import Path

                binary = Path(self.local["binary"]).resolve(strict=True)
                if hashlib.sha256(binary.read_bytes()).hexdigest() != self.local["sha256"]:
                    raise RuntimeError("The local execution binary failed verification.")
                database = Path(self.local["database"])
                database.parent.mkdir(parents=True, exist_ok=True)
                self.failure_stage = "local_server_startup"
                server = await WorkflowEnvironment.start_local(
                    dev_server_existing_path=str(binary),
                    dev_server_database_filename=str(database),
                    namespace=self.namespace,
                    ip="127.0.0.1",
                    port=self.local.get("port"),
                    ui=False,
                    dev_server_log_level="error",
                )
                client = server.client
            self.failure_stage = "worker_connection"
            await self.run_connected(client)
        except Exception as error:
            self.failure_type = type(error).__name__
            self.available = False
            self.issue = "Execution service unavailable. Saved requests remain queued."
            self.ready.set()
            if client is not None:
                raise
        finally:
            if server:
                await server.shutdown()

    async def run_connected(self, client=None):
        self.loop = asyncio.get_running_loop()
        self.wake, self.closing = asyncio.Event(), asyncio.Event()
        while not self.stopped.is_set():
            try:
                selected = client or await Client.connect(self.address, namespace=self.namespace)
                await self.serve(selected)
                return
            except Exception as error:
                self.failure_type = type(error).__name__
                # Never serialize transport exceptions containing private configuration.
                self.available = False
                self.issue = "Execution service unavailable. Saved requests remain queued."
                self.ready.set()
                if client:
                    raise
                try:
                    await asyncio.wait_for(self.closing.wait(), timeout=3)
                    return
                except TimeoutError:
                    pass

    async def serve(self, client):
        self.client = client
        methods = [
            self.activities.prepare,
            self.activities.effect,
            self.activities.finish,
            self.activities.review,
        ]
        with ThreadPoolExecutor(max_workers=8, thread_name_prefix="yggdras-activity") as executor:
            workers = [
                Worker(
                    client,
                    task_queue=self.queue + "-" + lane,
                    workflows=[AgentExecution],
                    activities=methods,
                    activity_executor=executor,
                    max_concurrent_activities=4 if lane == "chat" else 2,
                    graceful_shutdown_timeout=timedelta(seconds=5),
                    sticky_queue_schedule_to_start_timeout=timedelta(seconds=2),
                )
                for lane in ("chat", "background")
            ]
            async with AsyncExitStack() as stack:
                await stack.enter_async_context(workers[0])
                await stack.enter_async_context(workers[1])
                if self.calls and self.calls.mode != "disabled":
                    from .temporal_calls import CallActivities, CallCheckIns

                    await stack.enter_async_context(
                        Worker(
                            client,
                            task_queue=self.queue + "-calls",
                            workflows=[CallCheckIns],
                            activities=[CallActivities(self.calls).sweep],
                            activity_executor=executor,
                            graceful_shutdown_timeout=timedelta(seconds=5),
                        )
                    )
                    try:
                        await client.start_workflow(
                            CallCheckIns.run,
                            id="yggdras-call-checkins-v1",
                            task_queue=self.queue + "-calls",
                        )
                    except WorkflowAlreadyStartedError:
                        pass
                self.available, self.issue = True, ""
                self.failure_stage = self.failure_type = ""
                self.ready.set()
                self.wake.set()
                task = asyncio.create_task(self.dispatch_loop())
                try:
                    await self.closing.wait()
                finally:
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
                    self.available = False

    async def dispatch_loop(self):
        while not self.closing.is_set():
            notified = self.wake.is_set()
            self.wake.clear()
            try:
                await asyncio.to_thread(self.runner.store.recover_writes, self.runner.notes)
                try:
                    await asyncio.to_thread(self.runner.deliver)
                except AgentError:
                    pass  # One unavailable response must not block other queued jobs.
                self.issue = ""
                if notified and self.calls and self.calls.mode != "disabled":
                    await self.client.get_workflow_handle("yggdras-call-checkins-v1").signal("wake")
                await self.dispatch(notified)
            except Exception:  # noqa: BLE001 -- never expose private transport details
                self.issue = "Some queued work is waiting for its execution connection. It will be reconciled."
            try:
                await asyncio.wait_for(self.wake.wait(), timeout=2)
            except TimeoutError:
                pass

    async def dispatch(self, notified=True):
        rows = await asyncio.to_thread(
            self.store.reconcile, self.runner.default_model, self.runner.activated_at
        )
        for row in rows:
            try:
                await self.dispatch_one(row, notified)
            except Exception:  # noqa: BLE001 -- isolate a stale execution from the rest of the queue
                self.issue = (
                    "An execution is waiting for its connection; other requests can continue."
                )

    async def dispatch_one(self, row, notified=True):
        handle = self.client.get_workflow_handle(row["workflow_id"])
        if row["state"] == "pending":
            try:
                handle = await self.client.start_workflow(
                    AgentExecution.run,
                    str(row["run_id"]),
                    id=row["workflow_id"],
                    task_queue=self.queue + ("-chat" if row["chat_request_id"] else "-background"),
                    id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE,
                )
            except WorkflowAlreadyStartedError:
                pass
        description = await handle.describe()
        if description.status != WorkflowExecutionStatus.RUNNING:
            if description.status == WorkflowExecutionStatus.COMPLETED:
                run = await asyncio.to_thread(self.store.run, row["run_id"])
                if run["state"] in ("completed", "failed", "cancelled"):
                    await asyncio.to_thread(self.store.state, row["run_id"], run["state"])
                    return
            # An interrupted/terminated workflow is never silently restarted.
            await asyncio.to_thread(
                self.activities.finish,
                {
                    "run_id": str(row["run_id"]),
                    "error": "Execution was interrupted. Completed steps are recorded; resend explicitly to retry.",
                },
            )
            await asyncio.to_thread(self.store.fail_closed, row["run_id"])
            return
        if row["cancellation_requested"]:
            await handle.signal(AgentExecution.cancel)
        elif row["state"] == "waiting" and notified:
            await handle.signal(AgentExecution.reconcile)

    async def on_loop(self, operation):
        if not self.available or not self.client or not self.loop:
            raise HTTPException(503, "Execution service unavailable. Your saved work is retained.")

        async def invoke():
            return await operation()

        if asyncio.get_running_loop() is self.loop:
            return await invoke()
        future = asyncio.run_coroutine_threadsafe(invoke(), self.loop)
        return await asyncio.wrap_future(future)

    async def resolve(self, command):
        with self.store.database.connect() as db:
            row = db.execute(
                "SELECT e.workflow_id,e.state,p.state AS proposal_state FROM app.agent_proposals p JOIN app.agent_executions e ON e.run_id=p.run_id WHERE p.id=%s",
                (command.id,),
            ).fetchone()
        if not row:
            return self.runner.store.resolve(command)  # Existing pre-Temporal reviews.
        if row["proposal_state"] != "pending" or row["state"] not in ("running", "waiting"):
            return self.runner.store.resolve(command)  # Read/reject the existing exact receipt.
        try:
            result = await self.on_loop(
                lambda: self.client.get_workflow_handle(row["workflow_id"]).execute_update(
                    AgentExecution.resolve,
                    command.model_dump(mode="json"),
                    id=str(command.key) + ":" + payload_fingerprint(command),
                    rpc_timeout=timedelta(seconds=20),
                )
            )
        except HTTPException:
            raise
        except Exception:  # noqa: BLE001 -- sanitize errors before returning to the owner API
            raise HTTPException(
                503,
                "The decision response was interrupted. Refresh or retry the same decision; it cannot apply twice.",
            ) from None
        if not result["ok"]:
            raise HTTPException(result.get("status", 409), result["error"])
        return result["value"]

    async def query(self, identifier):
        trace = self.store.trace(identifier)
        try:
            live = await self.on_loop(
                lambda: self.client.get_workflow_handle(trace["workflow_id"]).query(
                    AgentExecution.status, rpc_timeout=timedelta(seconds=3)
                )
            )
        except Exception:  # noqa: BLE001 -- the durable trace remains available offline
            live = None
        return {**trace, "live": live}
