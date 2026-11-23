"""Narrow application tools. Models propose; only reviewed code mutates records."""

from datetime import date
from typing import Literal
from uuid import UUID

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from psycopg import sql
from pydantic import Field, model_validator

from .planning import LOCK, command_result, history, refresh_reminders, update
from .planning_models import Command, ExecutionInput, Model, TaskInput, TimeInput
from .temporal import DateItemInput, TimeCommand, temporal_result


class Proposal(Model):
    operation: Literal[
        "task.create",
        "task.update",
        "task.execute",
        "task.cancel",
        "event.create",
        "event.update",
        "event.remove",
        "date_item.create",
        "date_item.update",
        "date_item.remove",
        "availability.create",
        "availability.update",
        "availability.remove",
        "block.create",
        "block.update",
        "block.remove",
    ]
    id: UUID | None = None
    version: int | None = Field(default=None, ge=1, strict=True)
    data: dict = Field(default_factory=dict)
    explanation: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def valid(self):
        create = self.operation.endswith(".create")
        if create and (self.id is not None or self.version is not None):
            raise ValueError("Creation cannot identify an existing item.")
        if not create and (self.id is None or self.version is None):
            raise ValueError("An existing item requires its exact version.")
        if self.operation.endswith((".remove", ".cancel")):
            if self.data:
                raise ValueError("Removal has no extra fields.")
        elif self.operation == "task.execute":
            body = ExecutionInput.model_validate(self.data)
            if body.action not in ("complete", "progress", "reopen") or body.block_id:
                raise ValueError("Focus and timer actions require the explicit task controls.")
        else:
            kind = self.operation.partition(".")[0]
            if (
                create
                and (kind in ("event", "availability", "block") or self.data.get("deadline_at"))
                and not self.data.get("timezone")
            ):
                raise ValueError("An exact time requires an explicit named timezone.")
            schema = (
                TaskInput if kind == "task" else DateItemInput if kind == "date_item" else TimeInput
            )
            body = schema.model_validate(self.data)
            if kind == "block":
                # A task's time block: the task it belongs to, an exact interval, no title.
                if (
                    (create and not body.task_id)
                    or (not create and body.task_id)
                    or (body.end is None and body.duration_minutes is None)
                    or body.start.tzinfo is None
                    or (body.end is not None and body.end.tzinfo is None)
                ):
                    raise ValueError(
                        "A task block needs its task and an exact offset-aware interval."
                    )
            elif isinstance(body, TimeInput) and (
                not body.title
                or body.task_id
                or (body.end is None and body.duration_minutes is None)
                or body.start.tzinfo is None
                or (body.end is not None and body.end.tzinfo is None)
            ):
                raise ValueError("An appointment needs a title and explicit offset-aware interval.")
        return self


class ReadQuery(Model):
    query: str = Field(default="", max_length=200)
    start: date | None = None
    end: date | None = None
    limit: int = Field(default=20, ge=1, le=40, strict=True)
    free_minutes: int | None = Field(
        default=None,
        ge=5,
        le=600,
        description="Calendar only: also return free slots of at least this many minutes "
        "between start and end (computed from events, task blocks and routines; 08:00-22:00).",
    )

    @model_validator(mode="after")
    def interval(self):
        if (self.start is None) != (self.end is None):
            raise ValueError("Supply both dates or neither.")
        if self.start and not 0 <= (self.end - self.start).days <= 62:
            raise ValueError("Read at most 63 days.")
        return self


TABLES = {
    "task": "tasks",
    "event": "calendar_events",
    "date_item": "calendar_date_items",
    "availability": "availability_windows",
    "block": "execution_blocks",
}


class ApplicationTools:
    def __init__(self, database):
        self.database = database

    def read(self, agent, values):
        body = ReadQuery.model_validate(values)
        result = {}
        kinds = ["task"] if agent == "tasks" else ["event", "date_item", "availability", "block"]
        with self.database.connect() as db:
            db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            for kind in kinds:
                if kind == "block":
                    result["block"] = self.blocks(db, body)
                    continue
                table = TABLES[kind]
                temporal = {
                    "task": "COALESCE(due_date,(deadline_at AT TIME ZONE timezone)::date)",
                    "event": "(starts_at AT TIME ZONE timezone)::date",
                    "date_item": "starts_on",
                    "availability": "(starts_at AT TIME ZONE timezone)::date",
                }[kind]
                if kind == "date_item":
                    interval = "starts_on<=%s::date AND ends_before>%s::date"
                    bounds = (body.end, body.start)
                elif kind in ("event", "availability"):
                    interval = "starts_at<((%s::date+1)::timestamp AT TIME ZONE timezone) AND ends_at>(%s::date::timestamp AT TIME ZONE timezone)"
                    bounds = (body.end, body.start)
                else:
                    interval = temporal + " BETWEEN %s::date AND %s::date"
                    bounds = (body.start, body.end)
                fields = "id,title,version," + (
                    "objective,description,area,due_date,deadline_at,timezone,priority,estimated_minutes,effort,tags,goal_id,project_id,parent_id,state,done"
                    if kind == "task"
                    else "description,starts_on,ends_before,kind,cancelled"
                    if kind == "date_item"
                    else "description,starts_at,ends_at,timezone,cancelled"
                )
                if kind == "task":
                    fields += ",ARRAY(SELECT depends_on FROM app.task_dependencies WHERE task_id=tasks.id ORDER BY depends_on) AS dependencies"
                rows = db.execute(
                    sql.SQL(
                        "SELECT "
                        + fields
                        + " FROM app.{} WHERE (%s='' OR title ILIKE %s ESCAPE '\\') "
                        "AND (%s::date IS NULL OR " + interval + ") ORDER BY id LIMIT %s"
                    ).format(sql.Identifier(table)),
                    (
                        body.query,
                        "%"
                        + body.query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                        + "%",
                        body.start,
                        *bounds,
                        body.limit + 1,
                    ),
                ).fetchall()
                result[kind] = {
                    "items": jsonable_encoder(rows[: body.limit]),
                    "truncated": len(rows) > body.limit,
                }
        if agent != "tasks" and body.free_minutes and body.start:
            from .free_slots import free_slots

            with self.database.connect() as db:
                result["free_slots"] = free_slots(
                    db, body.start, (body.end - body.start).days + 1, body.free_minutes
                )
        return result

    def blocks(self, db, body):
        """Task time blocks (when a task is scheduled), so they can be moved like events."""
        rows = db.execute(
            "SELECT b.id,b.version,b.task_id,t.title,t.priority,b.starts_at,b.ends_at,b.timezone,"
            "b.cancelled FROM app.execution_blocks b JOIN app.tasks t ON t.id=b.task_id "
            "WHERE NOT b.cancelled AND NOT t.done AND (%s='' OR t.title ILIKE %s ESCAPE '\\') "
            "AND (%s::date IS NULL OR (b.starts_at<((%s::date+1)::timestamp AT TIME ZONE b.timezone) "
            "AND b.ends_at>(%s::date::timestamp AT TIME ZONE b.timezone))) ORDER BY b.starts_at LIMIT %s",
            (
                body.query,
                "%"
                + body.query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                + "%",
                body.start,
                body.end,
                body.start,
                body.limit + 1,
            ),
        ).fetchall()
        return {"items": jsonable_encoder(rows[: body.limit]), "truncated": len(rows) > body.limit}

    def inspect(self, proposal, db=None):
        """Read current values; approvals never authorize an unknown target version."""
        if proposal.id is None:
            return None
        if db is None:
            with self.database.connect() as connection:
                return self.inspect(proposal, connection)
        table = TABLES[proposal.operation.partition(".")[0]]
        row = db.execute(
            sql.SQL("SELECT * FROM app.{} WHERE id=%s FOR UPDATE").format(sql.Identifier(table)),
            (proposal.id,),
        ).fetchone()
        if not row or row["version"] != proposal.version:
            raise HTTPException(
                409, "This item changed. Review a fresh proposal before applying it."
            )
        if proposal.operation.startswith("task."):
            row["dependencies"] = [
                item["depends_on"]
                for item in db.execute(
                    "SELECT depends_on FROM app.task_dependencies WHERE task_id=%s ORDER BY depends_on",
                    (proposal.id,),
                ).fetchall()
            ]
        if proposal.operation in ("task.update", "task.cancel") and (
            row["done"] or row["state"] in ("in_progress", "paused", "skipped")
        ):
            raise HTTPException(409, "Started or finished work is preserved. Use the task editor.")
        if proposal.operation == "task.update":
            body = TaskInput.model_validate(self.edit_values(db, proposal, row))
            if body.objective != row["objective"] or body.goal_id != row["goal_id"]:
                raise HTTPException(
                    409,
                    "The original goal must stay unchanged. Create separate work for a different goal.",
                )
        return jsonable_encoder(row)

    def edit_values(self, db, proposal, current):
        kind = proposal.operation.partition(".")[0]
        if kind == "task":
            baseline = {key: current[key] for key in TaskInput.model_fields if key in current}
            baseline["dependencies"] = [
                row["depends_on"]
                for row in db.execute(
                    "SELECT depends_on FROM app.task_dependencies WHERE task_id=%s ORDER BY depends_on",
                    (proposal.id,),
                ).fetchall()
            ]
        elif kind == "date_item":
            baseline = {key: current[key] for key in DateItemInput.model_fields if key in current}
        elif kind == "block":
            baseline = {
                "start": current["starts_at"],
                "end": current["ends_at"],
                "timezone": current["timezone"],
            }
        else:
            baseline = {
                "title": current["title"],
                "description": current["description"],
                "start": current["starts_at"],
                "end": current["ends_at"],
                "timezone": current["timezone"],
            }
        return {**baseline, **proposal.data}

    def execute(self, proposal, key, db):
        db.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK,))
        current = self.inspect(proposal, db)
        values = {"key": key, "id": proposal.id, "version": proposal.version, "data": proposal.data}
        if current and proposal.operation.endswith(".update"):
            values["data"] = self.edit_values(db, proposal, current)
        db.execute("SELECT set_config('yggdress.command_id',%s,true)", (str(key),))
        if proposal.operation == "task.cancel":
            changed = update(db, "tasks", proposal.id, {"state": "skipped"})
            db.execute(
                "UPDATE app.execution_blocks SET cancelled=true,version=version+1 WHERE task_id=%s AND NOT cancelled",
                (proposal.id,),
            )
            history(db, proposal.id, "agent.cancel", {"goal_preserved": True})
            refresh_reminders(db)
            return jsonable_encoder({"id": changed["id"], "version": changed["version"]})
        if proposal.operation.startswith(("date_item.", "availability.")):
            result = temporal_result(db, TimeCommand(operation=proposal.operation, **values))
        else:
            result = command_result(db, Command(op=proposal.operation, **values))
        refresh_reminders(db)
        return jsonable_encoder(result)


def allowed(agent, proposal):
    if (agent == "tasks") != proposal.operation.startswith("task."):
        raise ValueError("The proposed operation is outside this specialist's domain.")
    return proposal
