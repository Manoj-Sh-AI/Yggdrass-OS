"""Yggdras's skills: the know-how, one folder per skill with a SKILL.md.

The layout follows Lia's skill library (frontmatter `name` and `description`, body loaded on
demand by `load_skill`), plus `domains`: the tool domains the skill unlocks (tool_gate.py).

At startup the registry reads ONLY each file's frontmatter, line by line up to the closing
`---`; the body is never read until a task loads the skill, and then exactly once per
registry (cached). The registry is files on disk because skills are reviewed code: they ship
with the application, change through pull requests, and need no migration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

FOLDER = Path(__file__).parent / "agent_skills"
FENCE = "---"


class SkillError(ValueError):
    pass


@dataclass(frozen=True)
class SkillCard:
    """What Yggdras sees about a skill before loading it."""

    name: str
    description: str
    domains: tuple[str, ...]
    path: Path


def read_frontmatter(path: Path) -> dict:
    """The YAML between the two `---` fences, read line by line: the body is never read."""
    lines: list[str] = []
    with path.open("rb") as handle:
        first = handle.readline().decode("utf-8").strip()
        if first != FENCE:
            raise SkillError(f"{path.parent.name}: SKILL.md must start with frontmatter")
        for raw in handle:
            line = raw.decode("utf-8")
            if line.strip() == FENCE:
                break
            lines.append(line)
        else:
            raise SkillError(f"{path.parent.name}: frontmatter is not closed")
    return parse_fields(lines, path.parent.name)


def parse_fields(lines: list[str], where: str) -> dict:
    """`key: value` lines; a value in brackets is a list (`domains: [tasks, calendar]`)."""
    meta: dict = {}
    for line in lines:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, sep, value = line.partition(":")
        if not sep or not key.strip().isidentifier():
            raise SkillError(f"{where}: frontmatter line is not 'key: value': {line.strip()!r}")
        value = value.strip()
        if value.startswith("[") and value.endswith("]"):
            meta[key.strip()] = [
                v.strip().strip("'\"") for v in value[1:-1].split(",") if v.strip()
            ]
        else:
            meta[key.strip()] = value.strip("'\"")
    return meta


def scan(folder: Path = FOLDER) -> dict[str, SkillCard]:
    cards = {}
    for path in sorted(folder.glob("*/SKILL.md")):
        meta = read_frontmatter(path)
        name, description = str(meta.get("name", "")), str(meta.get("description", "")).strip()
        if name != path.parent.name:
            raise SkillError(f"{path.parent.name}: name must equal the folder name")
        if not description or "\n" in description:
            raise SkillError(f"{name}: needs a one-line description")
        domains = meta.get("domains") or []
        if not isinstance(domains, list) or not all(isinstance(d, str) for d in domains):
            raise SkillError(f"{name}: domains must be a list of names")
        cards[name] = SkillCard(name, description, tuple(domains), path)
    return cards


@dataclass
class SkillRegistry:
    folder: Path = FOLDER
    cards: dict[str, SkillCard] = field(init=False)
    loads: dict[str, int] = field(init=False, default_factory=dict)  # body reads, per skill
    _bodies: dict[str, str] = field(init=False, default_factory=dict)

    def __post_init__(self):
        self.cards = scan(self.folder)

    def index(self, names=None) -> str:
        """The skill index Yggdras gets at startup: names and descriptions only."""
        rows = [
            f"{c.name} | {c.description}"
            for n, c in sorted(self.cards.items())
            if names is None or n in names
        ]
        return "<skill-index>\nname | use it for\n" + "\n".join(rows) + "\n</skill-index>"

    def body(self, name: str) -> str:
        """The skill's instructions, read from disk the first time only."""
        card = self.cards.get(name)
        if card is None:
            raise SkillError(f"no skill '{name}' (see the skill index)")
        if name not in self._bodies:
            text = card.path.read_text(encoding="utf-8")
            self._bodies[name] = text.split(FENCE, 2)[2].strip()
            self.loads[name] = self.loads.get(name, 0) + 1
        return self._bodies[name]

    def domains(self, name: str) -> tuple[str, ...]:
        card = self.cards.get(name)
        if card is None:
            raise SkillError(f"no skill '{name}'")
        return card.domains

    def load(self, name: str) -> dict:
        """What a load_skill call returns: the instructions and the domains they unlock."""
        return {"name": name, "instructions": self.body(name), "unlocks": list(self.domains(name))}


_REGISTRY: SkillRegistry | None = None


def registry() -> SkillRegistry:
    """The process-wide registry, scanned once at first use (startup)."""
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = SkillRegistry()
    return _REGISTRY


LOAD_SKILL = {
    "name": "load_skill",
    "description": "Load a skill from the skill index when the task matches it. Loading a skill "
    "gives its instructions and unlocks the tools of its domains; no other tools exist.",
    "input_schema": {
        "type": "object",
        "properties": {"name": {"type": "string"}},
        "required": ["name"],
        "additionalProperties": False,
    },
}
