"""`yggdras notes find|refs|linked` and `yggdras links list` (planning/cli-build-spec.md).

Reads only api.note_search, api.note_refs, api.note_links and api.links (migration 043), so
the sensitivity rule is applied once, in SQL. A restricted or unknown note ref asked for by
id exits 4; a missing one exits 3."""

from __future__ import annotations

from uuid import UUID

from .contract import CliError, Out

KINDS = ("note", "task", "event", "availability", "date_item")


def rows(sql: str, args: tuple = ()) -> list[dict]:
    from . import database

    with database().connect() as db:
        db.execute("SET TRANSACTION READ ONLY")
        return [dict(r) for r in db.execute(sql, args).fetchall()]


def uuid_arg(value: str) -> str:
    try:
        return str(UUID(value))
    except ValueError:
        raise CliError("invalid", f"not an id: {value!r}") from None


def check_ref(ref_id: str) -> dict:
    """The api.note_refs row for one id: missing exits 3, anything not normal exits 4."""
    found = rows(
        "SELECT id, slug, title, revision, sensitivity, last_verified_at FROM api.note_refs "
        "WHERE id = %s",
        (ref_id,),
    )
    if not found:
        raise CliError("not_found", f"no note ref {ref_id}")
    if found[0]["sensitivity"] != "normal":
        raise CliError("not_allowed", "that note is restricted")
    return found[0]


def find(args) -> Out:
    like = "%" + args.q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    found = rows(
        "SELECT id, slug, title FROM api.note_search WHERE slug ILIKE %s OR title ILIKE %s "
        "ORDER BY title, slug LIMIT %s",
        (like, like, args.limit),
    )
    return Out(found, [(r["id"], r["slug"], r["title"]) for r in found])


def refs(args) -> Out:
    if args.id:
        one = check_ref(uuid_arg(args.id))
        return Out(one, [(one["id"], one["slug"], one["title"], one["revision"])])
    found = rows(
        "SELECT id, slug, title, revision, sensitivity, last_verified_at FROM api.note_refs "
        "ORDER BY slug NULLS LAST, id LIMIT %s",
        (args.limit,),
    )
    return Out(found, [(r["id"], r["slug"], r["title"], r["revision"]) for r in found])


def thing_arg(value: str) -> tuple[str, str]:
    kind, _, identifier = value.partition(":")
    if kind not in KINDS or kind == "note":
        raise CliError("invalid", f"--thing is KIND:ID, KIND one of {', '.join(KINDS[1:])}")
    return kind, uuid_arg(identifier)


def linked(args) -> Out:
    if args.note:
        ref_id = uuid_arg(args.note)
        check_ref(ref_id)
        found = rows(
            "SELECT link_id, thing_kind, thing_id, verb FROM api.note_links "
            "WHERE note_ref_id = %s ORDER BY thing_kind, thing_id",
            (ref_id,),
        )
        return Out(found, [(r["thing_kind"], r["thing_id"], r["verb"], r["link_id"])
                           for r in found])  # fmt: skip
    kind, identifier = thing_arg(args.thing)
    found = rows(
        "SELECT link_id, verb, note_ref_id, slug, title, sensitivity FROM api.note_links "
        "WHERE thing_kind = %s AND thing_id = %s ORDER BY slug NULLS LAST, note_ref_id",
        (kind, identifier),
    )
    return Out(found, [(r["note_ref_id"], r["slug"], r["title"], r["verb"], r["link_id"])
                       for r in found])  # fmt: skip


def links_list(args) -> Out:
    identifier = uuid_arg(args.id)
    if args.kind == "note":
        check_ref(identifier)
    sql = (
        "SELECT id, from_kind, from_id, from_label, verb, to_kind, to_id, to_label, origin, "
        "approved, created_at FROM api.links "
        "WHERE ((from_kind = %s AND from_id = %s) OR (to_kind = %s AND to_id = %s))"
    )
    params: tuple = (args.kind, identifier, args.kind, identifier)
    if args.verb:
        sql, params = sql + " AND verb = %s", (*params, args.verb)
    found = rows(sql + " ORDER BY created_at, id", params)
    lines = [(r["id"], r["from_kind"], r["from_id"], r["from_label"], r["verb"], r["to_kind"],
              r["to_id"], r["to_label"]) for r in found]  # fmt: skip
    return Out(found, lines)


def register(groups, common) -> None:
    notes = groups.add_parser("notes", help="note refs the app knows (api.* views only)")
    verbs = notes.add_subparsers(dest="verb", required=True, parser_class=groups._parser_class)
    p = verbs.add_parser("find", parents=[common], help="find normal notes by slug or title")
    p.add_argument("q")
    p.add_argument("--limit", type=int, default=50)
    p.set_defaults(handler=find)
    p = verbs.add_parser("refs", parents=[common], help="note refs (restricted: masked)")
    p.add_argument("--id")
    p.add_argument("--limit", type=int, default=200)
    p.set_defaults(handler=refs)
    p = verbs.add_parser("linked", parents=[common], help="things linked to a note, or notes "
                         "linked to a thing")  # fmt: skip
    which = p.add_mutually_exclusive_group(required=True)
    which.add_argument("--note", metavar="ID", help="a note ref id")
    which.add_argument("--thing", metavar="KIND:ID", help="e.g. task:<uuid>")
    p.set_defaults(handler=linked)

    links = groups.add_parser("links", help="typed links between app things (api.links)")
    verbs = links.add_subparsers(dest="verb", required=True, parser_class=groups._parser_class)
    p = verbs.add_parser("list", parents=[common], help="the active links of one thing")
    p.add_argument("--kind", required=True, choices=KINDS)
    p.add_argument("--id", required=True)
    p.add_argument("--verb")
    p.set_defaults(handler=links_list)
