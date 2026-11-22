"""The conductor's run loop.

`start` creates a run and executes it on a worker thread, detached from any HTTP
request: closing the browser does not stop it. All progress goes through the run's
Recorder into the event log, which streaming clients tail.

A run either answers directly (mode `answering`) or orchestrates: it plans (`planning`;
the Plan card appearing above the reply is the visible switch), runs ready steps in
parallel worker threads (`executing`), checks each step against its verification
point, sends failures back with the reason, skips steps whose dependencies failed, and
finally composes one answer from the verified results.
"""

from __future__ import annotations

import json
import logging
import os
import socket
import threading
import time
import uuid
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from typing import Any

from .history import ChatHistory
from .log import RunLog, RunNotFound, set_
from .models import (
    CHAT_DEFAULT,
    CHOOSABLE,
    ROLE_DEFAULTS,
    Finished,
    ModelError,
    Models,
    ReasoningDelta,
    Reset,
    TextDelta,
    ToolUse,
)
from .planning import PLANNER_SYSTEM, ROUTER_SYSTEM, PlanDraft, RouteDecision, to_plan
from .policy import Decision, Policy, PolicyStore
from .recorder import Recorder
from .state import MAX_ATTEMPTS, Approval, Plan, RunState, ToolCall
from .tools import StaticToolbox, Toolbox
from .verify import verify
from .workers import WorkerResult, run_worker

LOG = logging.getLogger(__name__)
PARALLEL_STEPS = 3
HEARTBEAT_SECONDS = 20.0  # keep live runs fresh (stale after log.HEARTBEAT_STALE_SECONDS)
SWEEP_SECONDS = 60.0  # mark runs of stopped processes interrupted
APPROVAL_TIMEOUT_SECONDS = 30 * 60  # an unanswered approval card counts as "no"

SYSTEM = (
    "You are Yggdras, Manoj's second brain and assistant. Answer plainly and briefly. "
    "Say when you do not know something rather than guessing. Use Markdown only when it "
    "helps (lists, tables, code)."
)
COMPOSE_SYSTEM = (
    SYSTEM + " You planned this request and your workers carried out the steps below. "
    "Write Manoj's answer from their verified results. If a step failed or was skipped, "
    "say plainly what could not be done and why; never present it as done."
)


def process_owner() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


class Cancelled(Exception):
    pass


@dataclass
class Context:
    """Everything one run needs while it executes."""

    run_id: str
    conversation_id: str
    request: str
    model: str
    recorder: Recorder
    history: list[dict[str, Any]]
    cancel: threading.Event
    user_message_id: str
    lock: threading.Lock = field(default_factory=threading.Lock)
    usage_count: int = 0
    waiting: int = 0  # approval cards currently open (run status is 'waiting' while > 0)
    tools: list[ToolCall] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    def check_cancelled(self) -> None:
        if self.cancel.is_set():
            raise Cancelled


class Conductor:
    def __init__(
        self,
        log: RunLog,
        models: Models,
        history: ChatHistory,
        *,
        toolbox: Toolbox | None = None,
        policy: Policy | None = None,
        policy_store: PolicyStore | None = None,
        owner: str | None = None,
        workers: int = 16,  # runs waiting on an approval hold a thread; size for that
    ):
        self.log, self.models, self.history = log, models, history
        self.toolbox = toolbox or StaticToolbox()
        self.policy_store = policy_store or PolicyStore(log.database)
        self.policy = policy or Policy(models, self.policy_store.get)
        # (run_id, tool id) -> [event, approval]: a worker waiting for Manoj's answer.
        self._approvals: dict[tuple[str, str], list] = {}
        self.owner = owner or process_owner()
        self._pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="conductor")
        self._steps = ThreadPoolExecutor(max_workers=PARALLEL_STEPS * workers,
                                         thread_name_prefix="conductor-step")  # fmt: skip
        self._cancels: dict[str, threading.Event] = {}
        self._lock = threading.Lock()
        self._stopping = threading.Event()
        self._heartbeat: threading.Thread | None = None  # started with the first run

    # ---- public API ------------------------------------------------------------------
    def start(self, request: str, conversation_id: str | None = None, model: str = "",
              images: list[dict[str, Any]] | None = None) -> RunState:  # fmt: skip
        model = model if model in CHOOSABLE else CHAT_DEFAULT
        conversation = self.history.ensure_conversation(conversation_id, request, model)
        context_turns = self.history.recent(conversation)
        state = RunState(
            run_id=str(uuid.uuid4()), conversation_id=conversation, model=model, status="running"
        )
        # The run row first: chat messages older than a conversation's first run are
        # shown as plain history, so this run's own messages must come after it.
        self.log.start(state, request, self.owner)
        user_message = self.history.save_user(conversation, request, model)
        cancel = threading.Event()
        with self._lock:
            self._cancels[state.run_id] = cancel
            if self._heartbeat is None:
                self._heartbeat = threading.Thread(
                    target=self._keep_alive, name="conductor-heartbeat", daemon=True
                )
                self._heartbeat.start()
        context = Context(
            run_id=state.run_id,
            conversation_id=conversation,
            request=request,
            model=model,
            recorder=Recorder(self.log, state.run_id, self.owner),
            history=with_request(context_turns, request, images or []),
            cancel=cancel,
            user_message_id=user_message,
        )
        self._pool.submit(self._execute, context)
        return state

    def cancel(self, run_id: str) -> bool:
        with self._lock:
            event = self._cancels.get(run_id)
        if event:
            event.set()
        return event is not None

    def shutdown(self) -> None:
        self._stopping.set()
        self._pool.shutdown(wait=True)
        self._steps.shutdown(wait=True)

    def _keep_alive(self) -> None:
        """Heartbeats for this process's live runs; a periodic sweep marks runs whose
        process stopped (a restart, a crash) interrupted, so nothing stays 'running'."""
        last_sweep = 0.0
        while not self._stopping.wait(HEARTBEAT_SECONDS):
            with self._lock:
                live = list(self._cancels)
            for run_id in live:
                try:
                    self.log.heartbeat(run_id, self.owner)
                except Exception:
                    LOG.warning("Heartbeat failed for run %s.", run_id, exc_info=True)
            if time.monotonic() - last_sweep >= SWEEP_SECONDS:
                last_sweep = time.monotonic()
                try:
                    self.log.interrupt_stale()
                    self.log.bus.prune()
                except Exception:
                    LOG.warning("Stale-run sweep failed.", exc_info=True)

    # ---- execution -------------------------------------------------------------------
    def _execute(self, ctx: Context) -> None:
        try:
            self.run(ctx)
            ctx.recorder.flush()
            final, _ = self.log.snapshot(ctx.run_id)
            self.history.save_assistant(
                ctx.conversation_id, final.text, ctx.user_message_id, ctx.model
            )
            ctx.recorder.set(["status"], "completed")
        except Cancelled:
            self._finish(ctx, "cancelled", "")
        except ModelError as error:
            self._finish(ctx, "failed", str(error))
        except Exception:
            LOG.exception("Run %s failed.", ctx.run_id)
            self._finish(ctx, "failed", "Something went wrong while answering.")
        finally:
            with self._lock:
                self._cancels.pop(ctx.run_id, None)

    def _finish(self, ctx: Context, status: str, error: str) -> None:
        try:
            ctx.recorder.flush()
            ctx.recorder.sets([(["error"], error[:2000]), (["status"], status)])
        except Exception:
            LOG.exception("Could not record the end of run %s.", ctx.run_id)

    def run(self, ctx: Context) -> None:
        if self.route(ctx) == "answer":
            self.answer(ctx, system=SYSTEM, messages=ctx.history)
            return
        ctx.recorder.set(["mode"], "planning")
        plan = self.plan(ctx)
        ctx.recorder.sets([(["plan"], plan.model_dump(mode="json")), (["mode"], "executing")])
        plan = self.execute(ctx, plan)
        # The last history turn is the (possibly merged) request; compose_turn restates it.
        self.answer(
            ctx, system=COMPOSE_SYSTEM, messages=[*ctx.history[:-1], compose_turn(ctx, plan)]
        )

    # ---- deciding and planning -------------------------------------------------------
    def route(self, ctx: Context) -> str:
        ctx.check_cancelled()
        decision, usage = self.models.structured(
            role="router",
            model=ROLE_DEFAULTS["router"],
            system=ROUTER_SYSTEM,
            messages=recent_turns(ctx.history, 6),
            schema=RouteDecision,
            max_tokens=300,
        )
        self.record_usage(ctx, Finished(usage, "end_turn"))
        return decision.mode

    def plan(self, ctx: Context) -> Plan:
        ctx.check_cancelled()
        draft, usage = self.models.structured(
            role="orchestrator",
            model=ctx.model,
            system=PLANNER_SYSTEM,
            messages=ctx.history,
            schema=PlanDraft,
        )
        self.record_usage(ctx, Finished(usage, "end_turn"))
        try:
            return to_plan(draft)
        except ValueError as error:
            raise ModelError(f"The plan was not usable: {error}") from error

    # ---- executing: the parallel scheduler -------------------------------------------
    def execute(self, ctx: Context, plan: Plan) -> Plan:
        """Run ready steps in parallel, verify each, retry failures with feedback, skip
        steps whose dependencies failed. This thread is the only writer of step state."""
        index = {s.id: i for i, s in enumerate(plan.steps)}
        feedback: dict[str, str] = {}
        running: dict[Future, str] = {}
        try:
            while True:
                ctx.check_cancelled()
                self._skip_blocked(ctx, plan, index)
                for step in plan.ready():
                    if len(running) >= PARALLEL_STEPS:
                        break
                    if step.id in running.values():
                        continue
                    i = index[step.id]
                    step.status, step.attempts = "in_progress", step.attempts + 1
                    ctx.recorder.sets([(["plan", "steps", i], step.model_dump(mode="json"))])
                    inputs = {d: plan.steps[index[d]].result for d in step.depends_on}
                    future = self._steps.submit(
                        run_worker, self, ctx, step.model_copy(), inputs, feedback.get(step.id, "")
                    )
                    running[future] = step.id
                if not running:
                    return plan
                done, _ = wait(list(running), timeout=1.0, return_when=FIRST_COMPLETED)
                for future in done:
                    step = plan.steps[index[running.pop(future)]]
                    self._judge(ctx, plan, index[step.id], step, future, feedback)
        except BaseException:
            # Stopping (cancel or a fault): stop every worker, then close what is open so
            # the frozen run never shows a step or tool still in progress.
            ctx.cancel.set()
            wait(list(running), timeout=30)
            self._close_open(ctx, plan, index)
            raise

    def _close_open(self, ctx: Context, plan: Plan, index: dict[str, int]) -> None:
        try:
            changes = []
            for step in plan.steps:
                if step.status == "in_progress":
                    step.status, step.verdict, step.reason = "completed", "failed", "Stopped."
                    changes.append(
                        (["plan", "steps", index[step.id]], step.model_dump(mode="json"))
                    )
            with ctx.lock:
                for slot, call in enumerate(ctx.tools):
                    if call.state in ("input-streaming", "input-available", "approval-responded"):
                        spec = self.toolbox.get(call.name)
                        changes_data = (
                            spec is not None and spec.stakes_for(call.input) != "low-reversible"
                        )
                        call.state = "output-error"
                        call.error = (
                            "Stopped while running: the change may or may not have been made. "
                            "Check before trying again."
                            if changes_data
                            else "Stopped."
                        )
                    elif call.state == "approval-requested":
                        call.state, call.error = "output-denied", "Stopped before an answer."
                    else:
                        continue
                    changes.append((["tools", slot], call.model_dump(mode="json")))
            if changes:
                ctx.recorder.sets(changes)
        except Exception:
            LOG.exception("Could not close the open work of run %s.", ctx.run_id)

    def _changed_something(self, ctx: Context, step_id: str) -> bool:
        with ctx.lock:
            for call in ctx.tools:
                spec = self.toolbox.get(call.name)
                if (call.step_id == step_id and call.state == "output-available" and spec
                        and spec.stakes_for(call.input) != "low-reversible"):  # fmt: skip
                    return True
        return False

    def _judge(self, ctx, plan: Plan, i: int, step, future: Future, feedback: dict[str, str]):
        final = False
        try:
            result: WorkerResult = future.result()
            text = result.text
            if result.refused:  # Manoj (or a hard rule) said no: never re-ask by retrying
                passed, reason, final = False, result.refused, True
            else:
                outcome = self._verify(ctx, step, result)
                passed, reason = outcome.passed, outcome.reason
        except Cancelled:
            raise
        except Exception as error:
            LOG.warning("Step %s failed in run %s.", step.id, ctx.run_id, exc_info=True)
            passed, text = False, ""
            reason = str(error) if isinstance(error, ModelError) else "The worker failed."
        if not passed and not final and self._changed_something(ctx, step.id):
            # A retry would repeat a change that already happened (a second event...).
            final = True
            reason = f"{reason} Not retried: this step already made a change."
        if passed:
            step.status, step.verdict, step.reason = "completed", "passed", ""
        elif final:
            step.status, step.verdict, step.reason = "completed", "failed", reason[:1000]
        elif step.attempts < MAX_ATTEMPTS:
            step.status, step.verdict, step.reason = "pending", "failed", reason
            feedback[step.id] = reason
        else:
            step.status, step.verdict = "completed", "failed"
            step.reason = f"Gave up after {step.attempts} attempts: {reason}"[:1000]
        step.result = text[:20000]
        ctx.recorder.sets([(["plan", "steps", i], step.model_dump(mode="json"))])

    def _skip_blocked(self, ctx: Context, plan: Plan, index: dict[str, int]) -> None:
        failed = {s.id for s in plan.steps if s.status == "completed" and s.verdict == "failed"}
        changed = True
        while changed:
            changed = False
            for step in plan.steps:
                blocked = step.status == "pending" and failed & set(step.depends_on)
                if blocked:
                    first = min(failed & set(step.depends_on))
                    step.status, step.verdict = "in_progress", None
                    ctx.recorder.sets(
                        [(["plan", "steps", index[step.id]], step.model_dump(mode="json"))]
                    )
                    step.status, step.verdict = "completed", "failed"
                    step.reason = f"Skipped: it needs step {first}, which failed."
                    ctx.recorder.sets(
                        [(["plan", "steps", index[step.id]], step.model_dump(mode="json"))]
                    )
                    failed.add(step.id)
                    changed = True

    # ---- answering -------------------------------------------------------------------
    def answer(self, ctx: Context, *, system: str, messages: list[dict[str, Any]]) -> str:
        ctx.check_cancelled()
        text = ""
        for event in self.models.stream(
            role="orchestrator", model=ctx.model, system=system, messages=messages
        ):
            ctx.check_cancelled()
            if isinstance(event, Reset):  # a fallback model took over: drop the partial
                text = ""
                ctx.recorder.sets([(["text"], ""), (["reasoning"], "")])
            elif isinstance(event, TextDelta):
                text += event.text
                ctx.recorder.text(["text"], event.text)
            elif isinstance(event, ReasoningDelta):
                ctx.recorder.text(["reasoning"], event.text)
            elif isinstance(event, Finished):
                self.record_usage(ctx, event)
        return text

    def _verify(self, ctx: Context, step, result: WorkerResult):
        """Judge a result. A judge outage is retried on its own; the worker's (paid)
        result is never thrown away because the checker was briefly unavailable."""
        for attempt in range(3):
            ctx.check_cancelled()
            try:
                outcome = verify(self.models, step, result.text, result.tool_errors)
                break
            except ModelError:
                if attempt == 2:
                    raise
                time.sleep(1.5 * (attempt + 1))
        if outcome.usage:
            self.record_usage(ctx, Finished(outcome.usage, "end_turn"))
        return outcome

    # ---- shared by workers (thread-safe) ---------------------------------------------
    def record_usage(self, ctx: Context, finished: Finished) -> None:
        with ctx.lock:
            slot = ctx.usage_count
            ctx.recorder.set(["usage", slot], finished.usage.model_dump(mode="json"))
            ctx.usage_count += 1  # only after the write landed: memory never runs ahead

    def call_tool(self, ctx: Context, step_id: str, use: ToolUse) -> tuple[Any, bool]:
        """One tool call for a worker: record it, pass it through the safety layers
        (policy.py), then run it, ask Manoj, or refuse it."""
        spec = self.toolbox.get(use.name)
        with ctx.lock:
            slot = len(ctx.tools)
            # Prefixed with its slot: unique per run even when a model reuses an id.
            call = ToolCall(id=f"{slot}-{use.id}"[:80], name=use.name[:80], step_id=step_id,
                            input=bounded(use.input, 20_000), state="input-available")  # fmt: skip
            ctx.recorder.set(["tools", slot], call.model_dump(mode="json"))
            ctx.tools.append(call)  # only after the write landed
        if spec is None:
            return self._tool_done(ctx, slot, error=f"Unknown tool {use.name}.")
        ctx.check_cancelled()
        with ctx.lock:  # did this step read notes? Their text may have shaped the input.
            untrusted = any(
                c.step_id == step_id
                and (s := self.toolbox.get(c.name)) is not None
                and s.reads_notes
                for c in ctx.tools
            )
        try:
            decision = self.policy.decide(spec, use.input, untrusted=untrusted)
        except Exception:
            LOG.warning(
                "Safety check failed for %s in run %s.", use.name, ctx.run_id, exc_info=True
            )
            stakes = "high-irreversible"
            try:
                stakes = spec.stakes_for(use.input)
            except Exception:
                LOG.warning("Could not classify %s.", use.name, exc_info=True)
            decision = Decision("ask", "user", stakes, "The safety check was unavailable.")
        if decision.usage:
            self.record_usage(ctx, Finished(decision.usage, "end_turn"))
        with ctx.lock:
            call = ctx.tools[slot]
            call.stakes, call.decided_by = decision.stakes, decision.decided_by
            if decision.notify:
                call.intent = "Done without asking (reversible); kept in the review trail."
        if decision.action == "deny":
            message = f"Refused by the safety rules: {decision.reason}"
            return self._tool_done(ctx, slot, error=message, state="output-denied")
        if decision.action == "ask":
            approval = self._ask(ctx, slot, spec, use.input, decision.reason)
            if not approval.approved:
                reason = approval.reason or "Manoj declined."
                return self._tool_done(
                    ctx, slot, error=f"Not approved: {reason}", state="output-denied"
                )
        return self._run_tool(ctx, slot, spec, use.input)

    def _ask(self, ctx: Context, slot: int, spec, arguments: dict, why: str) -> Approval:
        """Record an approval card and wait (holding no lock) for Manoj's answer."""
        event = threading.Event()
        with ctx.lock:
            call = ctx.tools[slot]
            call.state = "approval-requested"
            call.intent = intent(spec, arguments, why)
            key = (ctx.run_id, call.id)
            self._approvals[key] = [event, None]
            ctx.waiting += 1
            changes = [(["tools", slot], call.model_dump(mode="json"))]
            if ctx.waiting == 1:
                changes.append((["status"], "waiting"))
            ctx.recorder.sets(changes)
        deadline = time.monotonic() + APPROVAL_TIMEOUT_SECONDS
        try:
            while not event.wait(1.0):
                ctx.check_cancelled()
                if time.monotonic() > deadline:
                    break
        finally:
            with self._lock:
                answer = self._approvals.pop(key, [None, None])[1]
        approval = answer or Approval(approved=False, reason="No answer within 30 minutes.")
        with ctx.lock:
            call = ctx.tools[slot]
            ctx.waiting -= 1
            changes = []
            if answer is not None:
                call.state, call.approval, call.decided_by = "approval-responded", approval, "user"
                changes.append((["tools", slot], call.model_dump(mode="json")))
            else:
                call.approval = approval
            if ctx.waiting == 0:
                changes.append((["status"], "running"))
            if changes:
                ctx.recorder.sets(changes)
        return approval

    def answer_approval(self, command: dict[str, Any]) -> str | None:
        """Manoj's answer to an approval card: {runId, toolCallId, approved, reason}.
        Returns the run id to keep streaming, or None."""
        run_id = str(command.get("runId", ""))
        tool_id = str(command.get("toolCallId", ""))[:80]
        approval = Approval(approved=command.get("approved") is True,
                            reason=str(command.get("reason", ""))[:1000])  # fmt: skip
        with self._lock:
            waiter = self._approvals.get((run_id, tool_id))
            if waiter is not None:
                waiter[1] = approval
                waiter[0].set()
                return run_id
        return self._answer_orphan(run_id, tool_id, approval)

    def _answer_orphan(self, run_id: str, tool_id: str, approval: Approval) -> str | None:
        """No live worker waits for this card. If the run is alive in this process, the
        answer is late or a duplicate: ignore it. Only a run whose process stopped (it is
        interrupted, or waiting with a stale heartbeat) records the answer and is
        interrupted, so the client offers to try again."""
        with self._lock:
            if run_id in self._cancels:
                return None
        try:
            state, _ = self.log.snapshot(run_id)
        except RunNotFound:
            return None
        dead = state.status == "interrupted" or (
            state.status == "waiting" and self.log.is_stale(run_id)
        )
        if not dead:
            return None
        for slot, call in enumerate(state.tools):
            if call.id == tool_id and call.state == "approval-requested":
                call.state, call.approval, call.decided_by = "approval-responded", approval, "user"
                ops = [set_(["tools", slot], call.model_dump(mode="json"))]
                if state.status == "waiting":
                    ops.append(set_(["status"], "interrupted"))
                self.log.append(run_id, ops)
                return run_id
        return None

    def _run_tool(self, ctx: Context, slot: int, spec, arguments: dict) -> tuple[Any, bool]:
        try:
            return self._tool_done(ctx, slot, output=spec.run(arguments))
        except Exception as error:  # noqa: BLE001 - a tool failure goes to the worker, not up
            return self._tool_done(ctx, slot, error=f"{type(error).__name__}: {error}"[:500])

    def _tool_done(self, ctx: Context, slot: int, *, output: Any = None, error: str = "",
                   state: str | None = None) -> tuple[Any, bool]:  # fmt: skip
        output = bounded(output)
        with ctx.lock:
            call = ctx.tools[slot]
            call.state = state or ("output-error" if error else "output-available")
            call.output, call.error = (None, error) if error else (output, "")
            ctx.recorder.set(["tools", slot], call.model_dump(mode="json"))
        return (error, True) if error else (output, False)


def intent(spec, arguments: dict[str, Any], why: str) -> str:
    """The Intent Preview, built from the fields that will actually be used (operation,
    target, data), not from the model's own summary, which is shown only as its note."""
    operation = arguments.get("operation")
    head = str(operation) if isinstance(operation, str) else spec.name
    target = f" on {arguments['id']}" if arguments.get("id") else ""
    data = arguments.get("data")
    fields = f" with {json.dumps(data, sort_keys=True, default=str)[:240]}" if data else ""
    note = str(arguments.get("explanation") or "").strip()
    note = f" Model's note: {note[:140]}." if note else ""
    return f"{head}{target}{fields}.{note} ({why})"[:500]


def with_request(turns: list[dict[str, Any]], request: str,
                 images: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:  # fmt: skip
    """Append the new request (with any attached images), merging it into a trailing
    user turn (e.g. after a failed run left no answer) so the model never sees two user
    turns in a row."""
    turns = [dict(t) for t in turns]
    if turns and turns[-1]["role"] == "user":
        request = f"{turns.pop()['content']}\n\n{request}"
    content: Any = [*images, {"type": "text", "text": request}] if images else request
    return [*turns, {"role": "user", "content": content}]


def bounded(value: Any, limit: int = 40_000) -> Any:
    """Tool outputs are stored on the run; an oversized one is cut, visibly, rather than
    failing the run when it is saved."""
    text = json.dumps(value, default=str)
    if len(text) <= limit:
        return json.loads(text)
    return {"truncated": True, "preview": text[:limit]}


def compose_turn(ctx: Context, plan: Plan) -> dict[str, str]:
    """The last turn of the compose prompt. Only verified results are given as facts;
    failed steps say why and carry no (rejected) result text."""
    last = ctx.history[-1]["content"] if ctx.history else ctx.request
    asked = (
        last
        if isinstance(last, str)
        else " ".join(b.get("text", "") for b in last if b.get("type") == "text")
    )
    lines = [f"Manoj asked: {asked}", f"Plan: {plan.title}"]
    for step in plan.steps:
        if step.verdict == "passed":
            lines.append(f"- {step.title} [verified]\n{step.result[:4000]}")
        else:
            lines.append(f"- {step.title} [NOT DONE: {step.reason}] (no verified result)")
    return {"role": "user", "content": "\n\n".join(lines)}


def recent_turns(history: list[dict[str, Any]], count: int) -> list[dict[str, Any]]:
    """The last `count` turns, never starting with an assistant turn."""
    turns = history[-count:]
    while turns and turns[0]["role"] != "user":
        turns = turns[1:]
    return turns
