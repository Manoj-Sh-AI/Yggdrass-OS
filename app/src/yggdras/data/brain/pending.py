"""Pending previews and Lia's writes, in local SQLite (D12): never in the brain.

A change that alters or removes content waits here as a preview until Manoj confirms or
cancels it; after 24 hours it expires. Each preview carries a random token that only the
app's card (or the CLI on Manoj's machine) holds, so the chat model can't confirm it.
"""

from __future__ import annotations

import json
import secrets
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

TTL_S = 24 * 3600

SCHEMA = """
create table if not exists pending (
  id text primary key,
  created real not null,
  expires real not null,
  token text not null,
  request text not null,
  app text not null,
  ops text not null,
  preview text not null,
  state text not null default 'pending',
  result text not null default ''
);
create table if not exists writes (
  sha text primary key,
  created real not null,
  title text not null,
  app text not null,
  token text not null default ''
);
"""


@dataclass
class Pending:
    id: str
    created: float
    expires: float
    token: str
    request: str
    app: str
    ops: list[dict]
    preview: str
    state: str
    result: str


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with self._db() as db:
            db.executescript(SCHEMA)

    def _db(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def add(
        self,
        request: str,
        app: str,
        ops: list[dict],
        preview: str,
        now: float | None = None,
        ttl: float = TTL_S,
    ) -> Pending:
        now = time.time() if now is None else now
        pid = time.strftime("c-%Y%m%d-%H%M%S", time.localtime(now)) + "-" + secrets.token_hex(2)
        token = secrets.token_urlsafe(16)
        with self._db() as db:
            db.execute(
                "insert into pending (id, created, expires, token, request, app, ops, preview) "
                "values (?, ?, ?, ?, ?, ?, ?, ?)",
                (pid, now, now + ttl, token, request, app, json.dumps(ops), preview),
            )
        return self.get(pid, now)

    def get(self, pid: str, now: float | None = None) -> Pending | None:
        with self._db() as db:
            row = db.execute(
                "select id, created, expires, token, request, app, ops, preview, state, result "
                "from pending where id = ?",
                (pid.strip(),),
            ).fetchone()
        if row is None:
            return None
        item = Pending(*row[:6], json.loads(row[6]), *row[7:])
        now = time.time() if now is None else now
        if item.state == "pending" and now > item.expires:
            self.resolve(item.id, "expired")
            item.state = "expired"
        return item

    def resolve(self, pid: str, state: str, result: str = "") -> None:
        with self._db() as db:
            db.execute(
                "update pending set state = ?, result = ? where id = ?", (state, result, pid)
            )

    def open_items(self, now: float | None = None) -> list[Pending]:
        with self._db() as db:
            ids = [
                r[0]
                for r in db.execute(
                    "select id from pending where state = 'pending' order by created"
                )
            ]
        return [p for p in (self.get(i, now) for i in ids) if p and p.state == "pending"]

    def record_write(self, sha: str, title: str, app: str) -> str:
        """Remember a write for Undo; returns the token the card's Undo button carries."""
        token = secrets.token_urlsafe(16)
        with self._db() as db:
            db.execute(
                "insert or replace into writes (sha, created, title, app, token) "
                "values (?, ?, ?, ?, ?)",
                (sha, time.time(), title, app, token),
            )
        return token

    def write_token(self, sha: str) -> str | None:
        with self._db() as db:
            rows = db.execute(
                "select sha, token from writes where sha like ?", (sha.strip() + "%",)
            ).fetchall()
        return rows[0][1] if len(rows) == 1 else None

    def recent_writes(self, limit: int = 10) -> list[tuple[str, float, str, str]]:
        with self._db() as db:
            return db.execute(
                "select sha, created, title, app from writes order by created desc limit ?",
                (limit,),
            ).fetchall()
