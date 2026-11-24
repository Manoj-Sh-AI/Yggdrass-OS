"""`yggdras task|goal|project|block|event|date-item|availability …` (planning/cli-build-spec.md).

Every write calls the router's own function: planning.apply_command (command_result),
temporal.apply_time_command (temporal_result) or connections.apply_connection (the
connections handler), so the lock, the receipt and the command id are the router's.
Fields are `--set name=value` (repeatable; numbers, true/false and null are read as JSON,
anything else is text) or `--data JSON`, given unchanged to the command model. `--key` is
optional: when it is left out one is made, and printed as the last field so a retry is safe.
A write prints `ok<TAB>id<TAB>new version<TAB>key`."""

from __future__ import annotations

import json
import re
from uuid import UUID, uuid4

from .contract import CliError, Out, kind_for_status
from .notes import check_ref, rows

SCALAR = re.compile(r"^(-?\d+(\.\d+)?|true|false|null)$")


def notes_client():
    """The brain notes client the connections router uses (BRAIN_SERVER_URL)."""
    from ..notes_proxy import NotesProxy

    return NotesProxy()


def fields(args) -> dict:
    data: dict = {}
    if args.data:
        try:
            data = json.loads(args.data)
        except json.JSONDecodeError:
            raise CliError("invalid", "--data is not JSON") from None
        if not isinstance(data, dict):
            raise CliError("invalid", "--data must be a JSON object")
    for item in args.set or ():
        name, sep, value = item.partition("=")
        if not sep or not name:
            raise CliError("usage", f"--set needs name=value, got {item!r}")
        data[name] = json.loads(value) if SCALAR.match(value) else value
    return data


def guarded(call):
    """Run a write; map the router's errors onto the contract."""
    from fastapi import HTTPException
    from pydantic import ValidationError

    from ..notes_proxy import NotesError

    try:
        return call()
    except HTTPException as error:
        detail = str(error.detail)
        raise CliError(kind_for_status(error.status_code, detail), detail) from None
    except NotesError as error:
        raise CliError(kind_for_status(error.status, error.message), error.message) from None
    except ValidationError as error:
        raise CliError("invalid", "; ".join(e["msg"] for e in error.errors())) from None


def written(args, key: str, result: dict, identifier=None) -> Out:
    ident = result.get("id") or identifier
    data = {**result, "key": key}
    return Out(data, [("ok", ident, result.get("version"), key)])


def key_of(args) -> str:
    if not args.key:
        return str(uuid4())
    try:
        return str(UUID(args.key))
    except ValueError:
        raise CliError("invalid", "--key must be a UUID") from None


def plan(op: str):
    def handler(args) -> Out:
        from ..planning import apply_command
        from ..planning_models import Command
        from . import database

        key, identifier = key_of(args), getattr(args, "id", None)
        result = guarded(lambda: apply_command(database(), Command(
            key=key, op=op, id=identifier, version=getattr(args, "version", None),
            data=fields(args))))  # fmt: skip
        return written(args, key, result, identifier)

    return handler


def timed(operation: str):
    def handler(args) -> Out:
        from ..temporal import TimeCommand, apply_time_command
        from . import database

        key, identifier = key_of(args), getattr(args, "id", None)
        result = guarded(lambda: apply_time_command(database(), TimeCommand(
            key=key, operation=operation, id=identifier,
            version=getattr(args, "version", None), data=fields(args))))  # fmt: skip
        return written(args, key, result, identifier)

    return handler


def note_slug(value: str, linking: bool) -> str:
    """A note ref id (from `notes find|refs`) or a slug. A restricted note exits 4, a missing
    one 3: by api.note_refs for an id; by the brain's own note when linking a slug; by
    api.note_search when unlinking a slug (a note not shown there is not found)."""
    try:
        return check_ref(str(UUID(value)))["slug"]
    except ValueError:
        pass
    if linking:
        from ..connections import verified_note
        from ..mobile_policy import sensitive

        note = guarded(lambda: verified_note(notes_client(), value))
        if sensitive(note):
            raise CliError("not_allowed", "that note is restricted")
        return value
    if not rows("SELECT slug FROM api.note_search WHERE slug = %s", (value,)):
        raise CliError("not_found", "no visible note with that slug")
    return value


def connect(operation: str):
    def handler(args) -> Out:
        from ..connections import ConnectionCommand, apply_connection
        from . import database

        key, linking = key_of(args), ".link_" in operation
        body = {"key": key, "operation": operation, "entity_id": args.id, "version": args.version}
        if operation.endswith("_note"):
            body |= {"note_slug": note_slug(args.note_ref, linking), "relation": args.relation}
            notes = notes_client() if linking else None
        else:
            body |= {"task_id": args.task, "task_version": args.task_version}
            notes = None
        result = guarded(lambda: apply_connection(database(), notes, ConnectionCommand(**body)))
        return written(args, key, result, args.id)

    return handler


def register(groups, common) -> None:
    sub = groups._parser_class

    def group(name, help_):
        parser = groups.add_parser(name, help=help_)
        return parser.add_subparsers(dest="verb", required=True, parser_class=sub)

    def verb(verbs, name, handler, help_, *, existing=True, data=True):
        p = verbs.add_parser(name, parents=[common], help=help_)
        if existing:
            p.add_argument("id", help="the item's id")
            p.add_argument("--version", type=int, required=True, help="the version you read")
        if data:
            p.add_argument("--set", action="append", metavar="NAME=VALUE", help="a field")
            p.add_argument("--data", metavar="JSON", help="all fields as a JSON object")
        p.add_argument("--key", help="retry key (UUID); made and printed when left out")
        p.set_defaults(handler=handler)
        return p

    def note_links(verbs, kind):
        for name, op in (("link-note", "link_note"), ("unlink-note", "unlink_note")):
            p = verb(verbs, name, connect(f"{kind}.{op}"), f"{name.split('-')[0]} a note",
                     data=False)  # fmt: skip
            p.add_argument("note_ref", help="a note ref id or a note slug")
            p.add_argument("--relation", choices=("source", "context", "result"),
                           default="context")  # fmt: skip

    verbs = group("task", "tasks")
    verb(verbs, "create", plan("task.create"), "create a task", existing=False)
    verb(verbs, "update", plan("task.update"), "update a task")
    verb(verbs, "execute", plan("task.execute"), "start, pause, complete … a task")
    note_links(verbs, "task")

    for name in ("goal", "project"):
        verbs = group(name, f"{name}s")
        verb(verbs, "create", plan(f"{name}.create"), f"create a {name}", existing=False)
        verb(verbs, "update", plan(f"{name}.update"), f"update a {name}")

    verbs = group("block", "execution blocks")
    verb(verbs, "create", plan("block.create"), "schedule a block", existing=False)
    verb(verbs, "update", plan("block.update"), "move a block")
    verb(verbs, "remove", plan("block.remove"), "cancel a block")
    verb(verbs, "split", plan("block.split"), "split a block (--set at=INSTANT)")

    verbs = group("event", "calendar events")
    verb(verbs, "create", plan("event.create"), "create an event", existing=False)
    verb(verbs, "update", plan("event.update"), "update an event")
    verb(verbs, "remove", plan("event.remove"), "cancel an event")
    note_links(verbs, "event")
    for name, op in (("link-task", "link_task"), ("unlink-task", "unlink_task")):
        p = verb(verbs, name, connect(f"event.{op}"), f"{name.split('-')[0]} a task", data=False)
        p.add_argument("task", help="the task's id")
        p.add_argument("--task-version", type=int, required=True, dest="task_version")

    for name, kind in (("date-item", "date_item"), ("availability", "availability")):
        verbs = group(name, f"{name} entries")
        verb(verbs, "create", timed(f"{kind}.create"), f"create a {name}", existing=False)
        verb(verbs, "update", timed(f"{kind}.update"), f"update a {name}")
        verb(verbs, "remove", timed(f"{kind}.remove"), f"remove a {name}")
