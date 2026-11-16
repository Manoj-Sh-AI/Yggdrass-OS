"""Shared deterministic agent steps; adapters own every external operation."""

from dataclasses import dataclass, field

from . import agent_skills, skill_registry
from .agent_tools import Proposal


@dataclass
class Effect:
    kind: str
    agent: str
    data: dict = field(default_factory=dict)
    turn: int = 0


def drive(steps, model, tools, lia=None, record=None):
    """Synchronous adapter retained for isolated role tests and legacy execution."""
    value, error = None, None
    while True:
        try:
            effect = steps.throw(error) if error else steps.send(value)
        except StopIteration as done:
            return done.value
        error = None
        try:
            if effect.kind == "model":
                selected = model.for_agent(effect.agent) if hasattr(model, "for_agent") else model
                data = dict(effect.data)
                chosen = data.pop("model", None)  # a per-step model (orchestration planner)
                if chosen and hasattr(selected, "with_model"):
                    selected = selected.with_model(chosen)
                value = selected.complete(**data)
                if record:
                    record(effect.agent, effect.turn, value)
            elif effect.kind == "read":
                value = tools.read(effect.agent, effect.data)
            elif effect.kind == "inspect":
                value = tools.inspect(Proposal.model_validate(effect.data))
            elif effect.kind == "skill":
                if effect.data.get("registry"):  # Yggdras's skill library (skill_registry.py)
                    value = skill_registry.registry().load(effect.data["name"])
                else:
                    value = agent_skills.load(effect.agent, effect.data)
            elif effect.kind == "tool":  # a gated tool (tool_gate.py), checked again by the host
                value = tools.call(effect.agent, effect.data)
            elif effect.kind == "lia":
                value = lia.ask(**effect.data)
            else:
                raise ValueError("Unknown agent operation.")
        except Exception as caught:  # noqa: BLE001 -- throw into the shared generator unchanged
            error = caught
