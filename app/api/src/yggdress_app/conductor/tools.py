"""The tools a run's workers may call, with the metadata the safety layers need.

A tool declares its stakes: impact (does it change anything that matters?) and
reversibility (can it be undone?). Policy (policy.py) decides from that, plus hard deny
rules and Manoj's plain-English policy, whether a call runs, asks, or is refused.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

Impact = Literal["low", "high"]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]
    impact: Impact = "low"
    reversible: bool = True
    reads_notes: bool = False  # results may contain note text (sensitive filtering applies)
    run: Callable[[dict[str, Any]], Any] = field(default=lambda _: None, compare=False)
    # Stakes can depend on the call (removing vs creating): (impact, reversible).
    classify: Callable[[dict[str, Any]], tuple[str, bool]] | None = field(
        default=None, compare=False
    )

    def stakes_for(self, arguments: dict[str, Any]) -> str:
        impact, reversible = (
            self.classify(arguments) if self.classify else (self.impact, self.reversible)
        )
        return f"{impact}-{'reversible' if reversible else 'irreversible'}"

    def anthropic(self) -> dict[str, Any]:
        # Inputs are validated server-side (ReadQuery/Proposal) before anything runs.
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }


class Toolbox(Protocol):
    def specs(self) -> list[dict[str, Any]]: ...
    def get(self, name: str) -> ToolSpec | None: ...


class StaticToolbox:
    def __init__(self, tools: list[ToolSpec] | None = None):
        self._tools = {t.name: t for t in tools or []}

    def specs(self) -> list[dict[str, Any]]:
        return [t.anthropic() for t in self._tools.values()]

    def get(self, name: str) -> ToolSpec | None:
        return self._tools.get(name)
