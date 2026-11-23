"""The effects the orchestration pipeline needs, carried out in-process for one run.

The host is the second half of the tool gate: it serves `skill` loads itself, so it knows
which domains this run unlocked, and it refuses a `tool` effect whose domain is still locked,
even if a generator (or a forged effect) asks for it. Risky actions arrive as `propose` and
become cards; they never reach `call`.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from .skill_registry import SkillRegistry
from .tool_gate import ToolLocked, ToolRegistry


@dataclass
class Host:
    skills: SkillRegistry
    tools: ToolRegistry
    handlers: dict[str, Callable[[dict], object]] = field(default_factory=dict)  # tool → fn
    on_card: Callable[[dict], dict] | None = None
    on_record: Callable[[dict], None] | None = None
    lessons: Callable[[str], list[str]] | None = None
    unlocked: set[str] = field(default_factory=set)
    ran: list[str] = field(default_factory=list)
    cards: list[dict] = field(default_factory=list)
    runs: list[dict] = field(default_factory=list)

    # the effect methods agent_effects.drive calls

    def load(self, name: str) -> dict:
        data = self.skills.load(name)
        self.unlocked |= set(data["unlocks"])
        return data

    def call(self, agent: str, data: dict):
        tool = self.tools.tools.get(data.get("name", ""))
        if tool is None or tool.domain not in self.unlocked:
            raise ToolLocked(f"'{data.get('name')}' is not unlocked in this run")
        if tool.risks:  # risky tools only ever run after approval, never from a run
            raise ToolLocked(f"'{tool.name}' needs Manoj's approval; it was not run")
        handler = self.handlers.get(tool.name)
        if handler is None:
            raise ToolLocked(f"'{tool.name}' is not connected yet")
        self.ran.append(tool.name)
        return handler(data.get("input") or {})

    def propose(self, agent: str, data: dict) -> dict:
        card = {"id": f"card-{len(self.cards) + 1}", "agent": agent, **data, "state": "waiting"}
        if self.on_card:
            card = self.on_card(card)
        self.cards.append(card)
        return card

    def recall(self, agent: str, data: dict) -> list[str]:
        return self.lessons(data.get("source", "")) if self.lessons else []

    def record(self, agent: str, data: dict) -> dict:
        self.runs.append(data)
        if self.on_record:
            self.on_record(data)
        return {"recorded": True}

    def read(self, agent, data):
        raise ToolLocked("reads go through gated tools")

    def inspect(self, proposal):
        return {"ok": True}
