"""Worker threads: each plan step runs as a small sub-agent with a clean context (its
task, the results it depends on, and feedback from a failed check), its own model, and
the run's tools. It returns only its result; the orchestrator judges it."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .models import Finished, Reset, TextDelta, ToolUse
from .state import Step

if TYPE_CHECKING:
    from .orchestrator import Conductor, Context

MAX_TURNS = 4

WORKER_SYSTEM = (
    "You are one worker in Yggdras, Manoj's second brain. Do only the task you are given. "
    "Use the tools to look things up rather than guessing; never invent facts about "
    "Manoj. Finish with the result itself, concise and complete, without preamble."
)


REFUSAL_PREFIXES = ("Refused by the safety rules", "Not approved")


@dataclass
class WorkerResult:
    text: str
    tool_errors: list[str] = field(default_factory=list)  # from the last tool round only
    refused: str = ""  # a call was refused or declined: the step must not be retried


def brief(step: Step, inputs: dict[str, str], feedback: str, request: str) -> str:
    parts = [f"Manoj asked: {request}", f"Your task: {step.title}", f"Done means: {step.check}"]
    for step_id, result in inputs.items():
        parts.append(f"Result of step {step_id}:\n{result[:6000]}")
    if feedback:
        parts.append(f"Your previous attempt did not pass the check: {feedback}\nFix that.")
    return "\n\n".join(parts)


def run_worker(conductor: Conductor, ctx: Context, step: Step, inputs: dict[str, str],
               feedback: str) -> WorkerResult:  # fmt: skip
    messages: list[dict[str, Any]] = [
        {"role": "user", "content": brief(step, inputs, feedback, ctx.request)}
    ]
    specs = conductor.toolbox.specs()
    errors: list[str] = []
    refused = ""
    text = ""
    for _ in range(MAX_TURNS):
        ctx.check_cancelled()
        text, uses, finished = "", [], None
        for event in conductor.models.stream(
            role="worker",
            model=step.model or ctx.model,
            system=WORKER_SYSTEM,
            messages=messages,
            tools=specs or None,
        ):
            ctx.check_cancelled()
            if isinstance(event, Reset):
                text, uses = "", []
            elif isinstance(event, TextDelta):
                text += event.text
            elif isinstance(event, ToolUse):
                uses.append(event)
            elif isinstance(event, Finished):
                finished = event
        if finished:
            conductor.record_usage(ctx, finished)
        if not uses:
            return WorkerResult(text.strip(), errors, refused)
        messages.append({"role": "assistant", "content": finished.content if finished else []})
        results = []
        errors = []  # a later round that recovers clears earlier errors
        for use in uses:
            content, is_error = conductor.call_tool(ctx, step.id, use)
            if is_error:
                errors.append(content)
                if str(content).startswith(REFUSAL_PREFIXES):
                    refused = refused or str(content)
            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": use.id,
                    "content": content if isinstance(content, str) else json.dumps(content),
                    "is_error": is_error,
                }
            )
        messages.append({"role": "user", "content": results})
    # Out of turns without a final answer: an empty result fails the free code check.
    return WorkerResult("", [*errors, "The worker ran out of turns."], refused)
