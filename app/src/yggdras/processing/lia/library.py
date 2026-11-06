"""Read-only view of one brain for Lia: notes, her maps (atlas and shelf map), the two tools.

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
MAX_K = 20
ABOUT_WORDS = 25  # descriptions in Lia's shelf map are cut to this many words (lia-v1 E5)


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

    def open_notes(self, slugs: list[str]) -> tuple[str, list[str]]:
        """Full text of up to MAX_OPEN notes in one call; unknown slugs are reported."""
        opened, parts = [], []
        for slug in list(dict.fromkeys(slugs))[:MAX_OPEN]:
            text = self._text.get(slug)
            if text is None:
                parts.append(f"=== {slug}: no such note (check the shelf map)")
                continue
            n = self.notes[slug]
            opened.append(slug)
            parts.append(f"=== {slug} ({n.path}) | updated {n.updated or '—'}\n{text.strip()}")
        if len(slugs) > MAX_OPEN:
            parts.append(f"(only the first {MAX_OPEN} slugs were opened)")
        return "\n\n".join(parts), opened

    @property
    def fact_index(self) -> search_mod.FactIndex:
        if self._fact_index is None:
            self._fact_index = search_mod.FactIndex(self.notes, self._text)
        return self._fact_index

    def search_notes(self, query: str, k: int = 10) -> str:
        """Ranked fact lines (and "about" rows) with their slugs: stemmed BM25 over every fact
        line, with the query expanded by the aliases of the notes it names."""
        return self.fact_index.search(query, max(1, min(k, MAX_K)))

    def candidates(self, words: list[str], exclude: set[str], k: int = 8) -> list[NoteMeta]:
        return search_mod.candidates(self.notes, words, exclude, k)

    def fact_lines(self, slug: str) -> list[str]:
        text = self._text.get(slug)
        return checks.note_fact_lines(text) if text else []
