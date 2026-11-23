"""The durable event log behind every run.

A run's state changes only by appending ops here. Each op gets the next sequence
number, so a client that disconnects (closed tab, dropped network) reconnects by
asking for everything after the last seq it saw and rebuilds the same state.

The two ops mirror assistant-stream's state protocol [cited]: `set` a value at a path
and `append-text` to a string at a path. `apply` is pure; the web client applies the
same ops with the same rules (web/src/features/chat/runtime/ops.ts).

Guarantees of `append`, all checked inside one row-locked transaction:
- the result validates against RunState (strict),
- the stored snapshot is byte-for-byte what a client gets by replaying the ops (ops
  must set complete objects, so schema defaults never diverge),
- every change is a legal forward move (state.check_moves); a finished run is frozen.
"""

from __future__ import annotations

import logging
import math
import threading
import time
from typing import Any, Literal
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .state import TERMINAL, RunState, check_moves

LOG = logging.getLogger(__name__)
Path = list[str | int]
HEARTBEAT_STALE_SECONDS = 90


def _clean(value: Any) -> Any:
    """Postgres jsonb rejects NUL characters and non-finite numbers: refuse or strip them
    at the door rather than failing a run mid-flight."""
    if isinstance(value, str):
        return value.replace("\x00", "")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("Non-finite numbers cannot be stored.")
    if isinstance(value, dict):
        return {_clean(k): _clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    return value


class Op(BaseModel):
    model_config = ConfigDict(extra="forbid")
    op: Literal["set", "append-text"]
    path: Path = Field(min_length=1, max_length=8)
    value: Any = None

    @field_validator("value")
    @classmethod
    def _storable(cls, value: Any) -> Any:
        return _clean(value)


def set_(path: Path, value: Any) -> Op:
    """Set a value. A dict value must be a complete object (model_dump(mode="json"))."""
    return Op(op="set", path=path, value=value)


def append_text(path: Path, text: str) -> Op:
    return Op(op="append-text", path=path, value=text)


def _child(node: Any, key: str | int, *, for_set: bool = False) -> Any:
    if isinstance(node, list):
        if not isinstance(key, int) or isinstance(key, bool) or key < 0:
            raise ValueError(f"List paths need a non-negative integer, got {key!r}.")
        limit = len(node) if for_set else len(node) - 1
        if key > limit:
            raise ValueError(f"Index {key} is past the end of a list of {len(node)}.")
        return key
    if isinstance(node, dict):
        if not isinstance(key, str):
            # One error type for every bad path, as the web client raises.
            raise ValueError(f"Object paths need a string key, got {key!r}.")  # noqa: TRY004
        if not for_set and key not in node:
            raise ValueError(f"No key {key!r} at this path.")
        return key
    raise ValueError("The path goes through a value that is not a list or object.")


def apply(state: dict, op: Op) -> dict:
    """Apply one op to a JSON state in place (and return it). Lists grow only by setting
    exactly one past the end; negative or out-of-range indexes are refused."""
    *parents, last = op.path
    node: Any = state
    for key in parents:
        node = node[_child(node, key)]
    if op.op == "set":
        key = _child(node, last, for_set=True)
        if isinstance(node, list) and key == len(node):
            node.append(op.value)
        else:
            node[key] = op.value
    else:
        key = _child(node, last)
        if not isinstance(op.value, str) or not isinstance(node[key], str):
            raise ValueError("append-text needs a string target and a string value.")
        node[key] += op.value
    return state


class RunNotFound(LookupError):
    pass


class Bus:
    """Wakes in-process listeners when a run's log grows. Durability is the database's
    job; this only saves a live stream from polling. One condition per run, dropped
    when the run finishes."""

    def __init__(self):
        self._lock = threading.Lock()
        self._runs: dict[str, tuple[threading.Condition, list[int]]] = {}
        self._closed: dict[str, float] = {}

    def _entry(self, run_id: str) -> tuple[threading.Condition, list[int]]:
        with self._lock:
            if run_id not in self._runs:
                self._runs[run_id] = (threading.Condition(), [0])
            return self._runs[run_id]

    def publish(self, run_id: str, seq: int) -> None:
        condition, latest = self._entry(run_id)
        with condition:
            latest[0] = max(seq, latest[0])
            condition.notify_all()

    def wait(self, run_id: str, after: int, timeout: float) -> bool:
        """True once the run has events after `after`; False on timeout."""
        condition, latest = self._entry(run_id)
        with condition:
            return condition.wait_for(lambda: latest[0] > after, timeout=timeout)

    def close(self, run_id: str) -> None:
        """The run finished: wake every waiter and keep answering "there is more" so a
        waiter arriving after the last event never sleeps (no lost wake-up)."""
        condition, latest = self._entry(run_id)
        with condition:
            latest[0] = 1 << 62
            condition.notify_all()
        with self._lock:
            self._closed[run_id] = time.monotonic()

    def prune(self, older_than: float = 600.0) -> None:
        """Forget runs that finished more than `older_than` seconds ago."""
        cutoff = time.monotonic() - older_than
        with self._lock:
            for run_id in [r for r, at in self._closed.items() if at < cutoff]:
                self._closed.pop(run_id, None)
                self._runs.pop(run_id, None)


def record_judgements(db, run_id: str, before: RunState, after: RunState) -> None:
    """Every approval card Manoj answers is a judgement (migration 045), written in the
    same transaction as the run change that records the answer. A card that timed out
    (decided_by is not 'user') is not his verdict and is not recorded."""
    earlier = {t.id: t.state for t in before.tools}
    for tool in after.tools:
        if (
            tool.state == "approval-responded"
            and tool.decided_by == "user"
            and tool.approval is not None
            and earlier.get(tool.id) != "approval-responded"
        ):
            key = f"{run_id}:{tool.id}"
            db.execute(
                "INSERT INTO app.judgements(subject_kind,subject_key,verdict,reason,"
                "source_table,source_id) VALUES ('conductor_tool',%s,%s,%s,'conductor_runs',%s) "
                "ON CONFLICT (source_table, source_id) DO NOTHING",
                (key, "approved" if tool.approval.approved else "rejected",
                 tool.approval.reason or None, key),
            )  # fmt: skip


class RunLog:
    def __init__(self, database, bus: Bus | None = None):
        self.database = database
        self.bus = bus or Bus()

    def start(self, state: RunState, request: str, owner: str) -> None:
        with self.database.connect() as db:
            db.execute(
                """INSERT INTO app.conductor_runs
                   (id,conversation_id,request,status,mode,state,owner,heartbeat_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,now())""",
                (
                    state.run_id,
                    state.conversation_id,
                    request,
                    state.status,
                    state.mode,
                    Jsonb(state.model_dump(mode="json")),
                    owner,
                ),
            )

    def append(self, run_id: str, ops: list[Op], owner: str | None = None) -> int:
        """Append ops atomically; returns the new last seq. `owner` refreshes the run's
        heartbeat (the process that executes it)."""
        if not ops:
            raise ValueError("Nothing to append.")
        with self.database.connect() as db:
            row = db.execute(
                "SELECT state,last_seq FROM app.conductor_runs WHERE id=%s FOR UPDATE",
                (run_id,),
            ).fetchone()
            if not row:
                raise RunNotFound(run_id)
            before = RunState.model_validate(row["state"])
            # The stored shape, upgraded to the current model (a row written before a new
            # optional field existed gains it with its default; nothing else changes).
            state = before.model_dump(mode="json")
            for op in ops:
                apply(state, op)
            after = RunState.model_validate(state)
            if after.model_dump(mode="json") != state:
                raise ValueError("Ops must set complete objects (use model_dump(mode='json')).")
            check_moves(before, after)
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
                   updated_at=now(),
                   heartbeat_at=CASE WHEN %s::text IS NULL THEN heartbeat_at ELSE now() END,
                   owner=COALESCE(%s,owner)
                   WHERE id=%s""",
                (Jsonb(state), seq, after.status, after.mode, owner, owner, run_id),
            )
            record_judgements(db, run_id, before, after)
        self.bus.publish(run_id, seq)
        if after.status in TERMINAL:
            self.bus.close(run_id)
        return seq

    def heartbeat(self, run_id: str, owner: str) -> None:
        with self.database.connect() as db:
            db.execute(
                "UPDATE app.conductor_runs SET heartbeat_at=now() WHERE id=%s AND owner=%s",
                (run_id, owner),
            )

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

    def runs_for(self, conversation_id: str) -> list[tuple[RunState, int]]:
        with self.database.connect() as db:
            rows = db.execute(
                """SELECT state,last_seq FROM app.conductor_runs WHERE conversation_id=%s
                   ORDER BY created_at""",
                (conversation_id,),
            ).fetchall()
        return [(RunState.model_validate(r["state"]), r["last_seq"]) for r in rows]

    def requests_for(self, conversation_id: str) -> dict[str, tuple[str, Any]]:
        """run id -> (request text, created_at)."""
        with self.database.connect() as db:
            rows = db.execute(
                "SELECT id,request,created_at FROM app.conductor_runs WHERE conversation_id=%s",
                (conversation_id,),
            ).fetchall()
        return {str(r["id"]): (r["request"], r["created_at"]) for r in rows}

    def is_stale(self, run_id: str, stale_seconds: int = HEARTBEAT_STALE_SECONDS) -> bool:
        with self.database.connect() as db:
            row = db.execute(
                """SELECT heartbeat_at < now() - make_interval(secs => %s) AS stale
                   FROM app.conductor_runs WHERE id=%s""",
                (stale_seconds, run_id),
            ).fetchone()
        return bool(row and row["stale"])

    def interrupt_stale(self, stale_seconds: int = HEARTBEAT_STALE_SECONDS) -> list[str]:
        """Runs whose executing process stopped heartbeating are marked interrupted, one
        at a time and only if still stale (a live run elsewhere is never touched).
        A waiting run's worker heartbeats too, so a stale waiting run is orphaned."""
        with self.database.connect() as db:
            rows = db.execute(
                """SELECT id FROM app.conductor_runs WHERE status IN ('running','waiting')
                   AND heartbeat_at < now() - make_interval(secs => %s)""",
                (stale_seconds,),
            ).fetchall()
        stopped = []
        for row in rows:
            run_id = str(row["id"])
            try:
                with self.database.connect() as db:
                    still = db.execute(
                        """SELECT 1 FROM app.conductor_runs WHERE id=%s AND status IN ('running','waiting')
                           AND heartbeat_at < now() - make_interval(secs => %s)""",
                        (run_id, stale_seconds),
                    ).fetchone()
                if still:
                    self.append(run_id, [set_(["status"], "interrupted")])
                    stopped.append(run_id)
            except (ValueError, psycopg.Error):  # one bad run must not block start-up
                LOG.warning("Could not mark run %s interrupted.", run_id, exc_info=True)
        return stopped


def is_finished(state: RunState) -> bool:
    return state.status in TERMINAL


def run_uuid(value: str) -> str:
    """Normalise and validate a run id from a client."""
    return str(UUID(value))
