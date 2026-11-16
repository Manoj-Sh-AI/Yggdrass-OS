"""Replayable agent execution. All model, filesystem, network and DB I/O is activity-owned."""

import asyncio
import json
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError

with workflow.unsafe.imports_passed_through():
    from .agent_effects import Effect
    from .agent_models import AgentError, ModelReply
    from .agent_orchestrator import Yggdras
    from .agent_source import interpret_steps
    from .agent_specialists import AgentResult, Budget, Specialist


@workflow.defn(name="YggdrasAgentExecutionV1")
class AgentExecution:
    def __init__(self):
        self.identifier = ""
        self.phase = "pending"
        self.ordinal = 0
        self.cancelled = False
        self.changed = False
        self.pending = 0
        self.decisions = asyncio.Lock()

    @workflow.query
    def status(self) -> dict:
        return {"state": self.phase, "steps": self.ordinal, "pending_reviews": self.pending}

    @workflow.signal
    def cancel(self):
        self.cancelled = True
        self.changed = True

    @workflow.signal
    def reconcile(self):
        self.changed = True

    @workflow.update
    async def resolve(self, decision: dict) -> dict:
        async with self.decisions:
            if self.phase == "running":
                await workflow.wait_condition(lambda: self.phase != "running" or self.cancelled)
            if self.phase != "waiting" or self.cancelled:
                return {
                    "ok": False,
                    "status": 409,
                    "error": "This execution is no longer waiting for that decision.",
                }
            result = await self.call("app_agent_review", {"decision": decision})
            if result["ok"]:
                self.pending = result["pending"]
                self.changed = True
            return result

    async def call(self, name, values=None, *, paid=False):
        return await workflow.execute_activity(
            name,
            {"run_id": self.identifier, **(values or {})},
            start_to_close_timeout=timedelta(seconds=180 if paid else 45),
            retry_policy=RetryPolicy(
                maximum_attempts=1 if paid else 3, initial_interval=timedelta(seconds=1)
            ),
        )

    async def effect(self, effect):
        if self.cancelled:
            raise AgentError("This request was cancelled.")
        ordinal = self.ordinal
        self.ordinal += 1
        result = await self.call(
            "app_agent_effect",
            {
                "ordinal": ordinal,
                "kind": effect.kind,
                "agent": effect.agent,
                "data": effect.data,
            },
            paid=effect.kind in ("model", "lia"),
        )
        if not result["ok"]:
            if result.get("status") in (400, 404, 409, 422):
                raise ValueError(result["error"])
            raise AgentError(result["error"])
        return ModelReply(**result["value"]) if effect.kind == "model" else result["value"]

    async def drive(self, steps):
        value, error = None, None
        while True:
            try:
                effect = steps.throw(error) if error else steps.send(value)
            except StopIteration as done:
                return done.value
            error = None
            try:
                value = await self.effect(effect)
            except (AgentError, ValueError) as caught:
                error = caught

    @workflow.run
    async def run(self, identifier: str) -> dict:
        self.identifier = identifier
        self.phase = "running"
        result, error = None, ""
        try:
            prepared = await self.call("app_agent_prepare")
            budget = Budget(
                deadline=workflow.now().timestamp() + 180, clock=lambda: workflow.now().timestamp()
            )
            context = prepared["context"]
            cancelled = lambda: self.cancelled
            if prepared["kind"] == "chat":
                agent = prepared["agent"]
                if agent == "lia":
                    if prepared["has_files"]:
                        raise AgentError(
                            "Direct Lia attachment ingestion is not connected. The files remain saved."
                        )
                    answer = await self.effect(
                        Effect(
                            "lia",
                            "lia",
                            {
                                "question": context["content"],
                                "model": prepared["model"],
                                "context": "This application chat channel is read-only. Direct note changes to Notes; do not imply a write occurred. Recent conversation data:\n"
                                + json.dumps(context["history"][-6:], ensure_ascii=False),
                            },
                        )
                    )
                    result = AgentResult(answer)
                else:
                    role = (
                        Specialist(agent, None, None)
                        if agent in ("tasks", "calendar")
                        else Yggdras(None, None, None)
                    )
                    result = await self.drive(
                        role.steps(context["request"], budget=budget, cancelled=cancelled)
                    )
                    if agent in ("tasks", "calendar") and result.proposals:
                        result.answer += "\n\nProposed only—use Review changes to apply or dismiss."
            elif prepared["kind"] == "note":
                if not context["superseded"]:
                    event = context["event"]
                    answer = await self.effect(
                        Effect(
                            "lia",
                            "lia",
                            {
                                "question": "Read the current note [["
                                + event["slug"]
                                + "]]. Explain any explicit commitments, dates, time ranges and cancellations, quoting the original phrases and distinguishing historical or uncertain context. If there are none, say so. Do not edit the Brain.",
                                "context": "Application handoff for saved note revision "
                                + event["revision"]
                                + ".",
                                "model": "default",
                            },
                        )
                    )
                    await self.effect(Effect("publish_note", "lia", {"answer": answer}))
            else:
                event, body = context["event"], context["source_body"]
                domains = ["tasks", "calendar"] if event["lifecycle"] == "active" else ["calendar"]
                for domain in domains:
                    cursor = await self.effect(Effect("cursor", domain))
                    items = (
                        await self.drive(interpret_steps(domain, event, cursor, body, budget))
                        if body
                        else []
                    )
                    await self.effect(
                        Effect(
                            "commit_handoff",
                            domain,
                            {
                                "cursor": cursor,
                                "items": [item.model_dump(mode="json") for item in items],
                            },
                        )
                    )
                await self.effect(Effect("ack_handoff", "yggdras"))
        except (AgentError, ValueError) as caught:
            error = str(caught)[:2000]
        except ActivityError:
            error = "An execution step was interrupted. Completed steps remain recorded; paid calls were not automatically repeated."
        except Exception:  # noqa: BLE001 -- fail visibly without recording private failures
            error = "The execution could not finish. Resend explicitly to retry."
        finished = await self.call(
            "app_agent_finish",
            {
                "answer": result.answer if result else "The saved context was processed.",
                "proposals": [p.model_dump(mode="json") for p in result.proposals]
                if result
                else [],
                "error": error,
            },
        )
        self.phase, self.pending = finished["state"], finished["pending"]
        while self.pending:
            self.phase = "waiting"
            await workflow.wait_condition(lambda: self.changed or self.cancelled)
            self.changed = False
            checked = await self.call("app_agent_review", {"cancel": self.cancelled})
            self.pending = checked["pending"]
            self.phase = checked["state"]
        await workflow.wait_condition(workflow.all_handlers_finished)
        return {"state": self.phase}
