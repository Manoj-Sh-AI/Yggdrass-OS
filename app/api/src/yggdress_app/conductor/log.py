"""The durable event log behind every run.

A run's state changes only by appending ops here. Each op gets the next sequence
number, so a client that disconnects (closed tab, dropped network) reconnects by
asking for everything after the last seq it saw and rebuilds the same state.

The two ops mirror assistant-stream's state protocol [cited]: `set` a value at a path
and `append-text` to a string at a path. `apply` is pure and shared with the tests;
the web client applies the same ops the same way.
"""

from __future__ import annotations

import threading
from typing import Any, Literal
from uuid import UUID

from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field

from .state import TERMINAL, RunState

Path = list[str | int]


class Op(BaseModel):
    model_config = ConfigDict(extra="forbid")
    op: Literal["set", "append-text"]
    path: Path = Field(min_length=1, max_length=8)
    value: Any = None


def set_(path: Path, value: Any) -> Op:
    return Op(op="set", path=path, value=value)


def append_text(path: Path, text: str) -> Op:
    return Op(op="append-text", path=path, value=text)


def apply(state: dict, op: Op) -> dict:
    """Apply one op to a JSON state in place (and return it)."""
    *parents, last = op.path
    node: Any = state
    for key in parents:
        node = node[key]
    if op.op == "set":
        if isinstance(node, list) and last == len(node):
            node.append(op.value)  # setting one past the end appends (new list item)
        else:
            node[last] = op.value
    else:
        if not isinstance(op.value, str) or not isinstance(node[last], str):
            raise ValueError("append-text needs a string target and a string value.")
        node[last] += op.value
    return state


class RunNotFound(LookupError):
    pass


class Bus:
    """Wakes in-process listeners when a run's log grows. Durability is the database's
    job; this only saves a live stream from polling."""

    def __init__(self):
        self._condition = threading.Condition()
        self._latest: dict[str, int] = {}

    def publish(self, run_id: str, seq: int) -> None:
        with self._condition:
            self._latest[run_id] = max(seq, self._latest.get(run_id, 0))
            self._condition.notify_all()

    def wait(self, run_id: str, after: int, timeout: float) -> bool:
        """True once the run has events after `after`; False on timeout."""
        with self._condition:
            return self._condition.wait_for(
                lambda: self._latest.get(run_id, 0) > after, timeout=timeout
            )


class RunLog:
    def __init__(self, database, bus: Bus | None = None):
        self.database = database
        self.bus = bus or Bus()

    def start(self, state: RunState, request: str) -> None:
        with self.database.connect() as db:
            db.execute(
                """INSERT INTO app.conductor_runs(id,conversation_id,request,status,mode,state)
                   VALUES (%s,%s,%s,%s,%s,%s)""",
                (
                    state.run_id,
                    state.conversation_id,
                    request,
                    state.status,
                    state.mode,
                    Jsonb(state.model_dump(mode="json")),
                ),
            )

    def append(self, run_id: str, ops: list[Op]) -> int:
        """Append ops atomically; returns the new last seq. The stored snapshot is
        validated against the schema, so an op can never leave an invalid state."""
        if not ops:
            raise ValueError("Nothing to append.")
        with self.database.connect() as db:
            row = db.execute(
                "SELECT state,last_seq FROM app.conductor_runs WHERE id=%s FOR UPDATE",
                (run_id,),
            ).fetchone()
            if not row:
                raise RunNotFound(run_id)
            state = row["state"]
            for op in ops:
                apply(state, op)
            checked = RunState.model_validate(state)
            seq = row["last_seq"]
            with db.cursor() as cursor:
                cursor.executemany(
                    "INSERT INTO app.conductor_events(run_id,seq,op,path,value) VALUES (%s,%s,%s,%s,%s)",
                    [
                        (run_id, seq + i, op.op, Jsonb(op.path), Jsonb(op.value))
                        for i, op in enumerate(ops, start=1)
                    ],
                )
            seq += len(ops)
            db.execute(
                """UPDATE app.conductor_runs SET state=%s,last_seq=%s,status=%s,mode=%s,
                   updated_at=now() WHERE id=%s""",
                (Jsonb(state), seq, checked.status, checked.mode, run_id),
            )
        self.bus.publish(run_id, seq)
        return seq

    def events(self, run_id: str, after: int = 0, limit: int = 1000) -> list[tuple[int, Op]]:
        with self.database.connect() as db:
            rows = db.execute(
                """SELECT seq,op,path,value FROM app.conductor_events
                   WHERE run_id=%s AND seq>%s ORDER BY seq LIMIT %s""",
                (run_id, after, limit),
            ).fetchall()
        return [(r["seq"], Op(op=r["op"], path=r["path"], value=r["value"])) for r in rows]

    def snapshot(self, run_id: str) -> tuple[RunState, int]:
        with self.database.connect() as db:
            row = db.execute(
                "SELECT state,last_seq FROM app.conductor_runs WHERE id=%s", (run_id,)
            ).fetchone()
        if not row:
            raise RunNotFound(run_id)
        return RunState.model_validate(row["state"]), row["last_seq"]

    def interrupt_unfinished(self) -> list[str]:
        """At start-up: runs left mid-flight by a stopped server are marked interrupted
        (their logged results survive; the client offers to resume)."""
        with self.database.connect() as db:
            rows = db.execute(
                "SELECT id FROM app.conductor_runs WHERE status IN ('running','waiting')"
            ).fetchall()
        stopped = [str(r["id"]) for r in rows]
        for run_id in stopped:
            self.append(run_id, [set_(["status"], "interrupted")])
        return stopped


def is_finished(state: RunState) -> bool:
    return state.status in TERMINAL


def run_uuid(value: str) -> str:
    """Normalise and validate a run id from a client."""
    return str(UUID(value))
