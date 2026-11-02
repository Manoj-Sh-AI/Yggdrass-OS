"""Read-only view of one brain: notes, maps (and their experiment variants), the two tools.

A library brain (the real one: `library/`) or a flat brain (the Apollo demo). Nothing here
writes a file.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from yggdras.data.graph import structural as st
from yggdras.data.maps import atlas as atlas_mod
from yggdras.data.maps import checks
from yggdras.data.maps import upcoming as upcoming_mod
from yggdras.data.maps.notes import NoteMeta, area_order, clean, load_notes, map_version
from yggdras.data.maps.relations import relationship_map
from yggdras.data.maps.shelf import shelf_map

MAX_OPEN = 10
MAX_K = 20
# L0 never fires on these: everyday words that are aliases somewhere but carry little
# meaning alone. Generic only (no personal data), per maps-design §8 (E3).
STOPLIST = frozenset(
    "work job bank visa thesis health money learning career german deutsch study studies "
    "home admin taxes salary skills ideas people places sources journal hobbies values "
    "purpose community relationships plan plans goal goals project projects notes brain "
    "resume cv apollo nasa moon".split()
)
WORD = re.compile(r"[a-z0-9äöüß]+")


@dataclass(frozen=True)
class MapOptions:
    """One experiment arm of the maps (maps-design §8). The default is the built template."""

    format: str = "pipe"  # pipe | json | prose  (E1)
    relationship: bool = True  # E2
    inverses: bool = True  # E4
    mentions: bool = True
    about_words: int | None = None  # E5: cut descriptions to this many words


def _cut(text: str, words: int | None) -> str:
    if not words:
        return text
    parts = clean(text).split()
    return " ".join(parts[:words])


def _tokens(text: str) -> list[str]:
    return WORD.findall(text.lower())


@dataclass
class Library:
    root: Path
    flat: bool = False
    notes: dict[str, NoteMeta] = field(init=False)
    graph: dict = field(init=False)

    def __post_init__(self):
        shelves = None if self.flat else st.mapped_shelves()
        self.shelves = shelves
        self.notes = load_notes(self.root, shelves)
        self.graph = st.build_map(self.root, shelves)
        self.version = map_version(self.root, shelves)
        self._text = {
            s: (self.root / n.path).read_text(encoding="utf-8") for s, n in self.notes.items()
        }
        self._index = {s: Counter(_tokens(self._doc(s))) for s in self.notes}
        self._avg = sum(sum(c.values()) for c in self._index.values()) / max(len(self._index), 1)

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

    def maps(self, options: MapOptions | None = None) -> dict[str, str]:
        options = options or MapOptions()
        notes = {
            s: NoteMeta(**{**n.__dict__, "description": _cut(n.description, options.about_words)})
            for s, n in self.notes.items()
        }
        graph = self.graph
        atlas = self._atlas(notes)
        shelf = shelf_map(notes, self.version)
        out = {"atlas.md": atlas, "shelf-map.md": shelf}
        if options.relationship:
            out["relationship-map.md"] = relationship_map(
                graph,
                notes,
                self.version,
                inverses=options.inverses,
                mentions=options.mentions,
                free_verbs=self.flat,
            )
        if options.format == "json":
            out = {k.replace(".md", ".json"): _to_json(v) for k, v in out.items()}
        elif options.format == "prose":
            out = {k: _to_prose(v) for k, v in out.items()}
        return out

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

    # ---------------------------------------------------------------- tools

    def note_text(self, slug: str) -> str | None:
        return self._text.get(slug)

    def open_notes(self, slugs: list[str], neighbours: bool = False) -> tuple[str, list[str]]:
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
            if neighbours:
                parts.append(self._neighbours(slug))
        if len(slugs) > MAX_OPEN:
            parts.append(f"(only the first {MAX_OPEN} slugs were opened)")
        return "\n\n".join(parts), opened

    def _neighbours(self, slug: str) -> str:
        rows = []
        for e in self.graph["edges"]:
            if e["kind"] == "hub":
                continue
            if e["from_slug"] == slug:
                other, verb = e["to_slug"], e["reason"]
            elif e["to_slug"] == slug:
                other, verb = e["from_slug"], f"←{e['reason']}"
            else:
                continue
            n = self.notes.get(other)
            if n and other != slug:
                rows.append(f"{verb} {other} | {n.type} | {clean(n.description)}")
        body = "\n".join(sorted(set(rows))) or "(none)"
        return f"--- neighbours of {slug} (1 hop, descriptions only)\n{body}"

    def _doc(self, slug: str) -> str:
        n = self.notes[slug]
        return " ".join(
            [n.slug.replace("-", " "), n.name, " ".join(n.aliases), n.description, self._text[slug]]
        )

    def search_notes(self, query: str, k: int = 10) -> str:
        """BM25 over title, aliases, description and note text; one ranked list with snippets."""
        k = max(1, min(k, MAX_K))
        terms = _tokens(query)
        n_docs = len(self._index)
        scores = {}
        for slug, counts in self._index.items():
            length = sum(counts.values())
            score = 0.0
            for t in set(terms):
                df = sum(1 for c in self._index.values() if t in c)
                if not df or not counts[t]:
                    continue
                idf = math.log(1 + (n_docs - df + 0.5) / (df + 0.5))
                tf = counts[t]
                score += idf * tf * 2.2 / (tf + 1.2 * (0.25 + 0.75 * length / self._avg))
            if score > 0:
                scores[slug] = score
        ranked = sorted(scores, key=lambda s: (-scores[s], s))[:k]
        if not ranked:
            return "No matches."
        out = []
        for slug in ranked:
            out.append(f"{slug} | {round(scores[slug], 2)} | {self._snippet(slug, terms)}")
        return "\n".join(out)

    def _snippet(self, slug: str, terms: list[str]) -> str:
        for line in self._text[slug].splitlines():
            if any(t in line.lower() for t in terms) and not line.startswith(("id:", "slug:")):
                return clean(line)[:160]
        return clean(self.notes[slug].description)[:160]

    # ---------------------------------------------------------------- L0 pre-pass (E3)

    def l0_matches(self, question: str) -> list[str]:
        """Notes whose name or alias appears in the question, when that name or alias belongs to
        exactly one note and is not on the stoplist."""
        owners: dict[str, set[str]] = {}
        for slug, n in self.notes.items():
            for name in (n.name, *n.aliases):
                key = " ".join(_tokens(name))
                if key:
                    owners.setdefault(key, set()).add(slug)
        q = " " + " ".join(_tokens(question)) + " "
        found = []
        for key, slugs in owners.items():
            if len(slugs) != 1 or key in STOPLIST or len(key) < 3:
                continue
            if f" {key} " in q:
                found.append(next(iter(slugs)))
        return sorted(set(found))

    def upcoming(self, today, days: int = upcoming_mod.HORIZON_DAYS) -> str:
        """The upcoming view (F6): dated items from *today* on, one row each, no fact text."""
        return upcoming_mod.upcoming(self.notes, self._text, today, days)

    def fact_lines(self, slug: str) -> list[str]:
        text = self._text.get(slug)
        return checks.note_fact_lines(text) if text else []


def _to_json(text: str) -> str:
    """Pipe rows to JSON: each table becomes a list of objects; incident lines a mapping."""
    lines = [line for line in text.splitlines() if line and not line.startswith("# ")]
    header, rows, section = None, [], None
    incident = {}
    for line in lines:
        if line.startswith("## "):
            section = line[3:]
            continue
        if "|" in line:
            cells = line.split("|")
            if header is None:
                header = cells
                continue
            rows.append(
                {
                    **({"section": section} if section else {}),
                    **dict(zip(header, cells, strict=False)),
                }
            )
        elif ": " in line:
            key, _, value = line.partition(": ")
            incident[key] = value.split(" · ")
    return json.dumps(rows if rows else incident, ensure_ascii=False, separators=(",", ":")) + "\n"


def _to_prose(text: str) -> str:
    """Pipe rows to sentences, one per row."""
    out, header = [], None
    for line in text.splitlines():
        if not line or line.startswith("# "):
            continue
        if line.startswith("## "):
            out.append(f"\nIn {line[3:]}:")
            continue
        if "|" in line:
            cells = line.split("|")
            if header is None:
                header = cells
                continue
            pairs = [
                f"{h} {c}" for h, c in zip(header[1:], cells[1:], strict=False) if c and c != "—"
            ]
            out.append(f"{cells[0]} has " + ", ".join(pairs) + ".")
        elif ": " in line:
            key, _, value = line.partition(": ")
            out.append(f"{key} links: " + ", ".join(value.split(" · ")) + ".")
    return "\n".join(out).strip() + "\n"
