"""The run state: the one schema the conductor streams and the web app renders.

Everything a client shows comes from a RunState. The backend changes it only through
the event log (log.py), so a reconnecting client rebuilds exactly the same state.
"""

from __future__ import annotations

from typing import Any, Literal, get_args

from pydantic import BaseModel, ConfigDict, Field, model_validator

# What the conductor is doing this turn. A Plan card appearing above the reply is the
# visible moment it stops answering and starts orchestrating (brief B10).
Mode = Literal["answering", "planning", "executing"]

RunStatus = Literal["running", "waiting", "completed", "failed", "cancelled", "interrupted"]
TERMINAL: frozenset[str] = frozenset({"completed", "failed", "cancelled"})

# A step's lifecycle is the three-value Task schema [cited]. Whether it passed its
# verification point is a separate `verdict`, so a failed step needs no fourth status.
StepStatus = Literal["pending", "in_progress", "completed"]
Verdict = Literal["passed", "failed"]

# Exactly the seven tool-part states both shadcn's and assistant-ui's cards expect [cited].
ToolState = Literal[
    "input-streaming",
    "input-available",
    "approval-requested",
    "approval-responded",
    "output-available",
    "output-error",
    "output-denied",
]
TOOL_STATES: tuple[str, ...] = get_args(ToolState)

# Allowed forward moves. Anything else is a bug in the conductor, not a user error.
STEP_TRANSITIONS: dict[str, frozenset[str]] = {
    "pending": frozenset({"in_progress"}),
    # A failed verification sends the step back for another attempt.
    "in_progress": frozenset({"completed", "pending"}),
    "completed": frozenset(),
}
TOOL_TRANSITIONS: dict[str, frozenset[str]] = {
    "input-streaming": frozenset({"input-available", "output-error"}),
    "input-available": frozenset({"approval-requested", "output-available", "output-error"}),
    "approval-requested": frozenset({"approval-responded", "output-denied"}),
    "approval-responded": frozenset({"output-available", "output-error"}),
    "output-available": frozenset(),
    "output-error": frozenset(),
    "output-denied": frozenset(),
}

# The stakes matrix [cited brief]: impact x reversibility decides the gate.
Stakes = Literal["low-reversible", "low-irreversible", "high-reversible", "high-irreversible"]
Decider = Literal["rule", "classifier", "user"]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Step(_Model):
    id: str = Field(pattern=r"^[a-z0-9-]{1,40}$")
    # Action word + specific item + limits ("Verifying policy coverage for 2025"):
    # trust tracks specificity, not volume [cited].
    title: str = Field(min_length=1, max_length=120)
    status: StepStatus = "pending"
    depends_on: list[str] = Field(default_factory=list, max_length=10)
    # The step's verification point: what must be true for it to count as done.
    check: str = Field(min_length=1, max_length=500)
    verdict: Verdict | None = None
    reason: str = Field(default="", max_length=1000)
    attempts: int = Field(default=0, ge=0, le=3)
    model: str = ""
    result: str = Field(default="", max_length=20000)


class Plan(_Model):
    title: str = Field(min_length=1, max_length=120)
    steps: list[Step] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def _a_valid_dag(self) -> Plan:
        ids = [s.id for s in self.steps]
        if len(set(ids)) != len(ids):
            raise ValueError("Step ids must be unique.")
        known = set(ids)
        for step in self.steps:
            missing = set(step.depends_on) - known
            if missing:
                raise ValueError(f"Step {step.id} depends on unknown steps {sorted(missing)}.")
            if step.id in step.depends_on:
                raise ValueError(f"Step {step.id} depends on itself.")
        if cyclic(self.steps):
            raise ValueError("Step dependencies form a cycle.")
        return self

    def ready(self) -> list[Step]:
        """Pending steps whose dependencies have all completed and passed."""
        done = {s.id for s in self.steps if s.status == "completed" and s.verdict == "passed"}
        return [s for s in self.steps if s.status == "pending" and set(s.depends_on) <= done]


def cyclic(steps: list[Step]) -> bool:
    graph = {s.id: s.depends_on for s in steps}
    state: dict[str, int] = {}  # 1 visiting, 2 done

    def visit(node: str) -> bool:
        if state.get(node) == 1:
            return True
        if state.get(node) == 2:
            return False
        state[node] = 1
        if any(visit(n) for n in graph.get(node, [])):
            return True
        state[node] = 2
        return False

    return any(visit(n) for n in graph)


class ToolCall(_Model):
    id: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=80)
    state: ToolState = "input-streaming"
    step_id: str | None = None
    input: dict[str, Any] = Field(default_factory=dict)
    output: Any = None
    error: str = Field(default="", max_length=2000)
    stakes: Stakes | None = None
    # Who let it run (or stopped it): a hard rule, the auto-approval classifier, or Manoj.
    decided_by: Decider | None = None
    # What will happen, in plain words, shown before a high-stakes approval.
    intent: str = Field(default="", max_length=500)


class Usage(_Model):
    role: str
    model: str
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    cost_usd: float = Field(ge=0)


class RunState(_Model):
    run_id: str
    conversation_id: str | None = None
    status: RunStatus = "running"
    mode: Mode = "answering"
    plan: Plan | None = None
    tools: list[ToolCall] = Field(default_factory=list)
    reasoning: str = ""
    text: str = ""
    model: str = ""
    usage: list[Usage] = Field(default_factory=list)
    error: str = Field(default="", max_length=2000)

    def cost_usd(self) -> float:
        return round(sum(u.cost_usd for u in self.usage), 6)


def check_step_move(current: str, target: str) -> None:
    if target not in STEP_TRANSITIONS[current]:
        raise ValueError(f"A step cannot move from {current} to {target}.")


def check_tool_move(current: str, target: str) -> None:
    if target not in TOOL_TRANSITIONS[current]:
        raise ValueError(f"A tool call cannot move from {current} to {target}.")
