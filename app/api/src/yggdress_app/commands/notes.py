"""`notes find/refs/linked` and `links list`: reads of the app's note references and links.

Reads only the api.* views (api.note_search, api.note_refs, api.note_links, api.links), which
apply the sensitivity rule once: a note that is not known to be normal never shows its slug,
title or revision. Naming a restricted note as the target exits 4; a missing one exits 3."""

from __future__ import annotations

from uuid import UUID

from .contract import CliError, Out

KINDS = ("note", "task", "event", "date_item", "availability")


def _uuid(value: str) -> UUID:
    try:
        return UUID(value)
    except ValueError:
        raise CliError("invalid", f"not an id: {value[:80]}") from None


def limit(maximum: int):
    """An argparse type: an integer from 1 to `maximum`."""

    def parse(value: str) -> int:
        number = int(value)
        if not 1 <= number <= maximum:
            raise ValueError(value)
        return number

    parse.__name__ = f"limit 1..{maximum}"
    return parse


def _thing(value: str) -> tuple[str, UUID]:
    kind, _, identifier = value.partition(":")
    if kind not in KINDS or not identifier:
        raise CliError("invalid", f"use KIND:ID, KIND one of {', '.join(KINDS)}")
    return kind, _uuid(identifier)


def _read(query: str, params: tuple) -> list[dict]:
    from . import database

    with database().connect() as db:
        db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        return [dict(r) for r in db.execute(query, params).fetchall()]


def visible_note(identifier: UUID) -> dict:
    """The note_ref row from api.note_refs, or exit 3 (missing) / 4 (not known to be normal)."""
    rows = _read(
        "SELECT id, slug, title, revision, sensitivity FROM api.note_refs WHERE id=%s",
        (identifier,),
    )
    if not rows:
        raise CliError("not_found", "no such note")
    if rows[0]["sensitivity"] != "normal":
        raise CliError("not_allowed", "this note is restricted")
    return rows[0]


def _out(rows: list[dict], fields: tuple[str, ...]) -> Out:
    rows = [{k: (str(v) if isinstance(v, UUID) else v) for k, v in r.items()} for r in rows]
    return Out(rows, [tuple(r[f] for f in fields) for r in rows])


def find(args) -> Out:
    pattern = "%" + args.query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    rows = _read(
        "SELECT id, slug, title FROM api.note_search WHERE title ILIKE %s OR slug ILIKE %s "
        "ORDER BY title, id LIMIT %s",
        (pattern, pattern, args.limit),
    )
    return _out(rows, ("id", "slug", "title"))


def refs(args) -> Out:
    fields = ("id", "slug", "title", "revision", "sensitivity")
    if args.id:
        return _out([visible_note(_uuid(args.id))], fields)
    rows = _read(
        "SELECT id, slug, title, revision, sensitivity FROM api.note_refs "
        "ORDER BY title, id LIMIT %s",
        (args.limit,),
    )
    return _out(rows, fields)


def linked(args) -> Out:
    if args.note:
        note = visible_note(_uuid(args.note))
        rows = _read(
            "SELECT link_id, thing_kind, thing_id, verb FROM api.note_links "
            "WHERE note_ref_id=%s ORDER BY thing_kind, thing_id, verb",
            (note["id"],),
        )
        return _out(rows, ("thing_kind", "thing_id", "verb", "link_id"))
    kind, identifier = _thing(args.thing)
    if kind == "note":
        raise CliError("invalid", "use --note for a note")
    rows = _read(
        "SELECT link_id, note_ref_id, slug, title, sensitivity, verb FROM api.note_links "
        "WHERE thing_kind=%s AND thing_id=%s ORDER BY note_ref_id, verb",
        (kind, identifier),
    )
    # A list with nothing in it is empty with exit 0, like `brain search`; exit 3 is kept for
    # "that one thing does not exist", so an agent can tell the two apart.
    return _out(rows, ("note_ref_id", "slug", "title", "sensitivity", "verb", "link_id"))


def links(args) -> Out:
    identifier = _uuid(args.id)
    if args.kind == "note":
        visible_note(identifier)
    rows = _read(
        "SELECT id, from_kind, from_id, from_label, verb, to_kind, to_id, to_label, origin, "
        "approved FROM api.links WHERE ((from_kind=%s AND from_id=%s) OR (to_kind=%s AND to_id=%s))"
        " AND (%s::text IS NULL OR verb=%s) ORDER BY verb, id",
        (args.kind, identifier, args.kind, identifier, args.link_verb, args.link_verb),
    )
    fields = ("id", "from_kind", "from_id", "from_label", "verb", "to_kind", "to_id", "to_label")
    return _out(rows, fields)


def register(groups, common) -> None:
    notes = groups.add_parser("notes", help="the app's note references (read)")
    verbs = notes.add_subparsers(dest="verb", required=True, parser_class=type(notes))

    p = verbs.add_parser("find", parents=[common], help="search visible notes by slug or title")
    p.add_argument("query")
    p.add_argument("--limit", type=limit(200), default=20, metavar="N")
    p.set_defaults(handler=find)

    p = verbs.add_parser("refs", parents=[common], help="list note references, or one by --id")
    p.add_argument("--id", help="a note_ref id")
    p.add_argument("--limit", type=limit(1000), default=100, metavar="N")
    p.set_defaults(handler=refs)

    p = verbs.add_parser(
        "linked", parents=[common], help="things linked to a note, or notes to a thing"
    )
    target = p.add_mutually_exclusive_group(required=True)
    target.add_argument("--note", metavar="ID", help="a note_ref id")
    target.add_argument("--thing", metavar="KIND:ID", help=f"KIND one of {', '.join(KINDS[1:])}")
    p.set_defaults(handler=linked)

    group = groups.add_parser("links", help="the app's links (read)")
    verbs = group.add_subparsers(dest="verb", required=True, parser_class=type(group))
    p = verbs.add_parser("list", parents=[common], help="active links at one end")
    p.add_argument("--kind", required=True, choices=KINDS)
    p.add_argument("--id", required=True)
    p.add_argument("--verb", dest="link_verb", default=None)
    p.set_defaults(handler=links)
