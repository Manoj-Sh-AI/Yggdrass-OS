"""What the app reads from the brain (D44, brain side only): the note tree, one note with its
relationships, and the version token a write must carry.

Read-only queries over the live notes (archived_at is null). A write goes through
RowStore.write_note with the version the reader was given; a stale one is refused.
"""

from __future__ import annotations

from yggdras.data.brain_db import render

LIVE = "n.archived_at IS NULL"


def _rows(conn, sql: str, args=()) -> list[tuple]:
    with conn.cursor() as cur:
        cur.execute(sql, args)
        return cur.fetchall()


def note_tree(conn) -> list[dict]:
    """Shelves for the sidebar: each area (09 is `cross`) with its notes, primary area only,
    in map order (area, then slug)."""
    areas = _rows(
        conn, 'SELECT area_code, name FROM brain.areas ORDER BY sort_order, area_code COLLATE "C"'
    )
    notes = _rows(
        conn,
        "SELECT n.area_code, n.slug, n.title, n.type, n.shelf_no, n.parent_slug, n.version "
        f'FROM brain.notes n WHERE {LIVE} ORDER BY n.area_code, n.slug COLLATE "C"',
    )
    by_area: dict[str, list[dict]] = {}
    for code, slug, title, type_, shelf, parent, version in notes:
        by_area.setdefault(code, []).append(
            dict(slug=slug, title=title, type=type_, shelf=shelf, parent=parent, version=version)
        )
    return [
        dict(code=code, name=render.area_value(code, name), notes=by_area.get(code, []))
        for code, name in areas
    ]


def note_with_relationships(conn, slug: str) -> dict | None:
    """One live note: its catalogue row, its text, its version, and its links: outgoing,
    incoming (the reverse is a query on to_slug, D31) and mentions both ways."""
    row = _rows(
        conn,
        "SELECT n.slug, n.title, n.type, n.area_code, n.description, n.status, n.version, "
        f"b.body FROM brain.notes n JOIN brain.note_bodies b ON b.slug = n.slug "
        f"WHERE n.slug = %s AND {LIVE}",
        (slug,),
    )
    if not row:
        return None
    s, title, type_, area, description, status, version, body = row[0]
    areas = [
        code
        for (code,) in _rows(
            conn, "SELECT area_code FROM brain.note_areas WHERE slug = %s ORDER BY ord", (slug,)
        )
    ]
    links = _rows(
        conn,
        "SELECT r.from_slug, r.verb, v.inverse, r.to_slug, r.kind FROM brain.relationships r "
        "JOIN brain.verbs v ON v.verb = r.verb "
        "JOIN brain.notes a ON a.slug = r.from_slug JOIN brain.notes b ON b.slug = r.to_slug "
        "WHERE (r.from_slug = %s OR r.to_slug = %s) "
        "AND a.archived_at IS NULL AND b.archived_at IS NULL "
        'ORDER BY r.kind, r.verb, r.from_slug COLLATE "C", r.to_slug COLLATE "C"',
        (slug, slug),
    )
    out = dict(
        slug=s, title=title, type=type_, area=area, areas=areas, description=description,
        status=status, version=version, body=body, outgoing=[], incoming=[], mentions=[],
        mentioned_in=[],
    )  # fmt: skip
    for a, verb, inverse, b, kind in links:
        if kind == "mention":
            (out["mentions"] if a == slug else out["mentioned_in"]).append(b if a == slug else a)
        elif a == slug:
            out["outgoing"].append(dict(verb=verb, to=b, kind=kind))
        else:
            out["incoming"].append(dict(verb=inverse, from_=a, kind=kind))
    return out


def version(conn, slug: str) -> int | None:
    """The version token of one live note: given on read, required on write."""
    row = _rows(conn, f"SELECT n.version FROM brain.notes n WHERE n.slug = %s AND {LIVE}", (slug,))
    return row[0][0] if row else None
