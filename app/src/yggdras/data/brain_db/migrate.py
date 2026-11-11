"""Versioned migrations for the `brain` schema, forward and back.

Usage:
    python -m yggdras.data.brain_db.migrate up            # apply every pending migration
    python -m yggdras.data.brain_db.migrate down [N]      # roll back to version N (default: one)
    python -m yggdras.data.brain_db.migrate status

Each migration is a pair of files in migrations/: NNNN_name.up.sql and NNNN_name.down.sql.
Each runs in one transaction with its log row, so a failed migration leaves nothing behind.
The runner owns the `brain` schema and its log table, brain.schema_migrations.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from importlib import resources

from yggdras.data.brain_db.db import SCHEMA, DatabaseError, connect

FILE = re.compile(r"^(\d{4})_([a-z0-9_]+)\.(up|down)\.sql$")


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    up: str
    down: str


def migrations() -> list[Migration]:
    """Every migration in the package, in version order."""
    found: dict[int, dict[str, str]] = {}
    folder = resources.files("yggdras.data.brain_db") / "migrations"
    for item in folder.iterdir():
        m = FILE.match(item.name)
        if m:
            entry = found.setdefault(int(m.group(1)), {"name": m.group(2)})
            entry[m.group(3)] = item.read_text(encoding="utf-8")
    out = []
    for version in sorted(found):
        entry = found[version]
        if "up" not in entry or "down" not in entry:
            raise ValueError(f"migration {version:04d} needs both an up and a down file")
        out.append(Migration(version, entry["name"], entry["up"], entry["down"]))
    return out


def _ensure_log(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
        cur.execute(
            f"CREATE TABLE IF NOT EXISTS {SCHEMA}.schema_migrations ("
            "version integer PRIMARY KEY, name text NOT NULL, "
            "applied_at timestamptz NOT NULL DEFAULT now())"
        )
    conn.commit()


def current(conn) -> int:
    _ensure_log(conn)
    with conn.cursor() as cur:
        cur.execute(f"SELECT coalesce(max(version), 0) FROM {SCHEMA}.schema_migrations")
        return cur.fetchone()[0]


def up(conn, target: int | None = None) -> list[int]:
    """Apply pending migrations up to *target* (default: all). Returns the versions applied."""
    done = []
    at = current(conn)
    for m in migrations():
        if m.version <= at or (target is not None and m.version > target):
            continue
        with conn.transaction(), conn.cursor() as cur:
            cur.execute(m.up)
            cur.execute(
                f"INSERT INTO {SCHEMA}.schema_migrations (version, name) VALUES (%s, %s)",
                (m.version, m.name),
            )
        done.append(m.version)
    conn.commit()
    return done


def down(conn, target: int | None = None) -> list[int]:
    """Roll back to *target* (default: one step back). Returns the versions rolled back."""
    done = []
    at = current(conn)
    target = max(at - 1, 0) if target is None else target
    for m in reversed(migrations()):
        if m.version > at or m.version <= target:
            continue
        with conn.transaction(), conn.cursor() as cur:
            cur.execute(m.down)
            cur.execute(f"DELETE FROM {SCHEMA}.schema_migrations WHERE version = %s", (m.version,))
        done.append(m.version)
    conn.commit()
    return done


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m yggdras.data.brain_db.migrate")
    parser.add_argument("command", choices=("up", "down", "status"))
    parser.add_argument("target", nargs="?", type=int)
    args = parser.parse_args(argv)
    try:
        conn = connect()
    except DatabaseError as exc:
        print(exc, file=sys.stderr)
        return 2
    with conn:
        if args.command == "up":
            print(f"applied: {up(conn, args.target) or 'nothing'}")
        elif args.command == "down":
            print(f"rolled back: {down(conn, args.target) or 'nothing'}")
        print(f"schema version: {current(conn)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
