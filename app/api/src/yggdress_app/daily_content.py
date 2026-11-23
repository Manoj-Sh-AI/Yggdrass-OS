"""Application-owned daily briefs. Preview uses the same inputs as delivery, without writes."""

import hashlib
import json
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from psycopg.types.json import Jsonb
from pydantic import Field

from .planning import day_bounds
from .planning_models import Model

ShortText = Annotated[str, Field(min_length=1, max_length=400)]


class JournalInput(Model):
    key: UUID
    text: str = Field(min_length=1, max_length=2000)
    source: Literal["text", "voice"] = "text"
    supersedes_id: UUID | None = None


class NextStep(Model):
    task_id: UUID
    step: ShortText
    slot: ShortText  # The user's plan or "not this week"; a review never moves the calendar.


class ReviewInput(Model):
    key: UUID
    outcome: Literal["yes", "partial", "no", "skip"]
    worked: str = Field(default="", max_length=500)
    friction: str = Field(default="", max_length=500)
    lessons: list[ShortText] = Field(default_factory=list, max_length=2)
    next_steps: list[NextStep] = Field(default_factory=list, max_length=40)
    tomorrow: str = Field(default="", max_length=400)
    energy: int | None = Field(default=None, ge=1, le=5, strict=True)


def digest(value):
    return hashlib.sha256(json.dumps(jsonable_encoder(value), sort_keys=True).encode()).hexdigest()


def _entry(db, key, day, source, kind, text, meta, supersedes=None):
    existing = db.execute("SELECT * FROM app.journal_entries WHERE id=%s", (key,)).fetchone()
    if existing:
        if (
            existing["local_date"],
            existing["source"],
            existing["kind"],
            existing["text"],
            existing["meta"],
            existing["supersedes_id"],
        ) != (day, source, kind, text, meta, supersedes):
            raise HTTPException(
                409, "This journal request has already been used for different input."
            )
        return existing
    if supersedes:
        original = db.execute(
            "SELECT id FROM app.journal_entries WHERE id=%s AND local_date=%s AND kind=%s",
            (supersedes, day, kind),
        ).fetchone()
        if (
            not original
            or db.execute(
                "SELECT 1 FROM app.journal_entries WHERE supersedes_id=%s", (supersedes,)
            ).fetchone()
        ):
            raise HTTPException(409, "Refresh the journal before correcting this entry.")
    return db.execute(
        "INSERT INTO app.journal_entries(id,local_date,source,kind,text,meta,supersedes_id) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING *",
        (key, day, source, kind, text, Jsonb(meta), supersedes),
    ).fetchone()


def _day_lock(db, day):
    db.execute("SELECT pg_advisory_xact_lock(%s,%s)", (703101, day.toordinal()))


def append_journal(db, day: date, body: JournalInput):
    if body.supersedes_id:
        old = db.execute(
            "SELECT local_date FROM app.journal_entries WHERE id=%s AND kind='journal'",
            (body.supersedes_id,),
        ).fetchone()
        if not old:
            raise HTTPException(404, "Journal entry not found.")
        day = old["local_date"]
    _day_lock(db, day)
    return _entry(db, body.key, day, body.source, "journal", body.text, {}, body.supersedes_id)


def list_lessons(db):
    rows = db.execute("SELECT * FROM app.daily_lessons ORDER BY local_date DESC,slot").fetchall()
    for row in rows:
        if row["status"] == "active" and row["review_due"] < datetime.now(UTC).date():
            row["status"] = "stale"
    return rows


def decide_lesson(db, identifier, decision, text=None):
    row = db.execute(
        "SELECT * FROM app.daily_lessons WHERE id=%s FOR UPDATE", (identifier,)
    ).fetchone()
    if not row:
        raise HTTPException(404, "Lesson not found.")
    if decision == "confirm":
        # ASSUMPTION: renew an explicitly confirmed lesson for eight weeks.
        return db.execute(
            "UPDATE app.daily_lessons SET status='active',confirmed_at=now(),review_due=CURRENT_DATE+56 "
            "WHERE id=%s RETURNING *",
            (identifier,),
        ).fetchone()
    if decision == "retire":
        return db.execute(
            "UPDATE app.daily_lessons SET status='retired' WHERE id=%s RETURNING *", (identifier,)
        ).fetchone()
    if decision == "edit" and isinstance(text, str) and 0 < len(text.strip()) <= 400:
        return db.execute(
            "UPDATE app.daily_lessons SET text=%s WHERE id=%s RETURNING *",
            (text.strip(), identifier),
        ).fetchone()
    raise HTTPException(422, "Choose confirm, retire, or enter the edited lesson.")


def submit_review(db, day: date, zone: str, body: ReviewInput):
    _day_lock(db, day)
    meta = body.model_dump(mode="json", exclude={"key"})
    meta["timezone"] = zone
    old = db.execute("SELECT * FROM app.daily_reviews WHERE local_date=%s", (day,)).fetchone()
    previous_attempt = db.execute(
        "SELECT * FROM app.journal_entries WHERE id=%s", (body.key,)
    ).fetchone()
    if previous_attempt:
        if previous_attempt["meta"] != meta or previous_attempt["local_date"] != day:
            raise HTTPException(409, "This review request already has a different result.")
    else:
        task_ids = [item.task_id for item in body.next_steps]
        if len(task_ids) != len(set(task_ids)) or (
            task_ids
            and len(
                db.execute(
                    "SELECT id FROM app.tasks WHERE id=ANY(%s) AND state NOT IN ('completed','skipped')",
                    (task_ids,),
                ).fetchall()
            )
            != len(task_ids)
        ):
            raise HTTPException(422, "Choose each existing unfinished item once.")
        _entry(
            db,
            body.key,
            day,
            "text",
            "review",
            "\n".join(s for s in [body.worked, body.friction, body.tomorrow] if s),
            meta,
            old["entry_id"] if old else None,
        )
        db.execute(
            "INSERT INTO app.daily_reviews(local_date,entry_id,outcome,tomorrow,next_steps) "
            "VALUES (%s,%s,%s,%s,%s) ON CONFLICT(local_date) DO UPDATE SET entry_id=excluded.entry_id,"
            "outcome=excluded.outcome,tomorrow=excluded.tomorrow,next_steps=excluded.next_steps",
            (day, body.key, body.outcome, body.tomorrow, Jsonb(meta["next_steps"])),
        )
        if body.energy is not None:
            db.execute(
                "INSERT INTO app.routine_checkins(day,anchor,energy) VALUES (%s,'evening',%s) "
                "ON CONFLICT(day,anchor) DO UPDATE SET energy=excluded.energy",
                (day, body.energy),
            )
        db.execute(
            "UPDATE app.daily_lessons SET status='retired' WHERE local_date=%s "
            "AND slot>%s AND status='candidate'",
            (day, len(body.lessons)),
        )
        for slot, lesson in enumerate(body.lessons, 1):
            db.execute(
                "INSERT INTO app.daily_lessons(local_date,slot,evidence_id,text) VALUES (%s,%s,%s,%s) "
                "ON CONFLICT(local_date,slot) DO UPDATE SET text=excluded.text,evidence_id=excluded.evidence_id "
                "WHERE daily_lessons.status='candidate'",
                (day, slot, body.key, lesson),
            )
    return {
        "entry_id": body.key,
        "for_date": day,
        "lessons": db.execute(
            "SELECT * FROM app.daily_lessons WHERE local_date=%s ORDER BY slot", (day,)
        ).fetchall(),
    }


def _source_ref(kind, task_id, starts_at):
    if kind != "pre_task":
        return ""
    if not task_id or not starts_at or starts_at.tzinfo is None:
        raise HTTPException(422, "Choose a scheduled task and start time.")
    return f"{task_id}@{starts_at.astimezone(UTC).isoformat()}"


def get_brief(db, kind, day, task_id=None, starts_at=None):
    return db.execute(
        "SELECT * FROM app.daily_briefs WHERE kind=%s AND for_date=%s AND source_ref=%s",
        (kind, day, _source_ref(kind, task_id, starts_at)),
    ).fetchone()


def _tasks(db, day, zone):
    start, end = day_bounds(day, day, zone)
    return db.execute(
        "SELECT t.id,t.title,t.state,t.objective,t.effort,t.priority,t.progress,t.estimated_minutes,"
        "t.deadline_at,t.due_date,t.version,b.starts_at FROM app.tasks t "
        "LEFT JOIN LATERAL (SELECT min(starts_at) starts_at FROM app.execution_blocks "
        " WHERE task_id=t.id AND NOT cancelled AND starts_at<%s AND ends_at>%s) b ON true "
        "WHERE t.state<>'skipped' AND (t.occurrence_date=%s OR t.due_date=%s OR b.starts_at IS NOT NULL "
        " OR (t.deadline_at>=%s AND t.deadline_at<%s) OR (t.completed_at>=%s AND t.completed_at<%s)) "
        "ORDER BY t.priority,b.starts_at NULLS LAST,t.title,t.id",
        (end, start, day, day, start, end, start, end),
    ).fetchall()


def _pre_task(db, identifier, starts_at, zone):
    task = db.execute("SELECT * FROM app.tasks WHERE id=%s", (identifier,)).fetchone()
    if not task:
        raise HTTPException(404, "Task not found.")
    clock = starts_at.astimezone(ZoneInfo(zone)).strftime("%H:%M")
    lines = [f"{task['title']} is scheduled for {clock}."]
    if task["objective"] and task["objective"] != task["title"]:
        lines.append(f"The goal is {task['objective']}.")
    if task["deadline_at"]:
        deadline = task["deadline_at"].astimezone(ZoneInfo(zone)).strftime("%d %b at %H:%M")
        lines.append(f"The deadline is {deadline}.")
    elif task["due_date"]:
        lines.append(f"It is due on {task['due_date']}.")
    previous = db.execute(
        "SELECT elem->>'step' AS step,entry_id FROM app.daily_reviews "
        "CROSS JOIN LATERAL jsonb_array_elements(next_steps) elem WHERE elem->>'task_id'=%s "
        "AND local_date<= %s ORDER BY local_date DESC LIMIT 1",
        (str(identifier), starts_at.astimezone(ZoneInfo(zone)).date()),
    ).fetchone()
    lines.append(f"You planned {task['estimated_minutes']} minutes.")
    step = previous["step"] if previous else None
    if step:
        lines.append(f"Your first step: {step}.")
    else:
        lines.append("Open the work. Write down the smallest step you can finish in this block.")
    lines.append("If the whole block feels too large, begin with five minutes on that step.")
    return lines, {
        "task_id": identifier,
        "task_version": task["version"],
        "title": task["title"],
        "area": task["area"],
        "goal": task["objective"],
        "starts_at": starts_at,
        "next_step": step,
        "step_evidence_id": previous["entry_id"] if previous else None,
    }


def _morning(db, day, zone, tasks):
    start, end = day_bounds(day, day, zone)
    upcoming = [t for t in tasks if t["state"] != "completed"]
    clock = ZoneInfo(zone)
    commitments = db.execute(
        "SELECT title,starts_at FROM app.calendar_events "
        "WHERE NOT cancelled AND starts_at<%s AND ends_at>%s ORDER BY starts_at,id LIMIT 3",
        (end, start),
    ).fetchall()
    all_day = db.execute(
        "SELECT title FROM app.calendar_date_items WHERE NOT cancelled AND kind='event' "
        "AND starts_on<=%s AND ends_before>%s ORDER BY title,id LIMIT 3",
        (day, day),
    ).fetchall()
    deadlines = db.execute(
        "SELECT title,coalesce((deadline_at AT TIME ZONE %s)::date,due_date) AS due FROM app.tasks "
        "WHERE state NOT IN ('completed','skipped') AND coalesce((deadline_at AT TIME ZONE %s)::date,due_date) "
        "BETWEEN %s AND %s ORDER BY due,priority,id LIMIT 3",
        (zone, zone, day, day + timedelta(days=6)),
    ).fetchall()
    last_review = db.execute(
        "SELECT tomorrow FROM app.daily_reviews WHERE local_date=%s", (day - timedelta(days=1),)
    ).fetchone()
    plan = db.execute(
        "SELECT intention FROM app.daily_plans WHERE day=%s AND timezone=%s", (day, zone)
    ).fetchone()
    target = (
        (plan or {}).get("intention")
        or (last_review or {}).get("tomorrow")
        or (upcoming or [{}])[0].get("title")
    )
    lines = [
        day.strftime("%A, %d %B") + ".",
        f"{len(upcoming)} planned task{'s' if len(upcoming) != 1 else ''}.",
    ]
    if target:
        lines.append(f"Today's focus: {target}")
    supports = [t["title"] for t in upcoming if t["title"] != target][:2]
    if supports:
        lines.append("Also planned: " + "; ".join(supports) + ".")
    if commitments or all_day:
        lines.append(
            "Calendar: "
            + "; ".join(
                [f"{e['starts_at'].astimezone(clock):%H:%M} {e['title']}" for e in commitments]
                + [e["title"] + " (all day)" for e in all_day]
            )
            + "."
        )
    if deadlines:
        lines.append(
            "Due this week: "
            + "; ".join(f"{d['title']} ({d['due']:%d %b})" for d in deadlines)
            + "."
        )
    lessons = db.execute(
        "SELECT id,text,evidence_id FROM app.daily_lessons WHERE status='active' AND "
        "local_date<%s AND review_due>=%s ORDER BY confirmed_at DESC LIMIT 1",
        (day, day),
    ).fetchall()
    if lessons:
        lines.append("From your last confirmed lesson: " + lessons[0]["text"])
    from .daily_filing import list_actions

    filing = list_actions(db, day - timedelta(days=1))
    if filing:
        applied = sum(a["state"] == "applied" for a in filing)
        pending = sum(a["state"] == "proposed" for a in filing)
        lines.append(f"Last night's filing: {applied} filed; {pending} awaiting your review.")
    from .daily_inputs import read_cached

    inputs = read_cached(db, day, zone)
    if upcoming and upcoming[0]["effort"] == "demanding":
        lines.append(
            "Use your best available focus window for the most demanding step. If time is tight, start with five minutes."
        )
    if inputs.get("weather"):
        lines.append(inputs["weather"]["text"])
    for item in inputs.get("news") or []:
        lines.append(f"{item['source']}: {item['title']}")
    lines.append("How is your energy, from 1 to 5?")
    return lines, {
        "task_count": len(upcoming),
        "focus": target,
        "priorities": supports,
        "lessons": lessons,
        "filing": filing,
        "weather": inputs.get("weather"),
        "news": inputs.get("news", []),
        "source_status": inputs.get("status", {}),
    }


def preview(db, kind, day, zone, task_id=None, starts_at=None):
    source = _source_ref(kind, task_id, starts_at)
    if kind == "pre_task":
        lines, details = _pre_task(db, task_id, starts_at, zone)
    elif kind in ("morning", "evening"):
        tasks = _tasks(db, day, zone)
        if kind == "morning":
            lines, details = _morning(db, day, zone, tasks)
        else:
            done = [t for t in tasks if t["state"] == "completed"]
            pending = [t for t in tasks if t["state"] != "completed"]
            lines = [
                f"{len(done)} of {len(tasks)} planned tasks completed."
                if tasks
                else "There were no planned tasks today.",
                "What would you like to carry into tomorrow?",
            ]
            details = {
                "unfinished": [{"task_id": t["id"], "title": t["title"]} for t in pending],
                "completed": [t["title"] for t in done],
            }
    else:
        raise HTTPException(422, "Choose a daily brief.")
    from .daily_routine_settings import ease_off

    quiet = ease_off(db, day)
    if quiet and kind in ("morning", "evening"):
        focus = details.get("focus")
        lines = [quiet, f"Today's focus: {focus}" if focus and kind == "morning" else lines[-1]]
        details = (
            {"short_form": True, "focus": focus} if kind == "morning" else {"short_form": True}
        )
    details = jsonable_encoder(details)
    return {
        "kind": kind,
        "for_date": day,
        "source_ref": source,
        "text": "\n".join(lines),
        "context": json.dumps(details, ensure_ascii=False),
        "input_hash": digest([day, zone, lines, details]),
        "details": details,
    }


def persist_brief(db, value):
    db.execute(
        "INSERT INTO app.daily_briefs(kind,for_date,source_ref,input_hash,text,context,details) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(kind,for_date,source_ref) DO UPDATE SET "
        "input_hash=excluded.input_hash,text=excluded.text,context=excluded.context,details=excluded.details,"
        "updated_at=now() WHERE daily_briefs.input_hash<>excluded.input_hash",
        (
            value["kind"],
            value["for_date"],
            value["source_ref"],
            value["input_hash"],
            value["text"],
            value["context"],
            Jsonb(value["details"]),
        ),
    )
    return value
