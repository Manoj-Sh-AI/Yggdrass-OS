"""Explicit date ranges and availability, separate from timed appointments and work."""

import hashlib
import re
from datetime import date
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from psycopg.types.json import Jsonb
from pydantic import Field, ValidationError, field_validator, model_validator

from .planning import LOCK, insert, time_values, update
from .planning_models import Model, TimeInput


class DateItemInput(Model):
    title: str = Field(min_length=1, max_length=180)
    description: str = Field(default="", max_length=2000)
    kind: Literal["event", "availability", "review"] = "event"
    starts_on: date
    ends_before: date

    @field_validator("starts_on", "ends_before", mode="before")
    @classmethod
    def date_precision(cls, value):
        if (
            type(value) is date
            or isinstance(value, str)
            and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value)
        ):
            return value
        raise ValueError("Use a calendar date, without an invented time or offset.")

    @model_validator(mode="after")
    def interval(self):
        if self.ends_before <= self.starts_on:
            raise ValueError("The exclusive end date must follow the start date.")
        return self


class TimeCommand(Model):
    key: UUID
    operation: Literal[
        "date_item.create",
        "date_item.update",
        "date_item.remove",
        "availability.create",
        "availability.update",
        "availability.remove",
    ]
    id: UUID | None = None
    version: int | None = Field(default=None, ge=1, strict=True)
    data: dict = Field(default_factory=dict)


def temporal_result(db, command: TimeCommand):
    date_item = command.operation.startswith("date_item.")
    table = "calendar_date_items" if date_item else "availability_windows"
    existing = None
    if not command.operation.endswith("create"):
        existing = db.execute(
            f"SELECT * FROM app.{table} WHERE id=%s FOR UPDATE", (command.id,)
        ).fetchone()
        if not existing:
            raise HTTPException(404, "Calendar item not found.")
        if command.version != existing["version"] or existing["cancelled"]:
            raise HTTPException(
                409, "This calendar item changed. Refresh before applying your edit."
            )
    if command.operation.endswith("remove"):
        if command.data:
            raise HTTPException(422, "Unexpected removal fields.")
        result = update(db, table, existing["id"], {"cancelled": True})
    else:
        if date_item:
            values = DateItemInput.model_validate(command.data).model_dump()
        else:
            body = TimeInput.model_validate(command.data)
            if not body.title or body.task_id:
                raise HTTPException(
                    422, "Availability needs its own title and cannot be a task block."
                )
            values = {**time_values(body), "title": body.title, "description": body.description}
        result = (
            update(db, table, existing["id"], values)
            if existing
            else insert(db, table, {"id": uuid4(), **values})
        )
    return {"id": result["id"], "version": result["version"]}


def temporal_router(database, session):
    router = APIRouter(prefix="/v1/application/time", dependencies=[Depends(session)])

    @router.post("/commands")
    def mutate(command: TimeCommand):
        fingerprint = hashlib.sha256(
            ("time:" + command.model_dump_json(exclude={"key"})).encode()
        ).hexdigest()
        with database.connect() as db:
            db.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK,))
            receipt = db.execute(
                "SELECT * FROM app.planning_commands WHERE id=%s", (command.key,)
            ).fetchone()
            if receipt:
                if receipt["fingerprint"] != fingerprint:
                    raise HTTPException(409, "This retry key belongs to a different change.")
                return receipt["result"]
            db.execute("SELECT set_config('yggdress.command_id',%s,true)", (str(command.key),))
            try:
                result = jsonable_encoder(temporal_result(db, command))
            except ValidationError as error:
                raise HTTPException(
                    422, "; ".join(item["msg"] for item in error.errors())
                ) from None
            db.execute(
                "INSERT INTO app.planning_commands(id,fingerprint,result) VALUES (%s,%s,%s)",
                (command.key, fingerprint, Jsonb(result)),
            )
            return result

    return router
