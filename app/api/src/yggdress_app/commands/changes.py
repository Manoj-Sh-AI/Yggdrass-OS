"""`yggdras changes read <consumer> [--limit N]` (planning/cli-build-spec.md).

The one exception to "reads use only api.* views": it wraps events.read, because the cursor
needs the `tx` column the api.events view leaves out. It returns exactly the api.events
columns (ids and kinds, never content). The cursor moves only when the read commits."""

from __future__ import annotations

import re

from .contract import CliError, Out

COLUMNS = ("seq", "at", "kind", "subject_kind", "subject_key", "actor", "sensitivity")


def read(args) -> Out:
    from .. import events
    from . import database

    if not re.match(events.CONSUMER_PATTERN, args.consumer):
        raise CliError("invalid", "consumer is 1-80 of a-z 0-9 _ . : -")
    if not 1 <= args.limit <= 1000:
        raise CliError("invalid", "limit must be between 1 and 1000")
    with database().connect() as db:
        found = [{c: r[c] for c in COLUMNS} for r in events.read(db, args.consumer, args.limit)]
    return Out(found, [tuple(r[c] for c in COLUMNS) for r in found])


def register(groups, common) -> None:
    changes = groups.add_parser("changes", help="the app's change stream, by cursor")
    verbs = changes.add_subparsers(dest="verb", required=True, parser_class=groups._parser_class)
    p = verbs.add_parser("read", parents=[common], help="the next events for a named cursor")
    p.add_argument("consumer")
    p.add_argument("--limit", type=int, default=100)
    p.set_defaults(handler=read)
