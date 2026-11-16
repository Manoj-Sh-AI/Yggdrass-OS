"""Tools, the hands, behind a real gate: progressive disclosure by skill domain.

Every tool belongs to one domain (tasks, calendar, brain, email, or a connector's). A request
gets a Toolbelt that starts with every domain locked. Loading a skill unlocks exactly the
domains its SKILL.md names; nothing else does. The gate is enforced where tools are CALLED,
not in the prompt:

- `Toolbelt.schemas()` offers the model only unlocked tools (it can't see the others), and
- `Toolbelt.require(name)` raises ToolLocked for any tool whose domain is still locked, so a
  model that names a hidden tool anyway is refused before any effect runs.

The worker/Temporal activity checks again, against the run's own completed skill loads
(`unlocked_domains`), so a forged effect can't reach a tool either.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .skill_registry import LOAD_SKILL, SkillRegistry

# What makes an action risky (orchestration.Checker): it waits for Manoj's approval.
WRITE = "writes outside the brain's add path"
SEND = "sends a message"
SPEND = "spends money"
DELETE = "deletes"
SENSITIVE = "touches a sensitive note"
RISKS = (WRITE, SEND, SPEND, DELETE, SENSITIVE)


class ToolLocked(PermissionError):
    pass


@dataclass(frozen=True)
class Tool:
    name: str
    domain: str
    description: str
    input_schema: dict
    risks: frozenset = frozenset()  # subset of RISKS; empty: reads and brain adds

    def schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }


@dataclass
class ToolRegistry:
    tools: dict[str, Tool] = field(default_factory=dict)

    def register(self, tool: Tool) -> None:
        if tool.name in self.tools or tool.name == LOAD_SKILL["name"]:
            raise ValueError(f"tool {tool.name} is registered already")
        if not set(tool.risks) <= set(RISKS):
            raise ValueError(f"{tool.name}: unknown risk")
        self.tools[tool.name] = tool

    def unregister_domain(self, domain: str) -> None:
        for name in [n for n, t in self.tools.items() if t.domain == domain]:
            del self.tools[name]

    def in_domains(self, domains) -> list[Tool]:
        return [t for _, t in sorted(self.tools.items()) if t.domain in domains]


@dataclass
class Toolbelt:
    """One request's (or one sub-agent's) hands: locked until a skill opens a domain."""

    tools: ToolRegistry
    skills: SkillRegistry
    unlocked: set[str] = field(default_factory=set)
    loaded: list[str] = field(default_factory=list)

    def load_skill(self, name: str) -> dict:
        data = self.skills.load(name)
        self.unlocked |= set(data["unlocks"])
        if name not in self.loaded:
            self.loaded.append(name)
        return data

    def open(self, loaded: dict) -> None:
        """Unlock from a load_skill result produced by an effect (worker or Temporal)."""
        self.unlocked |= set(loaded.get("unlocks", []))
        if loaded.get("name") and loaded["name"] not in self.loaded:
            self.loaded.append(loaded["name"])

    def schemas(self) -> list[dict]:
        return [LOAD_SKILL, *(t.schema() for t in self.tools.in_domains(self.unlocked))]

    def require(self, name: str) -> Tool:
        tool = self.tools.tools.get(name)
        if tool is None:
            raise ToolLocked(f"there is no tool '{name}'")
        if tool.domain not in self.unlocked:
            raise ToolLocked(f"'{name}' is locked: load a skill in the {tool.domain} domain first")
        return tool


def unlocked_domains(skill_results: list[dict]) -> set[str]:
    """The domains a run's completed load_skill effects opened (the activity-side gate)."""
    out: set[str] = set()
    for result in skill_results:
        out |= set((result or {}).get("unlocks", []))
    return out


def _schema(properties: dict, required: list[str]) -> dict:
    return {"type": "object", "properties": properties, "required": required,
            "additionalProperties": False}  # fmt: skip


TEXT = {"type": "string", "minLength": 1, "maxLength": 8000}


def default_registry() -> ToolRegistry:
    """The built-in tools, by domain. Writes are proposals: nothing here saves on its own."""
    reg = ToolRegistry()
    for tool in (
        Tool("read_tasks", "tasks", "Read current tasks, goals and their versions.",
             _schema({"query": TEXT}, ["query"])),
        Tool("propose_task_change", "tasks", "Propose one task change for Manoj's review. "
             "It is not saved until he approves.", _schema({"request": TEXT}, ["request"]),
             frozenset({WRITE})),
        Tool("read_calendar", "calendar", "Read calendar events and free time for a date range.",
             _schema({"query": TEXT}, ["query"])),
        Tool("propose_calendar_change", "calendar", "Propose one calendar change for review. "
             "It is not saved until Manoj approves.", _schema({"request": TEXT}, ["request"]),
             frozenset({WRITE})),
        Tool("search_brain", "brain", "Search Manoj's brain (Lia's notes) for facts. Read-only.",
             _schema({"query": TEXT}, ["query"])),
        Tool("offer_brain_fact", "brain", "Offer one new fact for a brain note, as a card Manoj "
             "approves. Adding is the brain's add path: written at once on approval, with Undo.",
             _schema({"slug": TEXT, "fact": TEXT}, ["slug", "fact"])),
        Tool("propose_brain_change", "brain", "Propose replacing or removing a brain fact. Shows "
             "a preview; nothing changes before Confirm.",
             _schema({"slug": TEXT, "old_line": TEXT, "new_line": {"type": "string"}},
                     ["slug", "old_line"]), frozenset({WRITE, DELETE})),
        Tool("draft_email", "email", "Draft an email (nothing is sent).",
             _schema({"to": TEXT, "subject": TEXT, "body": TEXT}, ["to", "subject", "body"])),
        Tool("send_email", "email", "Send an email. Always waits for Manoj's approval on a card.",
             _schema({"to": TEXT, "subject": TEXT, "body": TEXT}, ["to", "subject", "body"]),
             frozenset({SEND})),
    ):  # fmt: skip
        reg.register(tool)
    return reg
