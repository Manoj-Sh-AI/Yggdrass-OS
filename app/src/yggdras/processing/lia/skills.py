"""Lia's skill library: a short core skill always loaded, an index of job playbooks in the
cached prompt, and the playbooks themselves, loaded on demand with `load_skill`.

The layout in the brain repo: `skills/lia/core.md`, then one playbook per job in
`skills/lia/library/<name>.md`, with frontmatter `name`, `description` (one line) and
`done_when` (a checklist Lia reports with `checklist` before she answers).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

CORE = "core"
MAX_LOAD = 2


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    body: str
    done_when: tuple[str, ...] = field(default_factory=tuple)


def parse(path: Path) -> Skill:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        raise ValueError(f"{path.name}: no frontmatter")
    _, fm, body = text.split("---", 2)
    meta = yaml.safe_load(fm) or {}
    name, description = str(meta.get("name", "")), str(meta.get("description", ""))
    if name != path.stem or not description or "\n" in description.strip():
        raise ValueError(f"{path.name}: needs name = file name and a one-line description")
    done = tuple(str(x) for x in meta.get("done_when") or ())
    if name != CORE and not done:
        raise ValueError(f"{path.name}: a playbook needs a done_when checklist")
    return Skill(name, description.strip(), body.strip(), done)


def load_library(folder: Path) -> dict[str, Skill]:
    """The core skill (*folder*/core.md) and every playbook in *folder*/library/, by name."""
    core = folder / f"{CORE}.md"
    if not core.is_file():
        raise FileNotFoundError(f"no {CORE}.md in {folder}")
    playbooks = [parse(p) for p in sorted((folder / "library").glob("*.md"))]
    if not playbooks:
        raise FileNotFoundError(f"no playbooks in {folder / 'library'}")
    return {CORE: parse(core), **{s.name: s for s in playbooks}}


def index(library: dict[str, Skill]) -> str:
    rows = [f"{s.name} | {s.description}" for n, s in sorted(library.items()) if n != CORE]
    return "<skill-index>\nname | use it for\n" + "\n".join(rows) + "\n</skill-index>"


def system_text(library: dict[str, Skill]) -> str:
    """What goes into the cached prompt: the core skill and the index, never the playbooks."""
    return f"{library[CORE].body}\n\n{index(library)}"


def full_text(library: dict[str, Skill]) -> str:
    """Core plus every playbook in one prompt: the baseline the token saving is measured against."""
    parts = [library[CORE].body] + [s.body for n, s in sorted(library.items()) if n != CORE]
    return "\n\n".join(parts)


def loaded_text(library: dict[str, Skill], names: list[str]) -> tuple[str, list[str]]:
    """The playbooks *names* (at most MAX_LOAD, unknown ones reported), each with its checklist."""
    out, done = [], []
    for name in list(dict.fromkeys(names))[:MAX_LOAD]:
        s = library.get(name)
        if s is None or name == CORE:
            out.append(f"=== {name}: no such skill (see the skill index)")
            continue
        done.append(name)
        checklist = "\n".join(f"- {item}" for item in s.done_when)
        out.append(f"=== skill {name}\n{s.body}\n\nDone when:\n{checklist}")
    if len(names) > MAX_LOAD:
        out.append(f"(only the first {MAX_LOAD} skills were loaded)")
    return "\n\n".join(out), done


LOAD_SKILL_TOOL = {
    "name": "load_skill",
    "description": (
        "Load one or two playbooks from the skill index that fit the job the question asks for. "
        "Call it in your first turn, in the same turn as your first open_notes call. Finish each "
        "loaded playbook's 'Done when' list and report it with checklist before you answer."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "names": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 2}
        },
        "required": ["names"],
        "additionalProperties": False,
    },
}
CHECKLIST_TOOL = {
    "name": "checklist",
    "description": (
        "Before you write the answer, report each loaded playbook's 'Done when' items: done or "
        "not, with a short note. Items not done must be finished first, or the answer must say "
        "what is missing."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "skill": {"type": "string"},
                        "item": {"type": "string"},
                        "done": {"type": "boolean"},
                        "note": {"type": "string"},
                    },
                    "required": ["skill", "item", "done"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["items"],
        "additionalProperties": False,
    },
}
CHECKLIST_NUDGE = (
    "Before you answer, call checklist with every 'Done when' item of the playbooks you loaded."
)


def checklist_reply(items: list[dict], loaded: list[str], library: dict[str, Skill], round_: int):
    """The reply to a checklist call, and whether it is complete. Missing or undone items get
    one more round; after that, the answer must say what is missing."""
    # Items are matched by count per playbook, so a reworded item still counts.
    undone = [x for x in items if not x.get("done")]
    missing = []
    for name in loaded:
        reported = sum(1 for x in items if x.get("skill") == name)
        missing += [(name, i) for i in library[name].done_when[reported:]]
    complete = not undone and not missing
    if complete:
        return "Checklist complete. Write the answer now.", True
    if round_ == 0:
        lines = [f"- {x['skill']}: {x['item']}" for x in undone]
        lines += [f"- {n}: {i} (not reported)" for n, i in missing]
        return (
            "Finish these first (search or open what you need), then call checklist again:\n"
            + "\n".join(lines),
            False,
        )
    return "Write the answer now, and say plainly what is still missing.", False
