"""Unattended run receipts. No executor, no human focus accounting."""

import hashlib
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from psycopg.types.json import Jsonb
from pydantic import Field

from .planning import LOCK
from .planning_models import Model
from .receivers import payload_fingerprint, receiver_access


class RunEvent(Model):
    event_key: UUID
    provider: str = Field(min_length=1, max_length=100)
    external_run_id: str = Field(min_length=1, max_length=200)
    sequence: int = Field(ge=0, strict=True)
    label: str = Field(min_length=1, max_length=180)
    state: Literal["queued", "running", "succeeded", "failed", "cancelled"]
    task_id: UUID | None = None
    task_version: int | None = Field(default=None, ge=1, strict=True)


class CancelRun(Model):
    key: UUID
    id: UUID
    version: int = Field(ge=1, strict=True)


def background_routers(database, session, tokens=None):
    access, configured = receiver_access("background", tokens)
    receiver = APIRouter(prefix="/v1/receivers/background", dependencies=[Depends(access)])
    owner = APIRouter(prefix="/v1/application/background", dependencies=[Depends(session)])

    @owner.get("")
    def list_runs(limit: int = Query(default=40, ge=1, le=100), before: UUID | None = None):
        with database.connect() as db:
            rows = db.execute(
                "SELECT *,CASE WHEN started_at IS NULL THEN 0 ELSE greatest(0,extract(epoch FROM (coalesce(ended_at,clock_timestamp())-started_at))) END AS elapsed_seconds FROM app.background_runs WHERE (%s::uuid IS NULL OR (created_at,id)<(SELECT created_at,id FROM app.background_runs WHERE id=%s)) ORDER BY created_at DESC,id DESC LIMIT %s",
                (before, before, limit + 1),
            ).fetchall()
            return {
                "runs": rows[:limit],
                "truncated": len(rows) > limit,
                "server_now": datetime.now(UTC),
                "receiver_connected": configured,
            }

    @receiver.post("/events")
    def receive(event: RunEvent):
        fingerprint = payload_fingerprint(event)
        with database.connect() as db:
            db.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK,))
            previous = db.execute(
                "SELECT * FROM app.receiver_receipts WHERE scope='background' AND event_key=%s",
                (str(event.event_key),),
            ).fetchone()
            if previous:
                if previous["fingerprint"] != fingerprint:
                    raise HTTPException(409, "This run event identity belongs to another payload.")
                return previous["result"]
            run = db.execute(
                "SELECT * FROM app.background_runs WHERE provider=%s AND external_run_id=%s FOR UPDATE",
                (event.provider, event.external_run_id),
            ).fetchone()
            if not run:
                if event.sequence != 0 or event.state not in ("queued", "running"):
                    raise HTTPException(
                        409, "A run starts with queued or running at sequence zero."
                    )
                if event.task_id:
                    task = db.execute(
                        "SELECT version FROM app.tasks WHERE id=%s", (event.task_id,)
                    ).fetchone()
                    if not task or task["version"] != event.task_version:
                        raise HTTPException(
                            409, "The associated task changed. Reconcile before starting this run."
                        )
                elif event.task_version is not None:
                    raise HTTPException(422, "A task version requires a task identity.")
                run = db.execute(
                    "INSERT INTO app.background_runs(task_id,provider,external_run_id,label,state,started_at) VALUES (%s,%s,%s,%s,%s,CASE WHEN %s='running' THEN now() END) RETURNING *",
                    (
                        event.task_id,
                        event.provider,
                        event.external_run_id,
                        event.label,
                        event.state,
                        event.state,
                    ),
                ).fetchone()
            else:
                if event.task_id != run["task_id"] or event.sequence != run["next_sequence"]:
                    raise HTTPException(
                        409, "Run events must preserve the task and arrive in sequence."
                    )
                allowed = {
                    "queued": {"running", "failed", "cancelled"},
                    "running": {"running", "succeeded", "failed", "cancelled"},
                }
                if event.state not in allowed.get(run["state"], set()):
                    raise HTTPException(
                        409, "This run is finished or the state transition is invalid."
                    )
                run = db.execute(
                    "UPDATE app.background_runs SET state=%s,label=%s,started_at=CASE WHEN %s='running' THEN coalesce(started_at,clock_timestamp()) ELSE started_at END,ended_at=CASE WHEN %s IN ('succeeded','failed','cancelled') THEN clock_timestamp() END,next_sequence=next_sequence+1,version=version+1 WHERE id=%s RETURNING *",
                    (event.state, event.label, event.state, event.state, run["id"]),
                ).fetchone()
            result = jsonable_encoder({"run": run})
            db.execute(
                "INSERT INTO app.receiver_receipts(scope,event_key,fingerprint,result) VALUES ('background',%s,%s,%s)",
                (str(event.event_key), fingerprint, Jsonb(result)),
            )
            return result

    @receiver.get("/cancellations")
    def cancellations(provider: str = Query(min_length=1, max_length=100)):
        with database.connect() as db:
            return {
                "runs": db.execute(
                    "SELECT id,external_run_id,version,cancellation_requested_at FROM app.background_runs WHERE provider=%s AND cancellation_requested_at IS NOT NULL AND state IN ('queued','running') ORDER BY cancellation_requested_at LIMIT 100",
                    (provider,),
                ).fetchall()
            }

    @owner.post("/cancel")
    def cancel(command: CancelRun):
        fingerprint = hashlib.sha256(
            ("run-cancel:" + command.model_dump_json(exclude={"key"})).encode()
        ).hexdigest()
        with database.connect() as db:
            db.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK,))
            previous = db.execute(
                "SELECT * FROM app.planning_commands WHERE id=%s", (command.key,)
            ).fetchone()
            if previous:
                if previous["fingerprint"] != fingerprint:
                    raise HTTPException(409, "Retry identity belongs to another change.")
                return previous["result"]
            run = db.execute(
                "SELECT * FROM app.background_runs WHERE id=%s FOR UPDATE", (command.id,)
            ).fetchone()
            if not run:
                raise HTTPException(404, "Background run not found.")
            if command.version != run["version"] or run["state"] not in ("queued", "running"):
                raise HTTPException(409, "This run changed or finished. Refresh its state.")
            changed = db.execute(
                "UPDATE app.background_runs SET cancellation_requested_at=coalesce(cancellation_requested_at,clock_timestamp()),version=version+1 WHERE id=%s RETURNING *",
                (run["id"],),
            ).fetchone()
            result = jsonable_encoder(
                {
                    "run": changed,
                    "message": "Cancellation requested. The run remains active until its provider confirms.",
                }
            )
            db.execute(
                "INSERT INTO app.planning_commands(id,fingerprint,result) VALUES (%s,%s,%s)",
                (command.key, fingerprint, Jsonb(result)),
            )
            return result

    return owner, receiver
