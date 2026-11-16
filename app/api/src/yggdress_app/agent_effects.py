"""Shared deterministic agent steps; adapters own every external operation."""

from dataclasses import dataclass, field

from . import agent_skills
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
                value = selected.complete(**effect.data)
                if record:
                    record(effect.agent, effect.turn, value)
            elif effect.kind == "read":
                value = tools.read(effect.agent, effect.data)
            elif effect.kind == "inspect":
                value = tools.inspect(Proposal.model_validate(effect.data))
            elif effect.kind == "skill":
                value = agent_skills.load(effect.agent, effect.data)
            elif effect.kind == "lia":
                value = lia.ask(**effect.data)
            else:
                raise ValueError("Unknown agent operation.")
        except Exception as caught:  # noqa: BLE001 -- throw into the shared generator unchanged
            error = caught
