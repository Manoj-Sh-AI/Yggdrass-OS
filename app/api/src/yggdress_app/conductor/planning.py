"""Deciding and planning: the cheap router (Haiku) picks answer vs orchestrate, and the
orchestrator model writes a plan as structured output (Sonnet/Opus 5.5 reject forced
tool choice, so structured outputs are the documented route [cited])."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .state import Plan, Step

WORKER_MODELS = ("claude-haiku-5-5", "claude-sonnet-5-5")


class RouteDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["answer", "orchestrate"]
    reason: str = Field(max_length=300)


class StepDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(description="short id like s1, s2")
    title: str = Field(description="action word + specific item + limits, under 100 chars")
    check: str = Field(description="what must be true of the result for this step to be done")
    depends_on: list[str] = Field(description="ids of steps whose results this step needs")
    worker: Literal["haiku", "sonnet"] = Field(
        description="haiku for lookups and simple steps; sonnet for judgement or writing"
    )


class PlanDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str
    steps: list[StepDraft] = Field(min_length=1, max_length=8)


ROUTER_SYSTEM = (
    "Decide how Yggdras should handle Manoj's latest message. Choose 'answer' for "
    "conversation, single questions and anything one reply can do. Choose 'orchestrate' "
    "only when the request needs several distinct pieces of work (looking things up in "
    "several places, comparing, preparing several items, multi-part changes). When unsure, "
    "choose 'answer'."
)

PLANNER_SYSTEM = (
    "Break Manoj's request into 1 to 8 steps that worker agents will carry out. Each step "
    "must be self-contained and name exactly what to do (action word + specific item + "
    "limits, e.g. 'Find Saturday's free slots after 10:00'), and have a check: one "
    "sentence saying what must be true of its result. Make steps independent where "
    "possible so they can run at the same time; list a dependency only when a step needs "
    "another step's result. Use the haiku worker for lookups and simple steps, sonnet for "
    "judgement or writing."
)


def _step_id(raw: str, used: set[str]) -> str:
    base = re.sub(r"[^A-Za-z0-9_-]", "-", raw)[:30].strip("-") or "step"
    candidate, n = base, 2
    while candidate in used:
        candidate, n = f"{base}-{n}", n + 1
    used.add(candidate)
    return candidate


def to_plan(draft: PlanDraft) -> Plan:
    """Normalise a model-written plan: safe ids, known dependencies only, bounded text.
    Raises ValueError if it is still not a valid DAG."""
    used: set[str] = set()
    ids = [_step_id(s.id, used) for s in draft.steps]  # one id per step, by position
    first: dict[str, str] = {}
    for raw, new in zip((s.id for s in draft.steps), ids, strict=True):
        first.setdefault(raw, new)  # a dependency names the first step with that id
    steps = []
    for s, new in zip(draft.steps, ids, strict=True):
        depends = []
        for d in s.depends_on:
            target = first.get(d)
            if target and target != new and target not in depends:
                depends.append(target)
        steps.append(
            Step(
                id=new,
                title=s.title.strip()[:120] or "Unnamed step",
                check=s.check.strip()[:500] or "The step produced a result.",
                depends_on=depends,
                model=WORKER_MODELS[0] if s.worker == "haiku" else WORKER_MODELS[1],
            )
        )
    return Plan(title=draft.title.strip()[:120] or "Plan", steps=steps)
