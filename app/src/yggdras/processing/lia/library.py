"""Read-only view of one brain for Lia: notes, her maps (atlas and shelf map), the two tools.

Both tools return notes as `search_result` content blocks with citations enabled (D35): one
search result per note (source = slug, title = the note's name), one text block per line, so
Claude cites lines by pointer and code renders the footnote from the cited block.

A library brain (the real one: `library/`) or a flat brain (the Apollo demo). Nothing here
writes a file.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from yggdras.data.graph import structural as st
from yggdras.data.maps import atlas as atlas_mod
from yggdras.data.maps import checks
from yggdras.data.maps import upcoming as upcoming_mod
from yggdras.data.maps.notes import NoteMeta, area_order, clean, load_notes, map_version
from yggdras.data.maps.shelf import shelf_map
from yggdras.processing.lia import search as search_mod

MAX_OPEN = 10
SKIP_FIELDS = frozenset({"id", "slug"})  # frontmatter that is no fact about anything
MAX_K = 20
ABOUT_WORDS = 25  # descriptions in Lia's shelf map are cut to this many words (lia-v1 E5)


@dataclass(frozen=True)
class Block:
    """One citable line of a note: *kind* is field, fact, history or text; *shown* is what Lia
    reads; footnote() renders what a citation of it shows."""

    kind: str
    shown: str

    def footnote(self, slug: str) -> str:
        if self.kind == "field":
            return f"[[{slug}]] {self.shown}"
        if self.kind == "fact":
            return f"[[{slug}]] «{checks.quote_unit(self.shown)}»"
        if self.kind == "history":
            line = self.shown.removeprefix("History: ")
            return f"[[{slug}]] «{checks.quote_unit(line)}» (history)"
        return f"[[{slug}]] «{self.shown}»"


def note_blocks(text: str) -> list[Block]:
    """A note as citable lines: its scalar frontmatter fields ("review: 2030-03-01"), then every
    body line: Facts lines as they are, History lines marked "History:", other sections'
    lines prefixed with their heading ("Next action: …")."""
    parts = st._split(text)
    if parts is None:
        return [Block("text", line) for line in text.splitlines() if line.strip()]
    blocks = [
        Block("field", f"{name}: {value}")
        for name, value in checks.note_fields(text).items()
        if name not in SKIP_FIELDS
    ]
    for heading, _, line in st.sections(parts[1], parts[2]):
        body = line.strip()
        if not body or heading is None:
            continue
        item = body.removeprefix("- ")
        if heading == st.FACTS_HEADING and body.startswith("- "):
            blocks.append(Block("fact", item))
        elif heading == st.HISTORY_HEADING and body.startswith("- "):
            blocks.append(Block("history", f"History: {item}"))
        else:
            blocks.append(Block("text", f"{heading.removeprefix('## ')}: {item}"))
    return blocks


def search_result(slug: str, title: str, blocks: list[Block]) -> dict:
    return {
        "type": "search_result",
        "source": slug,
        "title": title,
        "content": [{"type": "text", "text": b.shown} for b in blocks],
        "citations": {"enabled": True},
    }


def _cut(text: str, words: int) -> str:
    return " ".join(clean(text).split()[:words])


@dataclass
class Library:
    root: Path
    flat: bool = False
    notes: dict[str, NoteMeta] = field(init=False)

    def __post_init__(self):
        shelves = None if self.flat else st.mapped_shelves()
        self.notes = load_notes(self.root, shelves)
        self.version = map_version(self.root, shelves)
        self._text = {
            s: (self.root / n.path).read_text(encoding="utf-8") for s, n in self.notes.items()
        }
        self._fact_index = None

    # ---------------------------------------------------------------- manual and maps

    def manual(self) -> str:
        """The taxonomy and node template a library brain carries; a short folder list for flat."""
        if not self.flat:
            parts = [
                (self.root / "00-manual" / f).read_text(encoding="utf-8")
                for f in ("taxonomy.md", "node.md")
            ]
            return "\n\n".join(parts)
        folders = sorted({n.area for n in self.notes.values()})
        return (
            "# This brain\n\nA flat demo brain. Folders: " + ", ".join(folders) + ".\n"
            "Each note: frontmatter (slug, name, type, description, aliases), ## Facts with one "
            "fact per line and its (src: ...), and ## Links with free-text verbs."
        )

    def maps(self) -> dict[str, str]:
        """Lia's maps: the atlas and the shelf map, descriptions cut to ABOUT_WORDS. (The
        relationship map is still built for the viewer, but Lia doesn't load it: lia-v1 E2.)"""
        notes = {
            s: NoteMeta(**{**n.__dict__, "description": _cut(n.description, ABOUT_WORDS)})
            for s, n in self.notes.items()
        }
        return {"atlas.md": self._atlas(notes), "shelf-map.md": shelf_map(notes, self.version)}

    def _atlas(self, notes: dict[str, NoteMeta]) -> str:
        if not self.flat:
            taxonomy = (self.root / "00-manual" / "taxonomy.md").read_text(encoding="utf-8")
            return atlas_mod.atlas(notes, taxonomy, self.version)
        rows = [
            f"# atlas | folders | notes {len(notes)} | map_version {self.version}",
            "folder|notes",
        ]
        for area in sorted({n.area for n in notes.values()}, key=area_order):
            rows.append(f"{area}|{sum(1 for n in notes.values() if n.area == area)}")
        return "\n".join(rows) + "\n"

    def upcoming(self, today, days: int = upcoming_mod.HORIZON_DAYS) -> str:
        """The upcoming view: dated items from *today* on, one row each, no fact text."""
        return upcoming_mod.upcoming(self.notes, self._text, today, days)

    # ---------------------------------------------------------------- tools

    def note_text(self, slug: str) -> str | None:
        return self._text.get(slug)

    def blocks(self, slug: str) -> list[Block]:
        text = self._text.get(slug)
        return note_blocks(text) if text else []

    def open_notes(
        self, slugs: list[str]
    ) -> tuple[list[dict], list[tuple[str, list[Block]]], list[str]]:
        """Up to MAX_OPEN notes in one call, each as a search_result block (every line of the
        note). Returns the search results, their (slug, blocks) in order, and the notices
        (unknown slugs, the cap) as plain lines. A tool result may not mix search_result and text
        blocks, so the caller sends the notices beside it, never inside."""
        content, results, notices = [], [], []
        for slug in list(dict.fromkeys(slugs))[:MAX_OPEN]:
            if slug not in self._text:
                notices.append(f"{slug}: no such note (check the shelf map)")
                continue
            blocks = self.blocks(slug)
            content.append(search_result(slug, self.notes[slug].name, blocks))
            results.append((slug, blocks))
        if len(slugs) > MAX_OPEN:
            notices.append(f"(only the first {MAX_OPEN} slugs were opened)")
        return content, results, notices

    @property
    def fact_index(self) -> search_mod.FactIndex:
        if self._fact_index is None:
            self._fact_index = search_mod.FactIndex(self.notes, self._text)
        return self._fact_index

    def search_notes(
        self, query: str, k: int = 10
    ) -> tuple[list[dict], list[tuple[str, list[Block]]]]:
        """The top *k* matching lines (stemmed BM25 over every fact line and each note's "about"
        row, the query expanded by the aliases of the notes it names), grouped by note in rank
        order, each note as a search_result block of its matching lines."""
        units = self.fact_index.ranked(query, max(1, min(k, MAX_K)))
        if not units:
            return [{"type": "text", "text": "No matches."}], []
        grouped: dict[str, list[Block]] = {}
        for u in units:
            text = u.text if u.kind != "about" else f"About: {u.text}"
            kind = {"fact": "fact", "history": "history", "about": "text"}[u.kind]
            shown = f"History: {text}" if kind == "history" else text
            grouped.setdefault(u.slug, []).append(Block(kind, shown))
        results = list(grouped.items())
        content = [search_result(s, self.notes[s].name, b) for s, b in results]
        return content, results

    def candidates(self, words: list[str], exclude: set[str], k: int = 8) -> list[NoteMeta]:
        return search_mod.candidates(self.notes, words, exclude, k)

    def fact_lines(self, slug: str) -> list[str]:
        text = self._text.get(slug)
        return checks.note_fact_lines(text) if text else []
