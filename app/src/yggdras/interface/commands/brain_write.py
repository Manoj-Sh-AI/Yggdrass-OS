"""`yggdras brain add-note|add-fact|replace-fact|remove-fact|link|unlink|undo`
(planning/cli-build-spec.md).

Every write calls the existing BrainWrites method unchanged, with a RowStore, exactly as
mcp_server.start_api builds it. api.brain_note_access(slug) is checked first: a restricted
note exits 4, a missing one 3. --version is passed to BrainWrites, so a stale one exits 5
and writes nothing. A write prints `ok<TAB>slug<TAB>new version[<TAB>undo_id]`."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from .brain_read import _connect, check_access
from .contract import CliError, Out, kind_for_status


def writes():
    """BrainWrites over the row store, as mcp_server.start_api builds it."""
    from yggdras import config
    from yggdras.data.brain_db.writes import BrainWrites
    from yggdras.interface import writing

    return BrainWrites(writing.row_store(), lambda: config.brain_source() == "rows",
                       lambda: dt.date.today().isoformat())  # fmt: skip


def _access(slug: str) -> None:
    with _connect() as conn:
        check_access(conn, slug)


def _version(slug: str):
    with _connect() as conn:
        row = conn.execute("SELECT version FROM api.brain_notes WHERE slug = %s",
                           (slug,)).fetchone()  # fmt: skip
    return row[0] if row else None


def _call(method: str, *call_args):
    from yggdras.data.brain_db.writes import ApiError

    try:
        return getattr(writes(), method)(*call_args)
    except ApiError as error:
        raise CliError(kind_for_status(error.status, error.message), error.message) from None


def _done(slug: str, result: dict) -> Out:
    if result.get("preview"):
        return Out(result, [("preview", slug, *_preview_cells(result))])
    new = _version(slug)
    data = {"slug": slug, "version": new, **result}
    line = ["ok", slug, new]
    if result.get("undo_id") and "undo" not in result:  # remove/unlink: no undo
        line.append(result["undo_id"])
    return Out(data, [tuple(line)])


def _preview_cells(result: dict) -> list:
    for key in ("add", "remove"):
        if key in result:
            return [key, result[key]]
    return ["replace", result.get("old_line"), result.get("new_line")]


def _body(args, **fields) -> dict:
    body = {"version": args.version, **fields}
    if hasattr(args, "preview"):
        body["preview"] = args.preview
    return body


def add_note(args) -> Out:
    text = Path(args.file).read_text(encoding="utf-8")
    from yggdras.data.maps.notes import meta_from_text

    meta = meta_from_text(text, "new.md")
    if meta is not None:
        with _connect() as conn:
            known = conn.execute("SELECT api.brain_note_access(%s)", (meta.slug,)).fetchone()[0]
        if known == "restricted":
            raise CliError("not_allowed", "that note is restricted")
    result = _call("add_note", {"text": text})
    return _done(meta.slug, result)


def add_fact(args) -> Out:
    _access(args.slug)
    body = _body(args, line=args.line, section=args.section, after_line=args.after_line)
    return _done(args.slug, _call("add_fact", args.slug, body))


def replace_fact(args) -> Out:
    _access(args.slug)
    body = _body(args, old_line=args.old, new_line=args.new)
    return _done(args.slug, _call("replace_fact", args.slug, body))


def remove_fact(args) -> Out:
    _access(args.slug)
    return _done(args.slug, _call("remove_fact", args.slug, _body(args, line=args.line)))


def _link(method: str):
    def handler(args) -> Out:
        _access(args.slug)
        _access(args.target)
        body = _body(args, verb=args.link_verb, target_slug=args.target)
        return _done(args.slug, _call(method, args.slug, body))

    return handler


def undo(args) -> Out:
    result = _call("undo", args.undo_id)
    return Out(result, [("ok", args.undo_id, result.get("operation"), result.get("change_id"))])


def register(verbs, common) -> None:
    def verb(name, handler, help_, *, version=True, preview=False):
        p = verbs.add_parser(name, parents=[common], help=help_)
        if version:
            p.add_argument("--version", type=int, required=True, help="the version you read")
        if preview:
            p.add_argument("--preview", action="store_true", help="show it; write nothing")
        p.set_defaults(handler=handler)
        return p

    p = verb("add-note", add_note, "add a note from a file (frontmatter needs a slug)",
             version=False)  # fmt: skip
    p.add_argument("--file", required=True)
    p = verb("add-fact", add_fact, "add a fact line to a note")
    p.add_argument("slug")
    p.add_argument("line")
    p.add_argument("--section")
    p.add_argument("--after-line", dest="after_line")
    p = verb("replace-fact", replace_fact, "replace a fact (the old line goes to history)",
             preview=True)  # fmt: skip
    p.add_argument("slug")
    p.add_argument("--old", required=True)
    p.add_argument("--new", required=True)
    p = verb("remove-fact", remove_fact, "remove a fact for good", preview=True)
    p.add_argument("slug")
    p.add_argument("line")
    for name, method, help_ in (("link", "link", "add a link"),
                                ("unlink", "unlink", "remove a link for good")):  # fmt: skip
        p = verb(name, _link(method), help_, preview=True)
        p.add_argument("slug")
        p.add_argument("link_verb", metavar="verb")
        p.add_argument("target")
    p = verb("undo", undo, "undo an add or a replace", version=False)
    p.add_argument("undo_id")
