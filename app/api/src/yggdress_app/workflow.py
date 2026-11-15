"""Structured producer intake, not semantic interpretation or a Brain writer."""

import hashlib
import re
from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from psycopg import sql
from psycopg.types.json import Jsonb
from pydantic import Field, ValidationError, model_validator

from .connections import ENTITIES, observe_note, verified_note
from .planning import LOCK, command_result, history, refresh_reminders, update
from .planning_models import Command, Model, TaskInput
from .receivers import payload_fingerprint, receiver_access
from .temporal import TimeCommand, temporal_result


class Interpretation(Model):
    commitment_identity: str = Field(min_length=1, max_length=200)
    meaning: Literal[
        "deadline",
        "appointment",
        "availability",
        "review",
        "preference",
        "recurrence",
        "historical",
        "cancellation",
    ]
    precision: Literal["date", "datetime", "interval", "month", "year", "relative", "unspecified"]
    disposition: Literal["clear", "uncertain"]
    action: Literal["upsert", "retract", "context"] = "upsert"
    entity_type: Literal["task", "event", "date_item", "availability"] | None = None
    data: dict = Field(default_factory=dict)
    anchor: str = Field(default="", max_length=1000)
    original_phrase: str = Field(default="", max_length=2000)
    explanation: str = Field(default="", max_length=2000)
    target_id: UUID | None = None
    target_version: int | None = Field(default=None, ge=1, strict=True)

    @model_validator(mode="after")
    def explicit_target(self):
        if (self.target_id is None) != (self.target_version is None):
            raise ValueError("An existing target requires both its identity and current version.")
        return self


class SourceChange(Model):
    handoff_id: UUID
    change_id: UUID
    producer: str = Field(min_length=1, max_length=100)
    namespace: str = Field(min_length=1, max_length=100)
    external_identity: str = Field(min_length=1, max_length=200)
    sequence: int = Field(ge=0, strict=True)
    previous_revision: str | None = Field(default=None, max_length=200)
    revision: str = Field(min_length=1, max_length=200)
    slug: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,200}$")
    lifecycle: Literal["active", "archived", "missing"] = "active"
    producer_version: str = Field(min_length=1, max_length=100)
    causation_id: UUID | None = None
    interpretations: list[Interpretation] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def identities(self):
        values = [item.commitment_identity for item in self.interpretations]
        if len(values) != len(set(values)):
            raise ValueError("A commitment can occur only once in a source change.")
        if self.lifecycle != "active" and self.interpretations:
            raise ValueError("Lifecycle observations cannot also propose work mutations.")
        return self


class ResolveReview(Model):
    key: UUID
    id: UUID
    version: int = Field(ge=1, strict=True)
    decision: Literal["accept", "dismiss"]
    target_version: int | None = Field(default=None, ge=1, strict=True)


def binding(db, source_id, identity):
    return db.execute(
        "SELECT * FROM app.workflow_bindings WHERE source_id=%s AND commitment_identity=%s FOR UPDATE",
        (source_id, identity),
    ).fetchone()


def target(db, kind, identifier, lock=True):
    return db.execute(
        sql.SQL("SELECT * FROM app.{} WHERE id=%s" + (" FOR UPDATE" if lock else "")).format(
            sql.Identifier(ENTITIES[kind][0])
        ),
        (identifier,),
    ).fetchone()


def remember_result(db, source, item, kind, result):
    _, links, column = ENTITIES[kind]
    db.execute(
        sql.SQL(
            "INSERT INTO app.{} ({},note_ref_id,kind,source_revision) VALUES (%s,%s,'source',%s) ON CONFLICT ({},note_ref_id,kind) DO UPDATE SET source_revision=EXCLUDED.source_revision"
        ).format(sql.Identifier(links), sql.Identifier(column), sql.Identifier(column)),
        (result["id"], source["note_ref_id"], source["revision"]),
    )
    db.execute(
        "INSERT INTO app.workflow_bindings(source_id,commitment_identity,entity_type,entity_id,applied_version,source_revision,last_payload) VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(source_id,commitment_identity) DO UPDATE SET applied_version=EXCLUDED.applied_version,source_revision=EXCLUDED.source_revision,last_payload=EXCLUDED.last_payload",
        (
            source["id"],
            item.commitment_identity,
            kind,
            result["id"],
            result["version"],
            source["revision"],
            Jsonb(item.model_dump(mode="json")),
        ),
    )
    refresh_reminders(db)
    return {"state": "applied", "entity_type": kind, **jsonable_encoder(result)}


def apply_interpretation(db, source, item, key, *, confirmed=False, target_version=None):
    existing = binding(db, source["id"], item.commitment_identity)
    if item.disposition != "clear":
        raise HTTPException(
            409, "The date or context is uncertain. Clarify it before changing application work."
        )
    if item.action == "context" or item.meaning == "historical":
        if existing:
            raise HTTPException(
                409,
                "Existing work needs an explicit decision; a historical mention does not cancel it.",
            )
        return {"state": "context", "meaning": item.meaning, "precision": item.precision}
    if (
        item.disposition != "clear"
        or item.precision in ("month", "year", "relative", "unspecified")
        or item.meaning in ("preference", "recurrence")
    ):
        raise HTTPException(
            409, "This meaning needs clarification; no exact time or task was invented."
        )
    kind = item.entity_type
    if not kind or existing and existing["entity_type"] != kind:
        raise HTTPException(
            409, "A change of work type needs a separate commitment or manual reconciliation."
        )
    if existing and item.target_id and item.target_id != existing["entity_id"]:
        raise HTTPException(409, "A commitment cannot silently switch to another application item.")
    current = (
        target(db, kind, existing["entity_id"])
        if existing
        else target(db, kind, item.target_id)
        if item.target_id
        else None
    )
    if item.target_id and not current:
        raise HTTPException(409, "The explicit target no longer exists.")
    if not existing and item.target_id and not confirmed:
        raise HTTPException(
            409,
            "Confirm binding this existing work; it will not be duplicated or silently overwritten.",
        )
    if existing and not current:
        raise HTTPException(
            409, "The original application item is missing; no replacement was silently created."
        )
    if current:
        if current["version"] != (target_version if confirmed else existing["applied_version"]):
            raise HTTPException(
                409, "This work was edited independently. Review its current version first."
            )
        if kind == "task" and (
            current["done"] or current["state"] in ("in_progress", "paused", "skipped")
        ):
            raise HTTPException(
                409, "Started or finished work is preserved. Reconcile it in the task editor."
            )
        if kind != "task" and current["cancelled"]:
            raise HTTPException(
                409, "This calendar item was removed. It will not be silently restored."
            )
    if item.action == "retract" or item.meaning == "cancellation":
        if not confirmed:
            raise HTTPException(
                409, "Confirm cancellation; removing a phrase alone never deletes work."
            )
        if not current:
            return {"state": "no_binding"}
        if kind == "task":
            changed = update(db, "tasks", current["id"], {"state": "skipped"})
            db.execute(
                "UPDATE app.execution_blocks SET cancelled=true,version=version+1 WHERE task_id=%s AND NOT cancelled",
                (current["id"],),
            )
            history(
                db,
                current["id"],
                "source.cancel",
                {"source_id": str(source["id"]), "goal_preserved": True},
            )
            return remember_result(
                db, source, item, "task", {"id": changed["id"], "version": changed["version"]}
            )
        operation, data = kind + ".remove", {}
    else:
        supported = {
            "task": ("deadline", ("date", "datetime")),
            "event": ("appointment", ("datetime", "interval")),
            "date_item": (("appointment", "availability", "review"), ("date",)),
            "availability": ("availability", ("datetime", "interval")),
        }
        meanings, precisions = supported[kind]
        if (
            item.meaning not in (meanings if isinstance(meanings, tuple) else (meanings,))
            or item.precision not in precisions
        ):
            raise HTTPException(
                409, "The proposed type does not match the stated time meaning and precision."
            )
        data = item.data.copy()
        if item.precision in ("datetime", "interval"):
            if not data.get("timezone"):
                raise HTTPException(409, "Exact times require an explicit named timezone.")
            for field in ("deadline_at",) if kind == "task" else ("start", "end"):
                if field == "end" and not data.get(field):
                    continue
                try:
                    value = datetime.fromisoformat(str(data.get(field, "")))
                except ValueError:
                    raise HTTPException(
                        409, "The time needs a complete offset-aware timestamp."
                    ) from None
                if value.tzinfo is None:
                    raise HTTPException(
                        409,
                        "The timestamp needs an explicit UTC offset; no daylight-saving choice was guessed.",
                    )
        if kind == "task":
            if item.precision == "date" and not re.fullmatch(
                r"\d{4}-\d{2}-\d{2}", str(data.get("due_date", ""))
            ):
                raise HTTPException(409, "Keep a date-only deadline as a calendar date.")
            if item.precision == "date" and (not data.get("due_date") or data.get("deadline_at")):
                raise HTTPException(
                    409, "A date deadline needs a date without an invented exact hour."
                )
            if item.precision == "datetime" and not data.get("deadline_at"):
                raise HTTPException(409, "An exact deadline needs an offset-aware timestamp.")
            if current:
                if data.get("objective", current["objective"]) != current["objective"] or (
                    "goal_id" in data and str(data["goal_id"]) != str(current["goal_id"])
                ):
                    raise HTTPException(
                        409,
                        "The original goal is fixed. Create a separate commitment for a different goal.",
                    )
                merged = {name: current[name] for name in TaskInput.model_fields if name in current}
                merged["dependencies"] = [
                    r["depends_on"]
                    for r in db.execute(
                        "SELECT depends_on FROM app.task_dependencies WHERE task_id=%s",
                        (current["id"],),
                    )
                ]
                data = {**jsonable_encoder(merged), **data}
        operation = kind + (".update" if current else ".create")
    if kind in ("task", "event"):
        result = command_result(
            db,
            Command(
                key=key,
                op=operation,
                id=current["id"] if current else None,
                version=current["version"] if current else None,
                data=data,
            ),
        )
    else:
        result = temporal_result(
            db,
            TimeCommand(
                key=key,
                operation=operation,
                id=current["id"] if current else None,
                version=current["version"] if current else None,
                data=data,
            ),
        )
    return remember_result(db, source, item, kind, result)


def workflow_routers(database, notes, session, tokens=None):
    authenticate, configured = receiver_access("workflow", tokens)
    receiver = APIRouter(prefix="/v1/receivers/workflow", dependencies=[Depends(authenticate)])
    owner = APIRouter(prefix="/v1/application/workflow", dependencies=[Depends(session)])

    @owner.get("/capabilities")
    def capabilities():
        return {
            "structured_intake": True,
            "producer_connected": configured,
            "semantic_extractor": False,
            "brain_archive_write": False,
            "source_identity_verification": "producer_assertion_with_http_revision_check",
        }

    @receiver.post("/changes")
    def receive(event: SourceChange):
        fingerprint = payload_fingerprint(event)
        with database.connect() as db:
            replay = db.execute(
                "SELECT fingerprint,result FROM app.workflow_changes WHERE id=%s",
                (event.change_id,),
            ).fetchone()
            if replay:
                if replay["fingerprint"] != fingerprint:
                    raise HTTPException(
                        409, "This source change identity already belongs to another payload."
                    )
                return replay["result"]
        verified = verified_note(notes, event.slug) if event.lifecycle == "active" else None
        if verified and verified["version"] != event.revision:
            raise HTTPException(
                409,
                "The source revision is no longer current. Redeliver its current committed change.",
            )
        with database.connect() as db:
            db.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK,))
            handoff = db.execute(
                "SELECT * FROM app.note_handoffs WHERE id=%s", (event.handoff_id,)
            ).fetchone()
            if not handoff or any(
                handoff[field] != getattr(event, field)
                for field in ("namespace", "external_identity", "slug", "revision", "lifecycle")
            ):
                raise HTTPException(
                    409, "An agent update must refer to the matching stored Lia handoff."
                )
            newest = db.execute(
                "SELECT revision FROM app.note_handoffs WHERE namespace=%s AND external_identity=%s ORDER BY sequence DESC LIMIT 1",
                (event.namespace, event.external_identity),
            ).fetchone()
            if newest["revision"] != event.revision:
                raise HTTPException(409, "A newer Lia handoff superseded this update.")
            replay = db.execute(
                "SELECT fingerprint,result FROM app.workflow_changes WHERE id=%s",
                (event.change_id,),
            ).fetchone()
            if replay:
                if replay["fingerprint"] != fingerprint:
                    raise HTTPException(409, "The source event was reused.")
                return replay["result"]
            source = db.execute(
                "SELECT * FROM app.workflow_sources WHERE producer=%s AND namespace=%s AND external_identity=%s FOR UPDATE",
                (handoff["producer"], event.namespace, event.external_identity),
            ).fetchone()
            if source and (
                event.sequence != source["sequence"] + 1
                or event.previous_revision != source["revision"]
            ):
                raise HTTPException(
                    409,
                    "Source changes must be delivered in sequence against the previous revision.",
                )
            if not source and (
                event.sequence != 0
                or event.previous_revision is not None
                or event.lifecycle != "active"
            ):
                raise HTTPException(
                    409, "Register an active verified source at sequence zero first."
                )
            if source and source["slug"] != event.slug:
                alias = db.execute(
                    "SELECT * FROM app.note_refs WHERE source='brain' AND external_id=%s",
                    (event.slug,),
                ).fetchone()
                if alias and alias["id"] != source["note_ref_id"]:
                    raise HTTPException(
                        409, "This slug belongs to another source. An identity merge needs review."
                    )
                if event.lifecycle != "active":
                    raise HTTPException(409, "A rename requires a current readable note revision.")
                db.execute(
                    "UPDATE app.note_refs SET external_id=%s WHERE id=%s",
                    (event.slug, source["note_ref_id"]),
                )
            reference = observe_note(db, event.slug, verified) if verified else None
            if reference:
                collision = db.execute(
                    "SELECT id FROM app.workflow_sources WHERE note_ref_id=%s AND (producer,namespace,external_identity)<>(%s,%s,%s)",
                    (
                        reference["id"],
                        handoff["producer"],
                        event.namespace,
                        event.external_identity,
                    ),
                ).fetchone()
                if collision:
                    raise HTTPException(
                        409,
                        "This note identity is already bound. Slug reuse will not merge unrelated work.",
                    )
            source = db.execute(
                "INSERT INTO app.workflow_sources(producer,namespace,external_identity,note_ref_id,slug,revision,sequence,lifecycle) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(producer,namespace,external_identity) DO UPDATE SET slug=EXCLUDED.slug,revision=EXCLUDED.revision,sequence=EXCLUDED.sequence,lifecycle=EXCLUDED.lifecycle,observed_at=now() RETURNING *",
                (
                    handoff["producer"],
                    event.namespace,
                    event.external_identity,
                    reference["id"] if reference else source["note_ref_id"],
                    event.slug,
                    event.revision,
                    event.sequence,
                    event.lifecycle,
                ),
            ).fetchone()
            # Supersede the same proposal or an old source revision, never an
            # unrelated agent's unresolved decision for the same source version.
            db.execute(
                "UPDATE app.workflow_reviews SET state='superseded',version=version+1,resolved_at=now() WHERE source_id=%s AND state='pending' AND (%s OR commitment_identity=ANY(%s) OR change_id IN (SELECT id FROM app.workflow_changes WHERE source_revision<>%s))",
                (
                    source["id"],
                    event.lifecycle != "active",
                    [item.commitment_identity for item in event.interpretations],
                    event.revision,
                ),
            )
            db.execute("SELECT set_config('yggdress.command_id',%s,true)", (str(event.change_id),))
            results = []
            if event.lifecycle != "active":
                pending = db.execute(
                    "SELECT commitment_identity FROM app.workflow_bindings WHERE source_id=%s",
                    (source["id"],),
                ).fetchall()
                for row in pending:
                    db.execute(
                        "INSERT INTO app.workflow_reviews(change_id,source_id,source_sequence,commitment_identity,reason,proposal) VALUES (%s,%s,%s,%s,%s,%s)",
                        (
                            event.change_id,
                            source["id"],
                            event.sequence,
                            row["commitment_identity"],
                            "Source "
                            + event.lifecycle
                            + ". Linked work and history remain intact.",
                            Jsonb({"lifecycle": event.lifecycle}),
                        ),
                    )
                results.append(
                    {"state": "observed", "lifecycle": event.lifecycle, "work_preserved": True}
                )
            for item in event.interpretations:
                try:
                    with db.transaction():
                        result = apply_interpretation(db, source, item, event.change_id)
                except (HTTPException, ValidationError) as error:
                    reason = (
                        error.detail
                        if isinstance(error, HTTPException)
                        else "; ".join(row["msg"] for row in error.errors())
                    )
                    review = db.execute(
                        "INSERT INTO app.workflow_reviews(change_id,source_id,source_sequence,commitment_identity,reason,proposal) VALUES (%s,%s,%s,%s,%s,%s) RETURNING id",
                        (
                            event.change_id,
                            source["id"],
                            event.sequence,
                            item.commitment_identity,
                            str(reason),
                            Jsonb(item.model_dump(mode="json")),
                        ),
                    ).fetchone()
                    result = {
                        "state": "review",
                        "review_id": str(review["id"]),
                        "reason": str(reason),
                    }
                results.append({"commitment_identity": item.commitment_identity, **result})
            result = jsonable_encoder(
                {"change_id": event.change_id, "source_id": source["id"], "results": results}
            )
            db.execute(
                "INSERT INTO app.workflow_changes(id,source_id,handoff_id,source_sequence,source_revision,fingerprint,payload,result) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    event.change_id,
                    source["id"],
                    event.handoff_id,
                    event.sequence,
                    event.revision,
                    fingerprint,
                    Jsonb(event.model_dump(mode="json")),
                    Jsonb(result),
                ),
            )
            return result

    @receiver.get("/source")
    def source_cursor(handoff_id: UUID):
        with database.connect() as db:
            handoff = db.execute(
                "SELECT * FROM app.note_handoffs WHERE id=%s", (handoff_id,)
            ).fetchone()
            if not handoff:
                raise HTTPException(404, "Handoff not found.")
            source = db.execute(
                "SELECT * FROM app.workflow_sources WHERE producer=%s AND namespace=%s AND external_identity=%s",
                (handoff["producer"], handoff["namespace"], handoff["external_identity"]),
            ).fetchone()
            bindings = (
                db.execute(
                    "SELECT commitment_identity,entity_type,entity_id,applied_version,source_revision,last_payload FROM app.workflow_bindings WHERE source_id=%s ORDER BY commitment_identity LIMIT 101",
                    (source["id"],),
                ).fetchall()
                if source
                else []
            )
            reference = source["note_ref_id"] if source else None
            if reference is None:
                note = db.execute(
                    "SELECT id FROM app.note_refs WHERE source='brain' AND external_id=%s",
                    (handoff["slug"],),
                ).fetchone()
                reference = note["id"] if note else None
            known_targets = []
            more_targets = False
            if reference:
                for kind, (table, links, column) in ENTITIES.items():
                    fields = "t.id,t.title,t.version" + (
                        ",t.objective,t.state,t.due_date,t.deadline_at,t.timezone,t.estimated_minutes,t.goal_id,t.project_id,t.description"
                        if kind == "task"
                        else ",t.cancelled,t.starts_on,t.ends_before,t.kind,t.description"
                        if kind == "date_item"
                        else ",t.cancelled,t.starts_at,t.ends_at,t.timezone,t.description"
                    )
                    found = db.execute(
                        sql.SQL(
                            "SELECT "
                            + fields
                            + " FROM app.{} t WHERE EXISTS(SELECT 1 FROM app.{} l WHERE l.{}=t.id AND l.note_ref_id=%s) ORDER BY t.id LIMIT 21"
                        ).format(
                            sql.Identifier(table), sql.Identifier(links), sql.Identifier(column)
                        ),
                        (reference,),
                    ).fetchall()
                    more_targets = more_targets or len(found) > 20
                    known_targets.extend({"entity_type": kind, **row} for row in found[:20])
            return {
                "next_sequence": source["sequence"] + 1 if source else 0,
                "previous_revision": source["revision"] if source else None,
                "bindings": bindings[:100],
                "truncated": len(bindings) > 100,
                "linked_targets": known_targets,
                "linked_targets_truncated": more_targets,
            }

    @owner.get("/reviews")
    def reviews(limit: int = Query(default=30, ge=1, le=100)):
        with database.connect() as db:
            db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            rows = db.execute(
                "SELECT r.*,s.slug,s.lifecycle,b.entity_type,b.entity_id FROM app.workflow_reviews r JOIN app.workflow_sources s ON s.id=r.source_id LEFT JOIN app.workflow_bindings b ON b.source_id=r.source_id AND b.commitment_identity=r.commitment_identity WHERE r.state='pending' ORDER BY r.created_at,r.id LIMIT %s",
                (limit + 1,),
            ).fetchall()
            for row in rows[:limit]:
                if (
                    not row["entity_type"]
                    and row["proposal"].get("target_id")
                    and row["proposal"].get("entity_type") in ENTITIES
                ):
                    row["entity_type"] = row["proposal"]["entity_type"]
                    row["entity_id"] = UUID(row["proposal"]["target_id"])
                current = (
                    target(db, row["entity_type"], row["entity_id"], lock=False)
                    if row["entity_type"]
                    else None
                )
                row["current"] = (
                    {
                        key: current[key]
                        for key in (
                            "id",
                            "version",
                            "title",
                            "objective",
                            "due_date",
                            "deadline_at",
                            "state",
                            "starts_at",
                            "ends_at",
                            "starts_on",
                            "ends_before",
                            "cancelled",
                        )
                        if current and key in current
                    }
                    if current
                    else None
                )
            return {"reviews": rows[:limit], "truncated": len(rows) > limit}

    @owner.post("/reviews/resolve")
    def resolve(command: ResolveReview):
        fingerprint = hashlib.sha256(
            ("workflow-review:" + command.model_dump_json(exclude={"key"})).encode()
        ).hexdigest()
        with database.connect() as db:
            previous = db.execute(
                "SELECT fingerprint,result FROM app.planning_commands WHERE id=%s", (command.key,)
            ).fetchone()
            if previous:
                if previous["fingerprint"] != fingerprint:
                    raise HTTPException(409, "Retry identity belongs to another decision.")
                return previous["result"]
        if command.decision == "accept":
            with database.connect() as db:
                candidate = db.execute(
                    "SELECT s.slug,s.revision,s.lifecycle FROM app.workflow_reviews r JOIN app.workflow_sources s ON s.id=r.source_id WHERE r.id=%s",
                    (command.id,),
                ).fetchone()
            if candidate and candidate["lifecycle"] == "active":
                current_note = verified_note(notes, candidate["slug"])
                if current_note["version"] != candidate["revision"]:
                    raise HTTPException(
                        409,
                        "The source note changed again. Wait for its current handoff before applying this proposal.",
                    )
        fingerprint = hashlib.sha256(
            ("workflow-review:" + command.model_dump_json(exclude={"key"})).encode()
        ).hexdigest()
        with database.connect() as db:
            db.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK,))
            replay = db.execute(
                "SELECT fingerprint,result FROM app.planning_commands WHERE id=%s", (command.key,)
            ).fetchone()
            if replay:
                if replay["fingerprint"] != fingerprint:
                    raise HTTPException(409, "Retry identity belongs to another decision.")
                return replay["result"]
            row = db.execute(
                "SELECT * FROM app.workflow_reviews WHERE id=%s FOR UPDATE", (command.id,)
            ).fetchone()
            if not row:
                raise HTTPException(404, "Review not found.")
            if row["version"] != command.version or row["state"] != "pending":
                raise HTTPException(409, "This decision changed. Refresh before responding.")
            source = db.execute(
                "SELECT * FROM app.workflow_sources WHERE id=%s FOR UPDATE", (row["source_id"],)
            ).fetchone()
            original = db.execute(
                "SELECT source_revision FROM app.workflow_changes WHERE id=%s", (row["change_id"],)
            ).fetchone()
            if command.decision == "accept" and original["source_revision"] != source["revision"]:
                raise HTTPException(409, "The source changed again. Review the latest version.")
            result = {"state": "dismissed"}
            if command.decision == "accept":
                if source["lifecycle"] != "active" or "lifecycle" in row["proposal"]:
                    raise HTTPException(
                        409,
                        "Lifecycle observations preserve work. Manage the task or calendar item explicitly.",
                    )
                try:
                    result = apply_interpretation(
                        db,
                        source,
                        Interpretation.model_validate(row["proposal"]),
                        command.key,
                        confirmed=True,
                        target_version=command.target_version,
                    )
                except ValidationError as error:
                    raise HTTPException(
                        422, "; ".join(item["msg"] for item in error.errors())
                    ) from None
            db.execute(
                "UPDATE app.workflow_reviews SET state=%s,version=version+1,resolved_at=now() WHERE id=%s",
                ("accepted" if command.decision == "accept" else "dismissed", row["id"]),
            )
            db.execute(
                "INSERT INTO app.planning_commands(id,fingerprint,result) VALUES (%s,%s,%s)",
                (command.key, fingerprint, Jsonb(result)),
            )
            return result

    return owner, receiver
