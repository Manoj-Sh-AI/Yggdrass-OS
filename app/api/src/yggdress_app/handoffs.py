"""Lia's date/context inbox for future Yggdras routing. No work is created here."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from psycopg.types.json import Jsonb
from pydantic import Field

from .connections import verified_note
from .planning import LOCK
from .planning_models import Model
from .receivers import payload_fingerprint, receiver_access


class DateContext(Model):
    meaning: Literal[
        "deadline",
        "appointment",
        "availability",
        "review",
        "preference",
        "recurrence",
        "historical",
        "cancellation",
        "uncertain",
    ]
    precision: Literal["date", "datetime", "interval", "month", "year", "relative", "unspecified"]
    value: dict = Field(default_factory=dict)
    anchor: str = Field(default="", max_length=1000)
    original_phrase: str = Field(default="", max_length=2000)
    uncertainty: str = Field(default="", max_length=2000)


class NoteHandoff(Model):
    id: UUID
    producer: str = Field(min_length=1, max_length=100)
    namespace: str = Field(min_length=1, max_length=100)
    external_identity: str = Field(min_length=1, max_length=200)
    sequence: int = Field(ge=0, strict=True)
    previous_revision: str | None = Field(default=None, max_length=200)
    revision: str = Field(min_length=1, max_length=200)
    slug: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,200}$")
    lifecycle: Literal["active", "archived", "missing"] = "active"
    context: str = Field(default="", max_length=4000)
    dates: list[DateContext] = Field(default_factory=list, max_length=100)


class AcknowledgeHandoff(Model):
    id: UUID


def handoff_routers(database, notes, tokens=None):
    lia, _ = receiver_access("note_signals", tokens)
    dispatch, _ = receiver_access("workflow_dispatch", tokens)
    inbox = APIRouter(prefix="/v1/receivers/note-signals", dependencies=[Depends(lia)])
    outbox = APIRouter(prefix="/v1/receivers/handoffs", dependencies=[Depends(dispatch)])

    @inbox.post("")
    def receive(event: NoteHandoff):
        fingerprint = payload_fingerprint(event)
        with database.connect() as db:
            existing = db.execute(
                "SELECT fingerprint FROM app.note_handoffs WHERE id=%s", (event.id,)
            ).fetchone()
            if existing:
                if existing["fingerprint"] != fingerprint:
                    raise HTTPException(409, "This handoff identity belongs to another payload.")
                return {"id": str(event.id), "saved": True, "work_changed": False}
        note = verified_note(notes, event.slug) if event.lifecycle == "active" else None
        if note and note["version"] != event.revision:
            raise HTTPException(
                409, "The source note changed before this handoff. Send its current revision."
            )
        with database.connect() as db:
            db.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK,))
            existing = db.execute(
                "SELECT fingerprint FROM app.note_handoffs WHERE id=%s", (event.id,)
            ).fetchone()
            if existing:
                if existing["fingerprint"] != fingerprint:
                    raise HTTPException(409, "This handoff identity belongs to another payload.")
                return {"id": str(event.id), "saved": True, "work_changed": False}
            previous = db.execute(
                "SELECT * FROM app.note_handoffs WHERE producer=%s AND namespace=%s AND external_identity=%s ORDER BY sequence DESC LIMIT 1",
                (event.producer, event.namespace, event.external_identity),
            ).fetchone()
            if previous and (
                event.sequence != previous["sequence"] + 1
                or event.previous_revision != previous["revision"]
            ):
                raise HTTPException(
                    409, "Deliver source handoffs in order against the previous revision."
                )
            if not previous and (
                event.sequence != 0
                or event.previous_revision is not None
                or event.lifecycle != "active"
            ):
                raise HTTPException(
                    409,
                    "The first handoff must identify an active readable source at sequence zero.",
                )
            # Keep every revision until the future router acknowledges it. Reading is not deletion.
            db.execute(
                "INSERT INTO app.note_handoffs(id,producer,namespace,external_identity,slug,revision,sequence,lifecycle,fingerprint,payload) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    event.id,
                    event.producer,
                    event.namespace,
                    event.external_identity,
                    event.slug,
                    event.revision,
                    event.sequence,
                    event.lifecycle,
                    fingerprint,
                    Jsonb(event.model_dump(mode="json")),
                ),
            )
            return {"id": str(event.id), "saved": True, "work_changed": False}

    @outbox.get("")
    def pending(limit: int = Query(default=50, ge=1, le=100)):
        with database.connect() as db:
            rows = db.execute(
                "SELECT id,payload,received_at FROM app.note_handoffs WHERE state='pending' ORDER BY received_at,id LIMIT %s",
                (limit + 1,),
            ).fetchall()
            return {"handoffs": rows[:limit], "truncated": len(rows) > limit}

    @outbox.post("/acknowledge")
    def acknowledge(command: AcknowledgeHandoff):
        with database.connect() as db:
            row = db.execute(
                "UPDATE app.note_handoffs SET state='acknowledged',acknowledged_at=coalesce(acknowledged_at,now()) WHERE id=%s RETURNING id",
                (command.id,),
            ).fetchone()
            if not row:
                raise HTTPException(404, "Handoff not found.")
            return {"id": str(command.id), "acknowledged": True}

    return inbox, outbox
