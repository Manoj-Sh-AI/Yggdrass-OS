"""Verification points: every step's result is checked before it counts as done.
Code checks run first (free, exact); only what code cannot decide goes to a Haiku judge
[principle: obvious is free, significant is paid]."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field

from .models import ROLE_DEFAULTS, Models
from .state import Step, Usage


class Judgement(BaseModel):
    model_config = ConfigDict(extra="forbid")
    passed: bool
    reason: str = Field(description="one sentence; if failed, what is missing or wrong")


@dataclass(frozen=True)
class Outcome:
    passed: bool
    reason: str
    usage: Usage | None = None


JUDGE_SYSTEM = (
    "You check one step of a plan. Given the step, its check and the worker's result, "
    "decide whether the result satisfies the check. Be strict about facts the check "
    "names and lenient about wording. If it fails, say in one sentence what is missing."
)


def code_check(result: str, tool_errors: list[str]) -> Outcome | None:
    """A verdict code can give without a model, or None."""
    if tool_errors:
        return Outcome(False, f"A tool failed: {tool_errors[0][:300]}")
    if not result.strip():
        return Outcome(False, "The worker returned no result.")
    return None


def verify(models: Models, step: Step, result: str, tool_errors: list[str]) -> Outcome:
    decided = code_check(result, tool_errors)
    if decided:
        return decided
    judgement, usage = models.structured(
        role="verifier",
        model=ROLE_DEFAULTS["verifier"],
        system=JUDGE_SYSTEM,
        messages=[
            {
                "role": "user",
                "content": f"Step: {step.title}\nCheck: {step.check}\n\nResult:\n{result[:12000]}",
            }
        ],
        schema=Judgement,
        max_tokens=500,
    )
    return Outcome(judgement.passed, judgement.reason.strip()[:1000], usage)
