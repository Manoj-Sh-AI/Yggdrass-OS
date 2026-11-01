"""What the maps need from each note: frontmatter fields, summary, fact lines, history."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from yggdras.data.graph import structural as st

GENERATOR_VERSION = "yggdras-maps/1"
TAXONOMY = Path("00-manual") / "taxonomy.md"
SUMMARY_HEADING = "## Summary"


@dataclass
class NoteMeta:
    slug: str
    name: str
    type: str
    path: str
    area: str
    also: list[str]
    description: str
    aliases: list[str]
    status: str = ""
    updated: str = ""
    review: str = ""
    pages: str = ""
    sensitive: bool = False
    summary: str = ""
    facts: list[str] = field(default_factory=list)  # Facts and History lines, without "- "
    has_history: bool = False

    @property
    def parent(self) -> str:
        """The parent source of a chunk (13-sources/<parent>/<chunk>.md), else ""."""
        parts = self.path.split("/")
        return parts[1] if len(parts) == 3 and parts[0] == "13-sources" else ""


def _text(value) -> str:
    return "" if value is None else str(value)


def load_notes(root: Path, shelves: tuple[str, ...]) -> dict[str, NoteMeta]:
    """Every parseable note under the mapped shelves, by slug (first one wins on a clash)."""
    notes: dict[str, NoteMeta] = {}
    for path in st.node_files(root, shelves):
        parts = st._split(path.read_text(encoding="utf-8"))
        if parts is None:
            continue
        try:
            fm = yaml.safe_load(parts[0]) or {}
        except yaml.YAMLError:
            continue
        slug = _text(fm.get("slug"))
        if not slug or slug in notes:
            continue
        meta = NoteMeta(
            slug=slug,
            name=_text(fm.get("name")),
            type=_text(fm.get("type")),
            path=path.relative_to(root).as_posix(),
            area=_text(fm.get("area")) or st.CROSS,
            also=st._as_list(fm.get("also")),
            description=_text(fm.get("description")),
            aliases=st._as_list(fm.get("aliases")),
            status=_text(fm.get("status")),
            updated=_text(fm.get("updated")),
            review=_text(fm.get("review")),
            pages=_text(fm.get("pages")),
            sensitive=_text(fm.get("sensitivity")).lower() == "high",
        )
        summary = []
        for heading, _, line in st.sections(parts[1], parts[2]):
            if heading == SUMMARY_HEADING and line.strip():
                summary.append(line.strip())
            elif heading in (st.FACTS_HEADING, st.HISTORY_HEADING) and line.startswith("- "):
                meta.facts.append(line[2:].strip())
                meta.has_history |= heading == st.HISTORY_HEADING
        meta.summary = " ".join(summary)
        notes[slug] = meta
    return notes


def map_version(root: Path, shelves: tuple[str, ...]) -> str:
    """A hash of everything the maps are made from: same input, same version."""
    digest = hashlib.sha256(GENERATOR_VERSION.encode())
    for path in st.node_files(root, shelves):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(path.read_bytes())
    taxonomy = root / TAXONOMY
    if taxonomy.is_file():
        digest.update(taxonomy.read_bytes())
    return digest.hexdigest()[:12]


def clean(text: str) -> str:
    """One line, single spaces. Pipes are refused by the checker, never escaped here."""
    return " ".join(text.split())


def area_heading(area: str) -> str:
    if area == st.CROSS:
        return "## cross"
    code, _, name = area.partition("-")
    return f"## {code} {name}"


def area_order(area: str) -> tuple[bool, str]:
    return (area == st.CROSS, area)
