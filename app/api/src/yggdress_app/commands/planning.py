"""Planning writes: task, goal, project, block, event, date-item and availability.

Each verb builds the existing command model (planning_models.Command, temporal.TimeCommand,
connections.ConnectionCommand) and calls the same shared function as its router
(planning.apply_command, temporal.apply_time_command, connections.apply_connection): the same
lock, receipt and command id. Fields come from `--set name=value` (repeatable; the value is read
as JSON when it parses, otherwise as text) or `--data JSON`, and are passed on unchanged.
`--key` is the retry key; when left out one is made and printed, so a retry is safe.

Success prints `ok\t<id>\t<version>\t<key>`."""

from __future__ import annotations

import json
from uuid import UUID, uuid4

from fastapi import HTTPException
from pydantic import ValidationError

from .contract import CliError, Out, kind_for_status
from .notes import visible_note

PLANNING = {
    "task": ("create", "update", "execute"),
    "goal": ("create", "update"),
    "project": ("create", "update"),
    "block": ("create", "update", "remove", "split"),
    "event": ("create", "update", "remove"),
}
TEMPORAL = {"date-item": "date_item", "availability": "availability"}
CONNECTIONS = {
    "task": ("link-note", "unlink-note"),
    "event": ("link-note", "unlink-note", "link-task", "unlink-task"),
}
HELP = {
    "create": "create one; fields by --set/--data",
    "update": "replace its fields; fields by --set/--data",
    "execute": "start, pause, resume, complete, progress, reopen or push (--set action=…)",
    "remove": "remove it",
    "split": "split it at --set at=<offset-aware instant>",
    "link-note": "link a note_ref to it",
    "unlink-note": "unlink a note_ref from it",
    "link-task": "link a task to this event",
    "unlink-task": "unlink a task from this event",
}


def _uuid(value: str) -> UUID:
    try:
        return UUID(value)
    except ValueError:
        raise CliError("invalid", f"not an id: {value[:80]}") from None


def _data(args) -> dict:
    data, text = {}, getattr(args, "data", None)
    if text is not None:
        try:
            data = json.loads(text)
        except json.JSONDecodeError as error:
            raise CliError("invalid", f"--data is not JSON: {error.msg}") from None
        if not isinstance(data, dict):
            raise CliError("invalid", "--data must be a JSON object")
    for pair in getattr(args, "set", None) or ():
        name, sep, text = pair.partition("=")
        if not sep or not name:
            raise CliError("invalid", f"--set needs name=value, got {pair[:80]}")
        try:
            data[name] = json.loads(text)
        except json.JSONDecodeError:
            data[name] = text
    return data


def _call(apply, *arguments) -> dict:
    """Run a shared write function, mapping its errors onto the CLI's kinds."""
    try:
        return apply(*arguments)
    except HTTPException as error:
        message = str(error.detail)
        raise CliError(kind_for_status(error.status_code, message), message) from None
    except ValidationError as error:
        raise CliError("invalid", "; ".join(e["msg"] for e in error.errors())) from None


def _model(model, **values):
    try:
        return model(**values)
    except ValidationError as error:
        raise CliError("invalid", "; ".join(e["msg"] for e in error.errors())) from None


def _ok(identifier, result: dict, key: UUID) -> Out:
    data = {**result, "id": str(identifier), "key": str(key)}
    return Out(data, [("ok", data["id"], result.get("version"), data["key"])])


def _key(args) -> UUID:
    return _uuid(args.key) if args.key else uuid4()


def planning_verb(group: str, verb: str):
    def handler(args) -> Out:
        from ..planning import apply_command
        from ..planning_models import Command
        from . import database

        key = _key(args)
        command = _model(
            Command,
            key=key,
            op=f"{group}.{verb}",
            id=_uuid(args.id) if verb != "create" else None,
            version=getattr(args, "version", None),
            data=_data(args),
        )
        result = _call(apply_command, database(), command)
        return _ok(result["id"], result, key)

    return handler


def temporal_verb(operation: str):
    def handler(args) -> Out:
        from ..temporal import TimeCommand, apply_time_command
        from . import database

        key = _key(args)
        verb = operation.partition(".")[2]
        command = _model(
            TimeCommand,
            key=key,
            operation=operation,
            id=_uuid(args.id) if verb != "create" else None,
            version=getattr(args, "version", None),
            data=_data(args),
        )
        result = _call(apply_time_command, database(), command)
        return _ok(result["id"], result, key)

    return handler


def _cli_note(note: dict):
    """The connections handler's `verify`: the note as the app last observed it, read through
    api.note_refs (visible_note has already refused a missing or restricted one)."""

    def verify(slug: str) -> dict:
        if slug != note["slug"]:
            raise CliError("failed", "the note changed while it was being linked")
        return {"slug": note["slug"], "title": note["title"], "version": note["revision"]}

    return verify


def connection_verb(group: str, verb: str):
    def handler(args) -> Out:
        from ..connections import ConnectionCommand, apply_connection
        from . import database

        key = _key(args)
        entity = _uuid(args.id)
        values = {
            "key": key,
            "operation": f"{group}.{verb.replace('-', '_')}",
            "entity_id": entity,
            "version": args.version,
        }
        verify = None
        if verb.endswith("-note"):
            note = visible_note(_uuid(args.note_ref))
            if not note["slug"]:
                raise CliError("not_allowed", "this note is restricted")
            values.update(note_slug=note["slug"], relation=args.relation)
            verify = _cli_note(note)
        else:
            values.update(task_id=_uuid(args.task), task_version=args.task_version)
        command = _model(ConnectionCommand, **values)
        result = _call(apply_connection, database(), command, verify)
        return _ok(entity, result, key)

    return handler


def _fields(parser) -> None:
    parser.add_argument(
        "--set",
        action="append",
        metavar="NAME=VALUE",
        help="one field; VALUE is read as JSON when it parses, else as text (repeatable)",
    )
    parser.add_argument("--data", metavar="JSON", help="all fields as one JSON object")


def _write(verbs, common, verb: str, label: str):
    p = verbs.add_parser(verb, parents=[common], help=HELP[verb])
    p.add_argument("--key", metavar="UUID", help="retry key; made and printed when left out")
    if verb != "create":
        p.add_argument("id", help=f"the {label} id")
        p.add_argument("--version", type=int, required=True, help="the version you read")
    return p


def register(groups, common) -> None:
    parsers = {}
    for group in (*PLANNING, *TEMPORAL):
        parser = groups.add_parser(group, help=f"{group} writes")
        parsers[group] = parser.add_subparsers(
            dest="verb", required=True, parser_class=type(parser)
        )
    for group, verbs in PLANNING.items():
        for verb in verbs:
            p = _write(parsers[group], common, verb, group)
            if verb != "remove":
                _fields(p)
            p.set_defaults(handler=planning_verb(group, verb))
    for group, name in TEMPORAL.items():
        for verb in ("create", "update", "remove"):
            p = _write(parsers[group], common, verb, group)
            if verb != "remove":
                _fields(p)
            p.set_defaults(handler=temporal_verb(f"{name}.{verb}"))
    for group, verbs in CONNECTIONS.items():
        for verb in verbs:
            p = _write(parsers[group], common, verb, group)
            if verb.endswith("-note"):
                p.add_argument("note_ref", help="the note_ref id")
                p.add_argument(
                    "--relation", choices=("source", "context", "result"), default="context"
                )
            else:
                p.add_argument("task", help="the task id")
                p.add_argument(
                    "--task-version", type=int, required=True, help="the task version you read"
                )
            p.set_defaults(handler=connection_verb(group, verb))
