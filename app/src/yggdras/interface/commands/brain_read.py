"""`yggdras brain tree|note|version|search` (planning/cli-build-spec.md).

Reads only the api.brain_* views and api.brain_note_access() (brain migration 0005), so the
sensitivity rule is applied once, in SQL. A restricted slug exits 4; a missing one exits 3."""

from __future__ import annotations

from .contract import CliError, Out


def _connect():
    from yggdras.data.brain_db import db

    return db.connect()


def _rows(sql: str, args: tuple = ()) -> list[dict]:
    with _connect() as conn:
        cur = conn.execute(sql, args)
        names = [c.name for c in cur.description]
        return [dict(zip(names, row, strict=True)) for row in cur.fetchall()]


def check_access(conn, slug: str) -> None:
    """Exit 4 for a restricted note and 3 for a missing one (api.brain_note_access)."""
    verdict = conn.execute("SELECT api.brain_note_access(%s)", (slug,)).fetchone()[0]
    if verdict is None:
        raise CliError("not_found", f"no live note '{slug}'")
    if verdict != "normal":
        raise CliError("not_allowed", "that note is restricted")


def _one(slug: str, sql: str) -> dict:
    with _connect() as conn:
        check_access(conn, slug)
        cur = conn.execute(sql, (slug,))
        names = [c.name for c in cur.description]
        row = cur.fetchone()
    if row is None:
        raise CliError("not_found", f"no live note '{slug}'")
    return dict(zip(names, row, strict=True))


def tree(args) -> Out:
    rows = _rows(
        "SELECT slug, title, type, area_code, shelf_no, parent_slug, version, sensitivity "
        "FROM api.brain_notes ORDER BY area_code, shelf_no NULLS LAST, slug NULLS LAST"
    )
    lines = [(r["area_code"], r["shelf_no"], r["slug"], r["type"], r["title"], r["version"])
             for r in rows]  # fmt: skip
    return Out(rows, lines)


def note(args) -> Out:
    row = _one(
        args.slug,
        "SELECT slug, title, type, area_code, description, status, version, body "
        "FROM api.brain_note_bodies WHERE slug = %s",
    )
    links = _rows(
        "SELECT from_slug, verb, inverse, to_slug, kind FROM api.brain_links "
        "WHERE from_slug = %s OR to_slug = %s ORDER BY from_slug, verb, to_slug",
        (args.slug, args.slug),
    )
    data = {**row, "links": links}
    lines = [(row["slug"], row["version"], row["title"], row["type"], row["area_code"]),
             (row["body"],)]  # fmt: skip
    lines += [("link", r["from_slug"], r["verb"], r["to_slug"], r["kind"]) for r in links]
    return Out(data, lines)


def version(args) -> Out:
    row = _one(args.slug, "SELECT slug, version FROM api.brain_notes WHERE slug = %s")
    return Out(row, [(row["slug"], row["version"])])


def search(args) -> Out:
    rows = _rows(
        "SELECT slug, title, type, area_code, version, "
        "ts_rank(document, plainto_tsquery('simple', %s)) AS rank FROM api.brain_search "
        "WHERE document @@ plainto_tsquery('simple', %s) ORDER BY rank DESC, slug LIMIT %s",
        (args.q, args.q, args.limit),
    )
    for r in rows:
        r["rank"] = round(float(r["rank"]), 4)
    return Out(rows, [(r["slug"], r["title"], r["type"], r["version"]) for r in rows])


def register(verbs, common) -> None:
    p = verbs.add_parser("tree", parents=[common], help="every live note (restricted: masked)")
    p.set_defaults(handler=tree)
    p = verbs.add_parser("note", parents=[common], help="one note with its text and links")
    p.add_argument("slug")
    p.set_defaults(handler=note)
    p = verbs.add_parser("version", parents=[common], help="a note's version token")
    p.add_argument("slug")
    p.set_defaults(handler=version)
    p = verbs.add_parser("search", parents=[common], help="full-text search over the notes")
    p.add_argument("q")
    p.add_argument("--limit", type=int, default=20)
    p.set_defaults(handler=search)
