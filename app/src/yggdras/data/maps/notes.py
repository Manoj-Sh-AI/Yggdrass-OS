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
# Where chunks live: the library's sources shelf, or a flat brain's sources folder.
SOURCE_SHELVES = ("13-sources", "sources")


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
        return parts[1] if len(parts) == 3 and parts[0] in SOURCE_SHELVES else ""


def _text(value) -> str:
    return "" if value is None else str(value)


def load_notes(root: Path, shelves: tuple[str, ...] | None) -> dict[str, NoteMeta]:
    """Every parseable note under the mapped shelves, by slug (first one wins on a clash).

    With *shelves* None, a flat brain (the Apollo demo): every note under *root*, and a
    note's top folder stands in for its area.
    """
    notes: dict[str, NoteMeta] = {}
    for path in st.node_files(root, shelves):
        rel = path.relative_to(root).as_posix()
        meta = meta_from_text(path.read_text(encoding="utf-8"), rel, library=shelves is not None)
        if meta is not None and meta.slug not in notes:
            notes[meta.slug] = meta
    return notes


def meta_from_text(text: str, rel: str, library: bool = True) -> NoteMeta | None:
    """One note's metadata from its text and its library path; None if it doesn't parse or
    has no slug. (The row store builds Lia's notes with this, from note_bodies.)"""
    parts = st._split(text)
    if parts is None:
        return None
    try:
        fm = yaml.safe_load(parts[0]) or {}
    except yaml.YAMLError:
        return None
    slug = _text(fm.get("slug"))
    if not slug:
        return None
    meta = NoteMeta(
        slug=slug,
        name=_text(fm.get("name")),
        type=_text(fm.get("type")),
        path=rel,
        area=(_text(fm.get("area")) or st.CROSS) if library else rel.split("/")[0],
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
    return meta


def map_version(root: Path, shelves: tuple[str, ...] | None) -> str:
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
