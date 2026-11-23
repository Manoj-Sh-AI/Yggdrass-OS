"""Authenticated application interfaces shared by all routine clients."""

from datetime import UTC, date, datetime, timedelta
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field

from . import daily_content as content
from .daily_routine_settings import RoutineSettings, Strict, save_settings, settings, timezone
from .routine_catalogue import LABELS, render
from .routine_delivery import queue_notice
from .routine_jobs import acknowledge, mark
from .routine_reflections import (
    PoolItem,
    Prediction,
    Resolution,
    add_prediction,
    calibration,
    resolve,
)


class Trigger(Strict):
    kind: str = Field(max_length=30)
    day: date | None = None
    dry_run: bool = True
    task_id: UUID | None = None
    starts_at: datetime | None = None


def run_anchor(database, lia, kind, day, zone, now):
    if kind == "filing":
        from .daily_filing import consolidate

        return consolidate(database, lia, day - timedelta(days=1))
    if kind == "morning":
        from .daily_inputs import refresh

        refresh(database, day, zone)
    with database.connect() as db:
        if kind in ("morning", "evening"):
            result = content.persist_brief(db, content.preview(db, kind, day, zone))
        else:
            result = render(db, kind, day, zone, issue=True)
        queue_notice(db, key=f"anchor:{kind}:{zone}:{day}", kind=kind)
        if kind == "weekly":
            for extra in ("scout", "outside", "wildcard"):
                render(db, extra, day, zone, issue=True)
        if kind == "morning":
            render(db, "radar", day, zone, issue=True)
            render(db, "intuition", day, zone, issue=True)
            render(db, "spark", day, zone, issue=True)
        return result


def sweep_blocks(database, now):
    from .call_service import quiet

    with database.connect() as db:
        zone = timezone(db)
        day = now.astimezone(ZoneInfo(zone)).date()
        pref = settings(db)
        calls_pref = db.execute("SELECT * FROM app.call_preferences").fetchone()
        if (
            not pref["enabled"]
            or day.weekday() == pref["rest_day"]
            or (calls_pref and quiet(now, calls_pref))
        ):
            return
        drift = db.execute(
            "SELECT b.id,b.task_id FROM app.execution_blocks b JOIN app.tasks t ON t.id=b.task_id "
            "WHERE NOT b.cancelled AND t.state='todo' AND NOT t.done "
            "AND b.ends_at BETWEEN %s AND %s ORDER BY b.ends_at,b.id",
            (now - timedelta(minutes=7), now - timedelta(minutes=5)),
        ).fetchall()
        db.execute("SELECT pg_advisory_xact_lock(719218432)")
        count = db.execute(
            "SELECT count(*) n FROM app.routine_editions WHERE kind='drift' AND for_date=%s", (day,)
        ).fetchone()["n"]
        for row in drift:
            if count >= 2:
                break
            period = str(day) + ":" + str(row["id"])
            if db.execute(
                "SELECT 1 FROM app.routine_editions WHERE kind='drift' AND period=%s", (period,)
            ).fetchone():
                continue
            item = render(
                db, "drift", day, zone, task_id=row["task_id"], subject=row["id"], issue=True
            )
            queue_notice(db, key="drift:" + str(row["id"]), kind=item["kind"])
            count += 1
        ended = db.execute(
            "SELECT b.id,b.task_id,t.done,t.state FROM app.execution_blocks b JOIN app.tasks t "
            "ON t.id=b.task_id WHERE NOT b.cancelled AND b.ends_at BETWEEN %s AND %s",
            (now - timedelta(minutes=2), now),
        ).fetchall()
        for row in ended:
            if row["done"] or row["state"] in ("in_progress", "paused"):
                item = render(
                    db, "shutdown", day, zone, task_id=row["task_id"], subject=row["id"], issue=True
                )
                queue_notice(db, key="shutdown:" + str(row["id"]), kind=item["kind"])


def routine_router(database, session, lia=None):
    router = APIRouter(prefix="/v1/application/daily-routines", dependencies=[Depends(session)])

    @router.get("")
    def overview(day: date | None = None):
        with database.connect() as db:
            zone = timezone(db)
            selected = day or datetime.now(UTC).astimezone(ZoneInfo(zone)).date()
            return {
                "settings": settings(db),
                "timezone": zone,
                "day": selected,
                "briefs": db.execute(
                    "SELECT * FROM app.daily_briefs WHERE for_date=%s", (selected,)
                ).fetchall(),
                "editions": db.execute(
                    "SELECT * FROM app.routine_editions WHERE for_date=%s", (selected,)
                ).fetchall(),
                "important": db.execute(
                    "SELECT block_id FROM app.routine_important_blocks"
                ).fetchall(),
                "jobs": db.execute(
                    "SELECT id,kind,run_at,status,attempts,outcome FROM app.scheduled_jobs "
                    "ORDER BY run_at DESC LIMIT 60"
                ).fetchall(),
                "lessons": content.list_lessons(db),
            }

    @router.put("/settings")
    def update(body: RoutineSettings):
        from .daily_inputs import SOURCES

        if set(body.approved_feeds) - set(SOURCES):
            raise HTTPException(422, "Choose a published news source.")
        with database.connect() as db:
            return save_settings(
                db, body, datetime.now(UTC).astimezone(ZoneInfo(timezone(db))).date()
            )

    @router.post("/trigger")
    def trigger(body: Trigger):
        with database.connect() as db:
            zone = timezone(db)
            day = body.day or datetime.now(UTC).astimezone(ZoneInfo(zone)).date()
            if body.kind in ("morning", "evening", "pre_task"):
                value = content.preview(db, body.kind, day, zone, body.task_id, body.starts_at)
                if not body.dry_run:
                    content.persist_brief(db, value)
                return value
            if body.kind == "filing":
                if body.dry_run:
                    return {
                        "kind": "filing",
                        "day": day,
                        "dry_run": True,
                        "approval_required": True,
                    }
            elif body.kind in LABELS:
                return render(
                    db, body.kind, day, zone, task_id=body.task_id, issue=not body.dry_run
                )
            else:
                raise HTTPException(422, "Unknown routine.")
        from .daily_filing import consolidate

        return consolidate(database, lia() if callable(lia) else lia, day)

    class Important(Strict):
        block_id: UUID
        enabled: bool

    @router.post("/important")
    def important(body: Important):
        with database.connect() as db:
            return mark(db, body.block_id, body.enabled)

    class Ack(Strict):
        escalation_id: UUID
        action: Literal["started", "not_yet"]

    @router.post("/ack")
    def ack(body: Ack):
        with database.connect() as db:
            return acknowledge(db, body.escalation_id, body.action)

    @router.post("/journal")
    def journal(body: content.JournalInput):
        with database.connect() as db:
            return content.append_journal(
                db, datetime.now(UTC).astimezone(ZoneInfo(timezone(db))).date(), body
            )

    @router.post("/review")
    def review(body: content.ReviewInput):
        with database.connect() as db:
            zone = timezone(db)
            return content.submit_review(
                db, datetime.now(UTC).astimezone(ZoneInfo(zone)).date(), zone, body
            )

    class Lesson(Strict):
        id: UUID
        decision: Literal["confirm", "retire", "edit"]
        text: str | None = Field(default=None, max_length=400)

    @router.post("/lessons")
    def lesson(body: Lesson):
        with database.connect() as db:
            return content.decide_lesson(db, body.id, body.decision, body.text)

    class Energy(Strict):
        anchor: Literal["morning", "midday", "evening"]
        value: int = Field(ge=1, le=5, strict=True)

    @router.post("/energy")
    def energy(body: Energy):
        with database.connect() as db:
            day = datetime.now(UTC).astimezone(ZoneInfo(timezone(db))).date()
            db.execute(
                "INSERT INTO app.routine_checkins(day,anchor,energy) VALUES(%s,%s,%s) "
                "ON CONFLICT(day,anchor) DO UPDATE SET energy=excluded.energy",
                (day, body.anchor, body.value),
            )
        return {"saved": True}

    @router.post("/predictions")
    def prediction(body: Prediction):
        with database.connect() as db:
            return add_prediction(db, body)

    @router.get("/predictions")
    def predictions():
        with database.connect() as db:
            return {
                "predictions": db.execute(
                    "SELECT * FROM app.routine_predictions ORDER BY created_at DESC LIMIT 100"
                ).fetchall(),
                "calibration": calibration(db),
            }

    @router.post("/predictions/{identifier}")
    def outcome(identifier: UUID, body: Resolution):
        with database.connect() as db:
            return resolve(db, identifier, body)

    @router.post("/pool")
    def pool(body: PoolItem):
        with database.connect() as db:
            return db.execute(
                "INSERT INTO app.routine_pool(kind,title,source_url,relevance) VALUES(%s,%s,%s,%s) RETURNING id",
                (
                    body.kind,
                    body.title,
                    str(body.source_url) if body.source_url else "",
                    body.relevance,
                ),
            ).fetchone()

    class Feedback(Strict):
        id: UUID
        kept: bool
        note: str = Field(default="", max_length=500)

    @router.post("/feedback")
    def feedback(body: Feedback):
        with database.connect() as db:
            row = db.execute(
                "UPDATE app.routine_editions SET feedback=%s,feedback_note=%s WHERE id=%s RETURNING id",
                ("kept" if body.kept else "dropped", body.note, body.id),
            ).fetchone()
            if not row:
                raise HTTPException(404, "Routine item not found.")
            return row

    class HypothesisDecision(Strict):
        id: UUID
        decision: Literal["confirmed", "rejected", "unsure"]

    @router.post("/hypotheses")
    def hypothesis(body: HypothesisDecision):
        with database.connect() as db:
            row = db.execute(
                "UPDATE app.routine_hypotheses SET state=%s WHERE id=%s RETURNING *",
                (body.decision, body.id),
            ).fetchone()
            if not row:
                raise HTTPException(404, "Pattern proposal not found.")
            return row

    @router.get("/hypotheses")
    def hypotheses():
        with database.connect() as db:
            return db.execute(
                "SELECT * FROM app.routine_hypotheses ORDER BY week DESC LIMIT 30"
            ).fetchall()

    @router.get("/filing")
    def filing(day: date | None = None):
        from .daily_filing import list_actions

        with database.connect() as db:
            return list_actions(db, day)

    class FilingDecision(Strict):
        decision: Literal["accept", "reject", "move", "undo"]
        target: str | None = Field(default=None, max_length=200)

    @router.post("/filing/{identifier}")
    def filing_decision(identifier: UUID, body: FilingDecision):
        from .daily_filing import decide

        return decide(
            database, lia() if callable(lia) else lia, identifier, body.decision, body.target
        )

    return router
