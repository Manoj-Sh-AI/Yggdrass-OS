"""Application relationships and bounded context reads. Never writes to Brain."""

import hashlib
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from psycopg import sql
from psycopg.types.json import Jsonb
from pydantic import Field, model_validator

from .notes_proxy import NotesError, note_view, slug_path
from .planning import LOCK, command_result, refresh_reminders
from .planning_models import Command, Model, TaskInput, TimeInput
from .temporal import DateItemInput, TimeCommand, temporal_result

ENTITIES = {
    "task": ("tasks", "task_note_links", "task_id"),
    "event": ("calendar_events", "event_note_links", "event_id"),
    "date_item": ("calendar_date_items", "date_item_note_links", "date_item_id"),
    "availability": ("availability_windows", "availability_note_links", "availability_id"),
}


class ConnectionCommand(Model):
    key: UUID
    operation: Literal[
        "task.link_note",
        "task.unlink_note",
        "event.link_note",
        "event.unlink_note",
        "event.link_task",
        "event.unlink_task",
        "date_item.link_note",
        "date_item.unlink_note",
        "availability.link_note",
        "availability.unlink_note",
    ]
    entity_id: UUID
    version: int = Field(ge=1, strict=True)
    note_slug: str | None = Field(default=None, pattern=r"^[a-zA-Z0-9_-]{1,200}$")
    relation: Literal["source", "context", "result"] = "context"
    task_id: UUID | None = None
    task_version: int | None = Field(default=None, ge=1, strict=True)

    @model_validator(mode="after")
    def target(self):
        if self.operation.endswith("_note"):
            if not self.note_slug or self.task_id is not None or self.task_version is not None:
                raise ValueError("A note link requires only a note slug and relation.")
        elif (
            self.task_id is None
            or self.task_version is None
            or self.note_slug is not None
            or self.relation != "context"
        ):
            raise ValueError("An event/task link requires the task ID and current task version.")
        return self


class FromNoteCommand(Model):
    key: UUID
    operation: Literal["task.create", "event.create", "date_item.create", "availability.create"]
    note_slug: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,200}$")
    note_revision: str = Field(min_length=1, max_length=200)
    task: TaskInput | None = None
    event: TimeInput | None = None
    date_item: DateItemInput | None = None
    availability: TimeInput | None = None

    @model_validator(mode="after")
    def payload(self):
        selected = self.operation.partition(".")[0]
        fields = {kind: getattr(self, kind) for kind in ENTITIES}
        if fields[selected] is None or sum(value is not None for value in fields.values()) != 1:
            raise ValueError("Provide only the selected kind of work to create from this note.")
        if selected in ("event", "availability"):
            body = fields[selected]
            if (
                body.task_id is not None
                or not body.title
                or (body.end is None and body.duration_minutes is None)
            ):
                raise ValueError(
                    "A time interval needs its own title and an explicit end or duration."
                )
        return self


def observe_note(db, slug, note):
    return db.execute(
        "INSERT INTO app.note_refs(external_id,observed_title,observed_revision) "
        "VALUES (%s,%s,%s) ON CONFLICT(source,external_id) DO UPDATE SET "
        "observed_title=EXCLUDED.observed_title, observed_revision=EXCLUDED.observed_revision, "
        "last_verified_at=now() RETURNING *",
        (slug, note["title"], note["version"]),
    ).fetchone()


def verified_note(notes, slug):
    note = note_view(notes.http.call("GET", slug_path(slug)), slug)
    if note["slug"] != slug:
        raise NotesError(502, "The Brain returned a different note. No work was linked.")
    return note


def receipt(db, key, fingerprint):
    row = db.execute("SELECT * FROM app.planning_commands WHERE id=%s", (key,)).fetchone()
    if not row:
        return None
    if row["fingerprint"] != fingerprint:
        raise HTTPException(409, "This request key was already used for a different change.")
    return row["result"]


def target(db, table, identifier, version):
    row = db.execute(
        sql.SQL("SELECT * FROM app.{} WHERE id=%s FOR UPDATE").format(sql.Identifier(table)),
        (identifier,),
    ).fetchone()
    if not row:
        raise HTTPException(404, "The application item was not found.")
    if row["version"] != version:
        raise HTTPException(409, "This item changed. Refresh before changing its connections.")
    return row


def bump(db, table, identifier):
    return db.execute(
        sql.SQL("UPDATE app.{} SET version=version+1 WHERE id=%s RETURNING version").format(
            sql.Identifier(table)
        ),
        (identifier,),
    ).fetchone()["version"]


def change_link(db, command, verified_note):
    kind = command.operation.partition(".")[0]
    parent_table, note_links, note_key = ENTITIES[kind]
    parent = target(db, parent_table, command.entity_id, command.version)
    attaching = ".link_" in command.operation
    if attaching and kind != "task" and parent["cancelled"]:
        raise HTTPException(409, "This event is cancelled. Restore or choose another event.")
    if command.operation.endswith("_task"):
        child = target(db, "tasks", command.task_id, command.task_version)
        existing = db.execute(
            "SELECT id FROM app.event_task_links WHERE event_id=%s AND task_id=%s",
            (parent["id"], child["id"]),
        ).fetchone()
        table, parent_key = "event_task_links", "event_id"
        values = {"event_id": parent["id"], "task_id": child["id"]}
        reference = None
    else:
        table, parent_key = note_links, note_key
        reference = db.execute(
            "SELECT * FROM app.note_refs WHERE source='brain' AND external_id=%s",
            (command.note_slug,),
        ).fetchone()
        existing = None
        if reference:
            existing = db.execute(
                sql.SQL("SELECT id FROM app.{} WHERE {}=%s AND note_ref_id=%s AND kind=%s").format(
                    sql.Identifier(table), sql.Identifier(parent_key)
                ),
                (parent["id"], reference["id"], command.relation),
            ).fetchone()
        values = {parent_key: parent["id"], "kind": command.relation}
    if bool(existing) == attaching:
        return {
            "changed": False,
            "version": parent["version"],
            "link_id": str(existing["id"]) if existing else None,
        }
    if attaching:
        if command.operation.endswith("_note"):
            reference = observe_note(db, command.note_slug, verified_note)
            values["note_ref_id"] = reference["id"]
            values["source_revision"] = verified_note["version"]
        fields = list(values)
        link = db.execute(
            sql.SQL("INSERT INTO app.{} ({}) VALUES ({}) RETURNING id").format(
                sql.Identifier(table),
                sql.SQL(",").join(map(sql.Identifier, fields)),
                sql.SQL(",").join(sql.Placeholder() for _ in fields),
            ),
            list(values.values()),
        ).fetchone()
    else:
        link = db.execute(
            sql.SQL("DELETE FROM app.{} WHERE id=%s RETURNING id").format(sql.Identifier(table)),
            (existing["id"],),
        ).fetchone()
    result = {
        "changed": True,
        "version": bump(db, parent_table, parent["id"]),
        "link_id": str(link["id"]),
    }
    if command.operation.endswith("_task"):
        result["task_version"] = bump(db, "tasks", child["id"])
    if reference:
        result["note_ref_id"] = str(reference["id"])
    return result


def limited(rows, limit):
    return rows[:limit], len(rows) > limit


def connections_router(database, notes, session):
    router = APIRouter(prefix="/v1/application/connections", dependencies=[Depends(session)])

    @router.get("/capabilities")
    def capabilities():
        with database.connect() as db:
            available = (
                db.execute(
                    "SELECT count(*) AS n FROM information_schema.columns WHERE table_schema='app' "
                    "AND table_name IN ('task_note_links','event_note_links') AND column_name='source_revision'"
                ).fetchone()["n"]
                == 2
            )
        return {"linked_work": available, "automatic_interpretation": False}

    @router.post("/from-note")
    def create_from_note(command: FromNoteCommand):
        fingerprint = hashlib.sha256(
            ("from-note:" + command.model_dump_json(exclude={"key"})).encode()
        ).hexdigest()
        with database.connect() as db:
            replay = receipt(db, command.key, fingerprint)
            if replay is not None:
                return replay
        # Read Brain server-side before opening the application transaction. The
        # saved revision is provenance, not a cross-database atomicity guarantee.
        verified = verified_note(notes, command.note_slug)
        if verified["version"] != command.note_revision:
            raise HTTPException(
                409, "The source note changed. Refresh it before creating linked work."
            )
        with database.connect() as db:
            db.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK,))
            replay = receipt(db, command.key, fingerprint)
            if replay is not None:
                return replay
            db.execute("SELECT set_config('yggdress.command_id',%s,true)", (str(command.key),))
            kind = command.operation.partition(".")[0]
            body = getattr(command, kind)
            if kind in ("task", "event"):
                created = command_result(
                    db,
                    Command(
                        key=command.key, op=command.operation, data=body.model_dump(mode="json")
                    ),
                )
            else:
                created = temporal_result(
                    db,
                    TimeCommand(
                        key=command.key,
                        operation=command.operation,
                        data=body.model_dump(mode="json"),
                    ),
                )
            reference = observe_note(db, command.note_slug, verified)
            _, table, field = ENTITIES[kind]
            link = db.execute(
                sql.SQL(
                    "INSERT INTO app.{} ({},note_ref_id,kind,source_revision) "
                    "VALUES (%s,%s,'source',%s) RETURNING id"
                ).format(sql.Identifier(table), sql.Identifier(field)),
                (created["id"], reference["id"], command.note_revision),
            ).fetchone()
            refresh_reminders(db)
            result = jsonable_encoder(
                {
                    **created,
                    "link_id": link["id"],
                    "note_ref_id": reference["id"],
                    "source_revision": command.note_revision,
                }
            )
            db.execute(
                "INSERT INTO app.planning_commands(id,fingerprint,result) VALUES (%s,%s,%s)",
                (command.key, fingerprint, Jsonb(result)),
            )
            return result

    @router.post("/commands")
    def mutate(command: ConnectionCommand):
        fingerprint = hashlib.sha256(
            ("connections:" + command.model_dump_json(exclude={"key"})).encode()
        ).hexdigest()
        # Replays do not depend on Brain availability; don't hold database locks over HTTP.
        with database.connect() as db:
            replay = receipt(db, command.key, fingerprint)
            if replay is not None:
                return replay
        verified = None
        if command.operation.endswith(".link_note"):
            verified = verified_note(notes, command.note_slug)
        with database.connect() as db:
            db.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK,))
            replay = receipt(db, command.key, fingerprint)
            if replay is not None:
                return replay
            db.execute("SELECT set_config('yggdress.command_id',%s,true)", (str(command.key),))
            result = jsonable_encoder(change_link(db, command, verified))
            db.execute(
                "INSERT INTO app.planning_commands(id,fingerprint,result) VALUES (%s,%s,%s)",
                (command.key, fingerprint, Jsonb(result)),
            )
            return result

    @router.get("/notes/{slug}")
    def for_note(slug: str, limit: int = Query(default=40, ge=1, le=100)):
        slug_path(slug)  # Same identifier validation as the existing Notes API.
        with database.connect() as db:
            db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            note = db.execute(
                "SELECT * FROM app.note_refs WHERE source='brain' AND external_id=%s",
                (slug,),
            ).fetchone()
            if not note:
                return {
                    "note_ref": None,
                    "tasks": [],
                    "events": [],
                    "truncated": {"tasks": False, "events": False},
                }
            tasks, more_tasks = limited(
                db.execute(
                    "SELECT t.id,t.title,t.objective,t.state,t.done,t.due_date,t.deadline_at,t.version,l.kind,l.source_revision "
                    "FROM app.task_note_links l JOIN app.tasks t ON t.id=l.task_id "
                    "WHERE l.note_ref_id=%s ORDER BY t.id,l.kind LIMIT %s",
                    (note["id"], limit + 1),
                ).fetchall(),
                limit,
            )
            events, more_events = limited(
                db.execute(
                    "SELECT e.*,l.kind,l.source_revision FROM app.event_note_links l JOIN app.calendar_events e ON e.id=l.event_id "
                    "WHERE l.note_ref_id=%s ORDER BY e.starts_at,e.id,l.kind LIMIT %s",
                    (note["id"], limit + 1),
                ).fetchall(),
                limit,
            )
            date_items, more_dates = limited(
                db.execute(
                    "SELECT d.*,l.kind AS relation,l.source_revision FROM app.date_item_note_links l JOIN app.calendar_date_items d ON d.id=l.date_item_id WHERE l.note_ref_id=%s ORDER BY d.starts_on,d.id,l.kind LIMIT %s",
                    (note["id"], limit + 1),
                ).fetchall(),
                limit,
            )
            availability, more_availability = limited(
                db.execute(
                    "SELECT a.*,l.kind AS relation,l.source_revision FROM app.availability_note_links l JOIN app.availability_windows a ON a.id=l.availability_id WHERE l.note_ref_id=%s ORDER BY a.starts_at,a.id,l.kind LIMIT %s",
                    (note["id"], limit + 1),
                ).fetchall(),
                limit,
            )
            return {
                "note_ref": note,
                "tasks": tasks,
                "events": events,
                "date_items": date_items,
                "availability": availability,
                "truncated": {
                    "tasks": more_tasks,
                    "events": more_events,
                    "date_items": more_dates,
                    "availability": more_availability,
                },
            }

    @router.get("/calendar-context/{kind}/{identifier}")
    def for_calendar_item(
        kind: Literal["date_item", "availability"],
        identifier: UUID,
        limit: int = Query(default=40, ge=1, le=100),
    ):
        entity_table, link_table, field = ENTITIES[kind]
        with database.connect() as db:
            db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            if not db.execute(
                f"SELECT 1 FROM app.{entity_table} WHERE id=%s", (identifier,)
            ).fetchone():
                raise HTTPException(404, "Calendar item not found.")
            rows, more = limited(
                db.execute(
                    f"SELECT n.*,l.kind,l.source_revision FROM app.{link_table} l JOIN app.note_refs n ON n.id=l.note_ref_id WHERE l.{field}=%s ORDER BY n.id,l.kind LIMIT %s",
                    (identifier, limit + 1),
                ).fetchall(),
                limit,
            )
            return {"notes": rows, "truncated": {"notes": more}}

    @router.get("/tasks/{task_id}")
    def for_task(task_id: UUID, limit: int = Query(default=40, ge=1, le=100)):
        with database.connect() as db:
            db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            if not db.execute("SELECT 1 FROM app.tasks WHERE id=%s", (task_id,)).fetchone():
                raise HTTPException(404, "Task not found.")
            refs, more_refs = limited(
                db.execute(
                    "SELECT n.*,l.kind,l.source_revision FROM app.task_note_links l JOIN app.note_refs n ON n.id=l.note_ref_id "
                    "WHERE l.task_id=%s ORDER BY n.id,l.kind LIMIT %s",
                    (task_id, limit + 1),
                ).fetchall(),
                limit,
            )
            events, more_events = limited(
                db.execute(
                    "SELECT e.* FROM app.event_task_links l JOIN app.calendar_events e ON e.id=l.event_id "
                    "WHERE l.task_id=%s ORDER BY e.starts_at,e.id LIMIT %s",
                    (task_id, limit + 1),
                ).fetchall(),
                limit,
            )
            runs, more_runs = limited(
                db.execute(
                    "SELECT *,CASE WHEN started_at IS NULL THEN 0 ELSE greatest(0,extract(epoch FROM "
                    "(coalesce(ended_at,now())-started_at))) END AS elapsed_seconds "
                    "FROM app.background_runs WHERE task_id=%s ORDER BY created_at DESC,id LIMIT %s",
                    (task_id, limit + 1),
                ).fetchall(),
                limit,
            )
            return {
                "notes": refs,
                "events": events,
                "background_runs": runs,
                "truncated": {
                    "notes": more_refs,
                    "events": more_events,
                    "background_runs": more_runs,
                },
            }

    @router.get("/events/{event_id}")
    def for_event(event_id: UUID, limit: int = Query(default=40, ge=1, le=100)):
        with database.connect() as db:
            db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            if not db.execute(
                "SELECT 1 FROM app.calendar_events WHERE id=%s", (event_id,)
            ).fetchone():
                raise HTTPException(404, "Event not found.")
            refs, more_refs = limited(
                db.execute(
                    "SELECT n.*,l.kind,l.source_revision FROM app.event_note_links l JOIN app.note_refs n ON n.id=l.note_ref_id "
                    "WHERE l.event_id=%s ORDER BY n.id,l.kind LIMIT %s",
                    (event_id, limit + 1),
                ).fetchall(),
                limit,
            )
            tasks, more_tasks = limited(
                db.execute(
                    "SELECT t.id,t.title,t.objective,t.state,t.done,t.version FROM app.event_task_links l "
                    "JOIN app.tasks t ON t.id=l.task_id WHERE l.event_id=%s ORDER BY t.id LIMIT %s",
                    (event_id, limit + 1),
                ).fetchall(),
                limit,
            )
            return {
                "notes": refs,
                "tasks": tasks,
                "truncated": {"notes": more_refs, "tasks": more_tasks},
            }

    return router
