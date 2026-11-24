"""`yggdras brain <write verb>`: the brain writes (planning/cli-build-spec.md).

Every verb calls the existing BrainWrites method unchanged, with a RowStore, exactly as
mcp_server.start_api builds it. Before any write, api.brain_note_access(slug) gives the
verdict: a restricted note exits 4, a missing one exits 3. Every writer that changes an
existing note needs --version, which BrainWrites checks: a stale one exits 5 and writes
nothing. A write prints `ok<TAB>slug<TAB>new version[<TAB>undo_id]`; --preview prints
`preview<TAB>slug<TAB>…` and writes nothing."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from .contract import CliError, Out, kind_for_status


def connect():
    from yggdras.data.brain_db import db

    return db.connect()


def make_writes():
    """BrainWrites as mcp_server.start_api builds it: the row store, live only on rows."""
    from yggdras import config
    from yggdras.data.brain_db.writes import BrainWrites
    from yggdras.interface import writing

    return BrainWrites(writing.row_store(), lambda: config.brain_source() == "rows",
                       lambda: dt.date.today().isoformat())  # fmt: skip


def access(slug: str) -> str | None:
    """'normal', 'restricted' or None (no live note), from api.brain_note_access."""
    with connect() as conn:
        row = conn.execute("SELECT api.brain_note_access(%s)", (slug,)).fetchone()
    return row[0] if row else None


def require(*slugs: str) -> None:
    for slug in slugs:
        verdict = access(slug)
        if verdict == "restricted":
            raise CliError("not_allowed", "that note is restricted")
        if verdict is None:
            raise CliError("not_found", f"no live note '{slug}'")


def version_of(slug: str):
    with connect() as conn:
        row = conn.execute("SELECT version FROM api.brain_notes WHERE slug = %s",
                           (slug,)).fetchone()  # fmt: skip
    return row[0] if row else None


def call(method: str, *args):
    from yggdras.data.brain_db.writes import ApiError

    writes = make_writes()
    try:
        return getattr(writes, method)(*args)
    except ApiError as error:
        raise CliError(kind_for_status(error.status, error.message), error.message) from None


def written(slug: str, result: dict, undo: bool) -> Out:
    line = ("ok", slug, version_of(slug)) + ((result.get("undo_id"),) if undo else ())
    return Out(result, [line])


# ---------------------------------------------------------------- handlers


def add_note(args) -> Out:
    from yggdras.data.maps.notes import meta_from_text

    path = Path(args.file)
    if not path.is_file():
        raise CliError("not_found", f"no file {args.file}")
    text = path.read_text(encoding="utf-8")
    meta = meta_from_text(text, "new.md")
    if meta is None:
        raise CliError("invalid", "the text needs frontmatter with a slug (the note format)")
    if access(meta.slug) == "restricted":
        raise CliError("not_allowed", "that note is restricted")
    result = call("add_note", {"text": text})
    return written(meta.slug, result, undo=True)


def add_fact(args) -> Out:
    require(args.slug)
    body = {"line": args.line, "version": args.version}
    if args.section:
        body["section"] = args.section
    if args.after_line:
        body["after_line"] = args.after_line
    return written(args.slug, call("add_fact", args.slug, body), undo=True)


def replace_fact(args) -> Out:
    require(args.slug)
    body = {"old_line": args.old, "new_line": args.new, "version": args.version,
            "preview": args.preview}  # fmt: skip
    result = call("replace_fact", args.slug, body)
    if args.preview:
        return Out(result, [("preview", args.slug, result["old_line"], result["new_line"])])
    return written(args.slug, result, undo=True)


def remove_fact(args) -> Out:
    require(args.slug)
    body = {"line": args.line, "version": args.version, "preview": args.preview}
    result = call("remove_fact", args.slug, body)
    if args.preview:
        return Out(result, [("preview", args.slug, result["remove"])])
    return written(args.slug, result, undo=False)


def link(args) -> Out:
    require(args.slug, args.target)
    body = {"verb": args.link_verb, "target_slug": args.target, "version": args.version,
            "preview": args.preview}  # fmt: skip
    result = call("link", args.slug, body)
    if args.preview:
        return Out(result, [("preview", args.slug, result["add"], result["reverse_reads_as"])])
    return written(args.slug, result, undo=True)


def unlink(args) -> Out:
    require(args.slug, args.target)
    body = {"verb": args.link_verb, "target_slug": args.target, "version": args.version,
            "preview": args.preview}  # fmt: skip
    result = call("unlink", args.slug, body)
    if args.preview:
        return Out(result, [("preview", args.slug, result["remove"])])
    return written(args.slug, result, undo=False)


def undo(args) -> Out:
    result = call("undo", args.undo_id)
    return Out(result, [("ok", args.undo_id, None)])


# ---------------------------------------------------------------- the parsers


def register(verbs, common) -> None:
    def verb(name, handler, help_text):
        parser = verbs.add_parser(name, parents=[common], help=help_text, description=help_text)
        parser.set_defaults(handler=handler)
        return parser

    def versioned(parser, preview=True):
        parser.add_argument("--version", type=int, required=True,
                            help="the note's version as read; a stale one exits 5")  # fmt: skip
        if preview:
            parser.add_argument("--preview", action="store_true", help="show it; write nothing")

    p = verb("add-note", add_note, "add a new note from a file (frontmatter with a slug)")
    p.add_argument("--file", required=True, help="the note's markdown")

    p = verb("add-fact", add_fact, "add a fact line to a note")
    p.add_argument("slug")
    p.add_argument("line", help="the fact; (src: self, today) is added when it has no source")
    p.add_argument("--section", help="the section heading (default: Facts)")
    p.add_argument("--after-line", help="insert after this exact line of the section")
    versioned(p, preview=False)

    p = verb("replace-fact", replace_fact, "replace a fact; the old line goes to History")
    p.add_argument("slug")
    p.add_argument("--old", required=True, help="the fact line as it is now")
    p.add_argument("--new", required=True, help="the new fact line")
    versioned(p)

    p = verb("remove-fact", remove_fact, "remove a fact for good (no undo)")
    p.add_argument("slug")
    p.add_argument("line", help="the fact line as it is now")
    versioned(p)

    for name, handler, text in (
        ("link", link, "add a link line: <slug> <verb> <target> (one row, one direction)"),
        ("unlink", unlink, "remove a link line for good (no undo)"),
    ):
        p = verb(name, handler, text)
        p.add_argument("slug")
        p.add_argument("link_verb", metavar="verb", help="a verb from the fixed list")
        p.add_argument("target")
        versioned(p)

    p = verb("undo", undo, "undo an add-note, add-fact, replace-fact or link, once")
    p.add_argument("undo_id")
