"""`yggdras brain tree|note|version|search` (planning/cli-build-spec.md).

Reads only the api.brain_* views and api.brain_note_access() (brain migration 0005), so the
sensitivity rule is applied once, in SQL. A restricted slug exits 4, a missing one exits 3;
the error names only the slug the caller already gave."""

from __future__ import annotations

from contextlib import closing

from .contract import CliError, Out


def _connect():
    from yggdras.data.brain_db import db

    return db.connect()


def _rows(conn, sql: str, args: tuple = ()) -> list[tuple]:
    with conn.cursor() as cur:
        cur.execute(sql, args)
        return cur.fetchall()


def _check_access(conn, slug: str) -> None:
    verdict = _rows(conn, "SELECT api.brain_note_access(%s)", (slug,))[0][0]
    if verdict is None:
        raise CliError("not_found", f"no live note {slug!r}")
    if verdict != "normal":
        raise CliError("not_allowed", "this note is restricted")  # never echo its slug


def tree(args) -> Out:
    """One line per live note: area, slug, title, type, shelf, parent, version. A restricted
    note is the masked row the view gives (slug '-', title 'Sensitive note')."""
    with closing(_connect()) as conn:
        rows = _rows(
            conn,
            "SELECT area_code, slug, title, type, shelf_no, parent_slug, version "
            'FROM api.brain_notes ORDER BY area_code, slug COLLATE "C" NULLS LAST',
        )
    keys = ("area", "slug", "title", "type", "shelf", "parent", "version")
    return Out([dict(zip(keys, r, strict=True)) for r in rows], [tuple(r) for r in rows])


def note(args) -> Out:
    """The note line (slug, title, type, area, version, description, status), its other
    areas, its links (from, verb, inverse, to, kind) and its masked body, one line each."""
    with closing(_connect()) as conn:
        _check_access(conn, args.slug)
        found = _rows(
            conn,
            "SELECT slug, title, type, area_code, version, description, status, body "
            "FROM api.brain_note_bodies WHERE slug = %s",
            (args.slug,),
        )
        if not found:
            raise CliError("not_found", f"no live note {args.slug!r}")
        areas = [
            code
            for (code,) in _rows(
                conn,
                "SELECT area_code FROM api.brain_note_areas WHERE slug = %s ORDER BY ord",
                (args.slug,),
            )
        ]
        links = _rows(
            conn,
            "SELECT from_slug, verb, inverse, to_slug, kind FROM api.brain_links "
            "WHERE from_slug = %s OR to_slug = %s "
            'ORDER BY from_slug COLLATE "C", verb, to_slug COLLATE "C"',
            (args.slug, args.slug),
        )
    slug, title, type_, area, version, description, status, body = found[0]
    data = dict(
        slug=slug, title=title, type=type_, area=area, version=version,
        description=description, status=status, areas=areas,
        links=[dict(zip(("from", "verb", "inverse", "to", "kind"), r, strict=True))
               for r in links],
        body=body,
    )  # fmt: skip
    lines: list[tuple] = [("note", slug, title, type_, area, version, description, status)]
    if areas:
        lines.append(("areas", *areas))
    lines += [("link", *r) for r in links]
    lines.append(("body", body))
    return Out(data, lines)


def version(args) -> Out:
    """`slug<TAB>version`: the token a write needs."""
    with closing(_connect()) as conn:
        _check_access(conn, args.slug)
        found = _rows(conn, "SELECT version FROM api.brain_notes WHERE slug = %s", (args.slug,))
    if not found:
        raise CliError("not_found", f"no live note {args.slug!r}")
    return Out(dict(slug=args.slug, version=found[0][0]), [(args.slug, found[0][0])])


def search(args) -> Out:
    """Full-text search (web-search syntax, 'simple' config), best match first. One line per
    hit: slug, title, type, area, version. Empty text lists every visible note by slug, as
    the brain's own search does."""
    q = args.q.strip()
    cols = "s.slug, s.title, s.type, s.area_code, s.version"
    with closing(_connect()) as conn:
        if not q:
            rows = _rows(conn, f'SELECT {cols} FROM api.brain_search s ORDER BY s.slug COLLATE "C"')
        else:
            rows = _rows(
                conn,
                f"SELECT {cols} FROM api.brain_search s, "
                "websearch_to_tsquery('simple', %s) AS query WHERE s.document @@ query "
                'ORDER BY ts_rank(s.document, query) DESC, s.slug COLLATE "C"',
                (q,),
            )
    keys = ("slug", "title", "type", "area", "version")
    return Out([dict(zip(keys, r, strict=True)) for r in rows], [tuple(r) for r in rows])


def register(verbs, common) -> None:
    p = verbs.add_parser("tree", parents=[common], help="every live note, by area")
    p.set_defaults(handler=tree)
    p = verbs.add_parser("note", parents=[common], help="one note: links and text")
    p.add_argument("slug")
    p.set_defaults(handler=note)
    p = verbs.add_parser("version", parents=[common], help="a note's version token")
    p.add_argument("slug")
    p.set_defaults(handler=version)
    p = verbs.add_parser("search", parents=[common], help="full-text search over notes")
    p.add_argument("q", help='words, "phrases", -not')
    p.set_defaults(handler=search)
