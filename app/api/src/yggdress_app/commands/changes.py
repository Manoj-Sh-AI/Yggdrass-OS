"""`changes read <consumer>`: the next events of the change stream for a named reader.

Wraps events.read (the cursor needs app.events.tx, which api.events does not have) and returns
exactly the api.events columns: ids and kinds, never content. The cursor moves only when the
read commits."""

from __future__ import annotations

import re

from .. import events
from .contract import CliError, Out
from .notes import limit

COLUMNS = ("seq", "at", "kind", "subject_kind", "subject_key", "actor", "sensitivity")


def _plain(value):
    return value.isoformat() if hasattr(value, "isoformat") else value


def read(args) -> Out:
    from . import database

    if not re.fullmatch(events.CONSUMER_PATTERN, args.consumer):
        raise CliError("invalid", "consumer must match " + events.CONSUMER_PATTERN)
    with database().connect() as db:
        rows = events.read(db, args.consumer, args.limit)
    data = [{column: _plain(row[column]) for column in COLUMNS} for row in rows]
    return Out(data, [tuple(row[column] for column in COLUMNS) for row in data])


def register(groups, common) -> None:
    group = groups.add_parser("changes", help="the app's change stream (read)")
    verbs = group.add_subparsers(dest="verb", required=True, parser_class=type(group))
    p = verbs.add_parser(
        "read", parents=[common], help="the next events for a consumer; moves its cursor"
    )
    p.add_argument("consumer", help="the reader's name, [a-z0-9_.:-]{1,80}")
    p.add_argument("--limit", type=limit(1000), default=100, metavar="N")
    p.set_defaults(handler=read)
