"""Real Temporal + disposable PostgreSQL. No provider calls or production data."""

import asyncio
import hashlib
import os
from pathlib import Path
from uuid import uuid4

import pytest
from temporalio.client import Client
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Replayer
from test_agent_specialists import proposal, text, tool
from test_application_agents import fixture, send
from test_chat import command as chat_command

from yggdress_app.agent_execution_store import ExecutionStore
from yggdress_app.temporal_agent_service import TemporalAgentService
from yggdress_app.temporal_agent_workflow import AgentExecution


async def wait_for(check, seconds=40):
    until = asyncio.get_running_loop().time() + seconds
    while asyncio.get_running_loop().time() < until:
        value = check()
        if value:
            return value
        await asyncio.sleep(0.03)
    raise AssertionError("The synthetic execution did not reach its expected state.")


async def environment():
    folder = Path(__file__).resolve().parents[1] / "runtime/temporal-tools"
    binary = folder / ("temporal.exe" if os.name == "nt" else "temporal")
    return await WorkflowEnvironment.start_local(
        dev_server_existing_path=str(binary) if binary.is_file() else None,
        dev_server_log_level="error",
    )


async def start(app, runner, env):
    service = TemporalAgentService(runner, env.client.service_client.config.target_host)
    app.state.agent_runtime = service
    task = asyncio.create_task(service.run(env.client))
    await wait_for(lambda: service.available)
    return service, task


async def stop(service, task):
    service.stopped.set()
    service.closing.set()
    await asyncio.wait_for(task, timeout=20)


def test_real_workflow_review_restart_duplicate_dispatch_and_replay(signed_in):
    client, app, runner, model, _ = fixture(
        signed_in, tool("propose_change", proposal()), text("Your proposal is ready.")
    )

    async def scenario():
        async with await environment() as env:
            service, task = await start(app, runner, env)
            try:
                sent = await asyncio.to_thread(send, client)

                def waiting():
                    with service.store.database.connect() as db:
                        return db.execute(
                            "SELECT * FROM app.agent_executions WHERE state='waiting'"
                        ).fetchone()

                row = await wait_for(waiting)
                assert len(model.calls) == 2
                assert len(runner.store.tools.read("tasks", {})["task"]["items"]) == 0
                await service.dispatch()
                await service.dispatch()
                assert len(model.calls) == 2
                trace = await asyncio.to_thread(
                    client.get, "/v1/application/agents/executions/" + str(row["run_id"])
                )
                assert trace.status_code == 200
                assert [s["kind"] for s in trace.json()["steps"]] == ["model", "inspect", "model"]
                assert all(
                    "result" not in s and "fingerprint" not in s for s in trace.json()["steps"]
                )
                await stop(service, task)
                # New client/service and worker; the waiting workflow lives on the server.
                fresh_client = await Client.connect(env.client.service_client.config.target_host)
                service = TemporalAgentService(
                    runner, fresh_client.service_client.config.target_host
                )
                app.state.agent_runtime = service
                task = asyncio.create_task(service.run(fresh_client))
                await wait_for(lambda: service.available)
                review = client.get("/v1/application/agents/reviews").json()["reviews"][0]
                decision = {
                    "key": str(uuid4()),
                    "id": review["id"],
                    "version": review["version"],
                    "decision": "accept",
                }
                accepted = await asyncio.to_thread(
                    client.post, "/v1/application/agents/reviews/resolve", json=decision
                )
                assert accepted.status_code == 200, accepted.text
                again = await asyncio.to_thread(
                    client.post, "/v1/application/agents/reviews/resolve", json=decision
                )
                assert again.json() == accepted.json()
                conflicting = await asyncio.to_thread(
                    client.post,
                    "/v1/application/agents/reviews/resolve",
                    json={**decision, "decision": "dismiss"},
                )
                assert conflicting.status_code == 409
                assert len(runner.store.tools.read("tasks", {})["task"]["items"]) == 1
                assert len(model.calls) == 2
                handle = env.client.get_workflow_handle(row["workflow_id"])
                assert await asyncio.wait_for(handle.result(), timeout=30) == {"state": "completed"}
                await Replayer(workflows=[AgentExecution]).replay_workflow(
                    await handle.fetch_history()
                )
                history = client.get("/v1/chat/conversations/" + sent["conversation"]["id"]).json()
                assert history["requests"][0]["state"] == "completed"
            finally:
                await stop(service, task)

    asyncio.run(scenario())


def test_held_messages_and_cancelled_source_do_not_run_paid_calls(signed_in):
    client, app, runner, model, _ = fixture(signed_in)
    held = send(client, deliver=False)
    sent = send(client)
    command = {
        "key": str(uuid4()),
        "operation": "request.cancel",
        "id": sent["request"]["id"],
        "version": sent["request"]["version"],
        "data": {},
    }
    assert client.post("/v1/chat/commands", json=command).status_code == 200

    async def scenario():
        async with await environment() as env:
            service, task = await start(app, runner, env)
            try:
                await service.dispatch()
                assert client.get("/v1/application/agents/executions").json()["executions"] == []
                history = client.get("/v1/chat/conversations/" + held["conversation"]["id"]).json()
                assert history["requests"][0]["state"] == "held"
                assert model.calls == []
            finally:
                await stop(service, task)

    asyncio.run(scenario())


def test_execution_cancel_supersedes_waiting_proposals(signed_in):
    client, app, runner, model, _ = fixture(
        signed_in, tool("propose_change", proposal()), text("Ready.")
    )

    async def scenario():
        async with await environment() as env:
            service, task = await start(app, runner, env)
            try:
                await asyncio.to_thread(send, client)

                def waiting():
                    with service.store.database.connect() as db:
                        return db.execute(
                            "SELECT * FROM app.agent_executions WHERE state='waiting'"
                        ).fetchone()

                row = await wait_for(waiting)
                path = "/v1/application/agents/executions/" + str(row["run_id"]) + "/cancel"
                result = await asyncio.to_thread(
                    client.post, path, json={"version": row["version"]}
                )
                assert result.status_code == 200
                assert client.post(path, json={"version": row["version"]}).status_code == 200
                handle = env.client.get_workflow_handle(row["workflow_id"])
                assert await asyncio.wait_for(handle.result(), timeout=10) == {"state": "cancelled"}
                assert client.get("/v1/application/agents/reviews").json()["reviews"] == []
                assert len(model.calls) == 2
            finally:
                await stop(service, task)

    asyncio.run(scenario())


def test_effect_receipt_reuses_completed_output_and_blocks_ambiguous_paid_retry(signed_in):
    client, app, _runner, _model, _ = fixture(signed_in)
    send(client)
    store = ExecutionStore(app.state.agent_store)
    row = store.reconcile("synthetic-model")[0]
    store.begin(row["run_id"])
    calls = []

    def perform():
        calls.append(1)
        return {"ok": True, "value": "synthetic cached result"}

    first = store.effect(row["run_id"], 0, "model", "tasks", {"a": 1}, perform)
    assert store.effect(row["run_id"], 0, "model", "tasks", {"a": 1}, perform) == first
    assert len(calls) == 1

    from yggdress_app.agent_models import AgentError

    with pytest.raises(AgentError, match="step changed"):
        store.effect(row["run_id"], 0, "model", "tasks", {"a": 2}, perform)

    def interrupted():
        raise RuntimeError("Synthetic process interruption before a receipt")

    with pytest.raises(RuntimeError):
        store.effect(row["run_id"], 1, "model", "tasks", {}, interrupted)
    with pytest.raises(AgentError, match="not repeated"):
        store.effect(row["run_id"], 1, "model", "tasks", {}, perform)
    assert len(calls) == 1


def test_saved_note_runs_lia_then_specialists_through_real_temporal(signed_in):
    item = {
        "commitment_identity": "finish-synthetic",
        "meaning": "deadline",
        "precision": "date",
        "disposition": "clear",
        "entity_type": "task",
        "original_phrase": "Finish on 2 January",
        "data": {
            "title": "Invented deadline",
            "objective": "Finish the synthetic goal",
            "due_date": "2030-01-02",
        },
    }
    client, app, runner, model, brain = fixture(
        signed_in,
        tool("return_interpretations", {"items": [item]}),
        tool("return_interpretations", {"items": []}),
    )
    note = app.state.notes_proxy.get("synthetic-observer", "sample")["note"]
    observed = runner.store.note_saved(note)
    assert runner.store.note_saved(note) == observed

    async def scenario():
        async with await environment() as env:
            service, task = await start(app, runner, env)
            try:
                tasks = await wait_for(
                    lambda: runner.store.tools.read("tasks", {})["task"]["items"]
                )
                assert tasks[0]["due_date"] == "2030-01-02"

                def finished():
                    with service.store.database.connect() as db:
                        return (
                            db.execute(
                                "SELECT count(*) AS n FROM app.agent_executions WHERE state='completed'"
                            ).fetchone()["n"]
                            == 2
                        )

                await wait_for(finished)
                assert len(runner.lia.calls) == 1 and len(model.calls) == 2
                assert client.get("/v1/application/agents/reviews").json()["reviews"] == []
                assert all(method == "GET" for method, _, _ in brain.calls)
            finally:
                await stop(service, task)

    asyncio.run(scenario())


@pytest.mark.slow  # > 40 s (timed 2026-11-22); CI only, not gates
def test_full_local_server_restart_preserves_waiting_approval(signed_in, tmp_path):
    client, app, runner, model, _ = fixture(
        signed_in, tool("propose_change", proposal()), text("Ready.")
    )
    binary = Path(__file__).resolve().parents[1] / "runtime/temporal-tools/temporal.exe"
    if not binary.is_file():
        pytest.skip("The local Windows lifecycle check requires the verified CLI.")
    options = {
        "binary": str(binary),
        "sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
        "database": str(tmp_path / "temporal/history.sqlite"),
    }

    async def scenario():
        service = TemporalAgentService(runner, local=options)
        app.state.agent_runtime = service
        task = asyncio.create_task(service.run())
        await wait_for(lambda: service.available)
        try:
            await asyncio.to_thread(send, client)

            def waiting():
                with service.store.database.connect() as db:
                    return db.execute(
                        "SELECT * FROM app.agent_executions WHERE state='waiting'"
                    ).fetchone()

            row = await wait_for(waiting)
            await stop(service, task)  # Stops the real server, not only the worker.
            service = TemporalAgentService(runner, local=options)
            app.state.agent_runtime = service
            task = asyncio.create_task(service.run())
            await wait_for(lambda: service.available)
            review = client.get("/v1/application/agents/reviews").json()["reviews"][0]
            response = await asyncio.to_thread(
                client.post,
                "/v1/application/agents/reviews/resolve",
                json={
                    "key": str(uuid4()),
                    "id": review["id"],
                    "version": review["version"],
                    "decision": "dismiss",
                },
            )
            assert response.status_code == 200, response.text
            result = await asyncio.wait_for(
                service.client.get_workflow_handle(row["workflow_id"]).result(), 10
            )
            assert result == {"state": "completed"} and len(model.calls) == 2
        finally:
            await stop(service, task)

    asyncio.run(scenario())


@pytest.mark.parametrize("agent", ["lia", "calendar", "yggdras"])
def test_each_existing_destination_uses_temporal_without_changing_its_role(signed_in, agent):
    replies = () if agent == "lia" else (text("Synthetic answer."),)
    client, app, runner, model, _ = fixture(signed_in, *replies)

    async def scenario():
        async with await environment() as env:
            service, task = await start(app, runner, env)
            try:
                sent = await asyncio.to_thread(send, client, agent)

                def done():
                    history = client.get(
                        "/v1/chat/conversations/" + sent["conversation"]["id"]
                    ).json()
                    return history if history["requests"][0]["state"] == "completed" else None

                history = await wait_for(done)
                assert history["messages"][-1]["agent_id"] == agent
                assert len(model.calls) == (0 if agent == "lia" else 1)
                assert len(runner.lia.calls) == (1 if agent == "lia" else 0)
            finally:
                await stop(service, task)

    asyncio.run(scenario())


def test_model_failure_is_sanitized_and_not_retried(signed_in):
    client, app, runner, _model, _ = fixture(signed_in)
    calls = []

    class Broken:
        def complete(self, **_kwargs):
            calls.append(1)
            raise RuntimeError("synthetic-private-provider-secret")

    runner.model_factory = lambda _name: Broken()

    async def scenario():
        async with await environment() as env:
            service, task = await start(app, runner, env)
            try:
                await asyncio.to_thread(send, client)

                def failed():
                    rows = client.get("/v1/application/agents/executions").json()["executions"]
                    return rows[0] if rows and rows[0]["state"] == "failed" else None

                row = await wait_for(failed)
                trace = await asyncio.to_thread(
                    client.get, "/v1/application/agents/executions/" + row["id"]
                )
                assert "synthetic-private-provider-secret" not in trace.text
                assert trace.json()["steps"][0]["state"] == "failed"
                await service.dispatch()
                assert calls == [1]
            finally:
                await stop(service, task)

    asyncio.run(scenario())


def test_execution_apis_require_session_and_csrf(signed_in):
    client, _app, runner, _model, _ = fixture(signed_in)
    send(client)
    store = ExecutionStore(runner.store)
    row = store.reconcile("synthetic")[0]
    path = "/v1/application/agents/executions/" + str(row["run_id"])
    assert client.get(path).status_code == 200
    assert (
        client.post(
            path + "/cancel", json={"version": 1}, headers={"X-Yggdress-CSRF": "wrong"}
        ).status_code
        == 403
    )
    client.cookies.clear()
    assert client.get(path).status_code == 401
    assert client.get("/v1/application/agents/executions").status_code == 401


def test_source_edit_invalidates_temporal_review(signed_in):
    client, app, runner, _model, _ = fixture(
        signed_in, tool("propose_change", proposal()), text("Ready.")
    )

    async def scenario():
        async with await environment() as env:
            service, task = await start(app, runner, env)
            try:
                sent = await asyncio.to_thread(send, client)

                def waiting():
                    with service.store.database.connect() as db:
                        return db.execute(
                            "SELECT * FROM app.agent_executions WHERE state='waiting'"
                        ).fetchone()

                row = await wait_for(waiting)
                review = client.get("/v1/application/agents/reviews").json()["reviews"][0]
                await asyncio.to_thread(
                    chat_command,
                    client,
                    "message.edit",
                    {"content": "Changed request"},
                    sent["message"],
                )
                decision = {
                    "key": str(uuid4()),
                    "id": review["id"],
                    "version": review["version"],
                    "decision": "accept",
                }
                result = await asyncio.to_thread(
                    client.post, "/v1/application/agents/reviews/resolve", json=decision
                )
                assert result.status_code == 409, result.text
                assert runner.store.tools.read("tasks", {})["task"]["items"] == []
                trace = service.store.trace(row["run_id"])
                assert trace["timings"]["pickup_ms"] >= 0
                assert trace["timings"]["result_ms"] >= 0
            finally:
                await stop(service, task)

    asyncio.run(scenario())


def test_core_crud_remains_available_when_execution_loop_has_stopped(signed_in):
    client, app, runner, model, _ = fixture(signed_in)
    service = TemporalAgentService(runner)
    service.loop = asyncio.new_event_loop()
    service.loop.close()
    service.wake = asyncio.Event()
    app.state.agent_runtime = service
    sent = send(client)
    assert sent["request"]["state"] == "queued"
    assert client.get("/v1/application/agents/status").json()["execution"]["ready"] is False
    assert client.get("/v1/chat/conversations/" + sent["conversation"]["id"]).status_code == 200
    assert model.calls == []


def test_terminated_workflow_invalidates_proposals_without_rerunning_models(signed_in):
    client, app, runner, model, _ = fixture(
        signed_in, tool("propose_change", proposal()), text("Ready.")
    )

    async def scenario():
        async with await environment() as env:
            service, task = await start(app, runner, env)
            try:
                await asyncio.to_thread(send, client)

                def waiting():
                    with service.store.database.connect() as db:
                        return db.execute(
                            "SELECT * FROM app.agent_executions WHERE state='waiting'"
                        ).fetchone()

                row = await wait_for(waiting)
                await env.client.get_workflow_handle(row["workflow_id"]).terminate(
                    "Synthetic lifecycle test"
                )
                await service.dispatch()
                assert service.store.trace(row["run_id"])["state"] == "failed"
                assert client.get("/v1/application/agents/reviews").json()["reviews"] == []
                assert len(model.calls) == 2
            finally:
                await stop(service, task)

    asyncio.run(scenario())
