"""The three maps, rendered from the brain's rows into brain.map_cache.

Same pipe-row format as the markdown build (data/maps), byte for byte. Every query has a
total ORDER BY, so the same rows always give byte-identical text: Lia's prompt cache depends
on it. Lia reads the maps from map_cache, never from live queries.

map_version is a hash of the rendered text (rendered with its own version field blank, then
written into the header), so it changes when, and only when, the text changes.
"""

from __future__ import annotations

import datetime as dt
import hashlib
from dataclasses import dataclass

import yaml

from yggdras.data.graph import structural as st
from yggdras.data.maps.atlas import COLUMNS as ATLAS_COLUMNS
from yggdras.data.maps.atlas import REGISTRIES
from yggdras.data.maps.notes import NoteMeta, clean
from yggdras.data.maps.relations import relationship_map
from yggdras.data.maps.shelf import shelf_map

MAPS = ("atlas", "shelf", "relationships")
# `area: cross` is a real area in the database, 09-cross. The maps show it as today: the
# "## cross" section and the registries' cross-area count, never as an atlas row.
CROSS_CODE, CROSS_NAME = "09", "cross"


@dataclass
class RowNote(NoteMeta):
    """A note as the maps see it, built from rows instead of a file."""

    parent_slug: str = ""

    @property
    def parent(self) -> str:  # a chunk's source (notes.parent_slug)
        return self.parent_slug


def area_value(code: str, name: str) -> str:
    """The value a note's frontmatter holds for this area: `04-learning`, or `cross`."""
    return st.CROSS if code == CROSS_CODE else f"{code}-{name}"


def _iso(value) -> str:
    if value is None:
        return ""
    if isinstance(value, dt.datetime):
        return value.astimezone(dt.UTC).date().isoformat()
    return value.isoformat()


def _frontmatter(body: str) -> dict:
    parts = st._split(body)
    if parts is None:
        return {}
    try:
        return yaml.safe_load(parts[0]) or {}
    except yaml.YAMLError:
        return {}


def _has_history(body: str) -> bool:
    parts = st._split(body)
    if parts is None:
        return False
    return any(
        heading == st.HISTORY_HEADING and line.startswith("- ")
        for heading, _, line in st.sections(parts[1], parts[2])
    )


def _query(conn, sql: str) -> list[tuple]:
    with conn.cursor() as cur:
        cur.execute(sql)
        return cur.fetchall()


def load_rows(conn) -> tuple[list[tuple], dict[str, RowNote], list[dict]]:
    """(areas, notes by slug, link edges), each read with a total ORDER BY."""
    areas = _query(
        conn,
        "SELECT area_code, name, hub_slug, belongs_here, not_here FROM brain.areas "
        'ORDER BY sort_order, area_code COLLATE "C"',
    )
    names = {code: name for code, name, *_ in areas}
    aliases: dict[str, list[str]] = {}
    for alias, slug in _query(
        conn,
        'SELECT alias, slug FROM brain.aliases ORDER BY slug COLLATE "C", ord, alias COLLATE "C"',
    ):
        aliases.setdefault(slug, []).append(alias)
    also: dict[str, list[str]] = {}
    for slug, code in _query(
        conn,
        "SELECT slug, area_code FROM brain.note_areas WHERE NOT is_primary "
        'ORDER BY slug COLLATE "C", ord, area_code COLLATE "C"',
    ):
        also.setdefault(slug, []).append(area_value(code, names[code]))
    # Bodies are read here, while building the cache, for the two flags only the text holds
    # (pages, superseded facts). A shelf read never touches them.
    bodies = dict(
        _query(conn, 'SELECT slug, body FROM brain.note_bodies ORDER BY slug COLLATE "C"')
    )
    edges = [
        {"from_slug": a, "reason": verb, "to_slug": b, "kind": kind}
        for a, verb, b, kind in _query(
            conn,
            "SELECT from_slug, verb, to_slug, kind FROM brain.relationships "
            'ORDER BY from_slug COLLATE "C", verb COLLATE "C", to_slug COLLATE "C"',
        )
    ]
    notes: dict[str, RowNote] = {}
    for (
        slug, title, type_, code, parent, shelf_no, description, status, sensitivity, review,
        updated,
    ) in _query(
        conn,
        "SELECT slug, title, type, area_code, parent_slug, shelf_no, description, status, "
        "sensitivity, review_date, updated_at FROM brain.notes "
        'WHERE archived_at IS NULL ORDER BY slug COLLATE "C"',
    ):  # fmt: skip
        body = bodies.get(slug, "")
        notes[slug] = RowNote(
            slug=slug,
            name=title,
            type=type_,
            path=f"{shelf_no:02d}" if shelf_no is not None else "",
            area=area_value(code, names[code]),
            also=also.get(slug, []),
            description=description or "",
            aliases=aliases.get(slug, []),
            status=status or "",
            updated=_iso(updated),
            review=_iso(review),
            pages=str(_frontmatter(body).get("pages") or ""),
            sensitive=(sensitivity or "").lower() == "high",
            has_history=_has_history(body),
            parent_slug=parent or "",
        )
    return areas, notes, edges


def atlas(areas: list[tuple], notes: dict[str, RowNote], version: str) -> str:
    life = [a for a in areas if a[0] != CROSS_CODE]
    rows = [
        f"# atlas | areas {len(life)} | notes {len(notes)} | map_version {version}",
        ATLAS_COLUMNS,
    ]
    for code, name, hub_slug, holds, not_here in life:
        hub = notes.get(hub_slug) if hub_slug else None
        count = sum(1 for n in notes.values() if n.area == area_value(code, name))
        rows.append(
            "|".join(
                [
                    code,
                    name,
                    hub.slug if hub else "",
                    str(count),
                    clean(holds or ""),
                    clean(not_here or ""),
                    ", ".join(clean(a) for a in hub.aliases) if hub else "",
                ]
            )
        )
    shelves: dict[str, int] = {}
    for n in notes.values():
        shelves[n.path] = shelves.get(n.path, 0) + 1
    cross = sum(1 for n in notes.values() if n.area == st.CROSS)
    parts = [
        f"{name} {shelf[:2]} ({shelves.get(shelf[:2], 0)})" for shelf, name in REGISTRIES.items()
    ]
    rows.append("registries|" + " · ".join([*parts, f"cross-area ({cross})"]))
    return "\n".join(rows) + "\n"


def _render(areas, notes, edges, version: str) -> dict[str, str]:
    return {
        "atlas": atlas(areas, notes, version),
        "shelf": shelf_map(notes, version),
        "relationships": relationship_map({"edges": edges}, notes, version),
    }


def version_of(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def render_maps(conn) -> dict[str, tuple[str, str]]:
    """Each map's (text, map_version), from the rows as they are now."""
    areas, notes, edges = load_rows(conn)
    blank = _render(areas, notes, edges, "")
    out = {}
    for name in MAPS:
        version = version_of(blank[name])
        out[name] = (_render(areas, notes, edges, version)[name], version)
    return out


def build_cache(conn, now: dt.datetime | None = None) -> dict[str, str]:
    """Render the maps into brain.map_cache. A map whose text is unchanged keeps its row as it
    was (built_at included). Returns each map's version."""
    now = now or dt.datetime.now(dt.UTC)
    maps = render_maps(conn)
    with conn.cursor() as cur:
        for name, (text, version) in maps.items():
            cur.execute(
                "INSERT INTO brain.map_cache (map_name, rendered_text, map_version, built_at) "
                "VALUES (%s, %s, %s, %s) ON CONFLICT (map_name) DO UPDATE SET "
                "rendered_text = EXCLUDED.rendered_text, map_version = EXCLUDED.map_version, "
                "built_at = EXCLUDED.built_at "
                "WHERE brain.map_cache.map_version <> EXCLUDED.map_version",
                (name, text, version, now),
            )
    conn.commit()
    return {name: version for name, (_, version) in maps.items()}
