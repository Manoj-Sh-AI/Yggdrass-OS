"""What happened to each scheduled item occurrence, and the rules that decide it.

One append-only audit trail (app.item_outcomes, migration 014): the newest row for an
occurrence is its outcome. Rules (Manoj, 2026-11-20):
- a missed reminder call is retried twice, 5 and 10 minutes after the first miss;
- after both retries go unanswered, a one-off item (an event) counts as completed and a
  recurring one (a routine) as not answered;
- when an item's time slot ends it counts as completed (events always; tasks once started);
- the next call for a routine first asks about an unanswered earlier occurrence.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

RETRIES = (timedelta(minutes=5), timedelta(minutes=10))  # after the first missed call
FINAL = ("completed", "not_done", "not_answered", "removed")
RETRYABLE = ("event_start", "routine", "snooze", "retry")
SLOT_END_WINDOW = timedelta(hours=2)  # only recent slots: no backfill of old history
FOLLOW_UP_DAYS = 14


def occurrence(item) -> tuple[str, str, date]:
    """(item_kind, item_id, local date) of a call_briefs.item_for() item."""
    zone = ZoneInfo(item.get("timezone") or "Europe/Berlin")
    return item["kind"], str(item["id"]), item["starts_at"].astimezone(zone).date()


def record(db, kind, item_id, day, outcome, decided_by, call_id=None, note="") -> None:
    db.execute(
        "INSERT INTO app.item_outcomes(id,item_kind,item_id,occurrence,outcome,decided_by,call_id,note) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
        (uuid4(), kind, item_id, day, outcome, decided_by, call_id, note[:500]),
    )


def latest(db, kind, item_id, day):
    return db.execute(
        "SELECT * FROM app.item_outcomes WHERE item_kind=%s AND item_id=%s AND occurrence=%s "
        "ORDER BY at DESC, id LIMIT 1",
        (kind, item_id, day),
    ).fetchone()


def is_final(db, kind, item_id, day) -> bool:
    row = latest(db, kind, item_id, day)
    return bool(row) and row["outcome"] in FINAL


def cancel_retries(db, original_key: str) -> None:
    """Manoj answered (or acted) about this reminder: no retry rings after that."""
    if original_key:
        db.execute(
            "UPDATE app.call_schedules SET state='cancelled' WHERE state='pending' AND kind='retry' "
            "AND source_key LIKE %s",
            ("retry:%:" + original_key,),
        )


# ------------------------------------------------------------------ missed calls


def after_missed(db, call, now: datetime) -> str | None:
    """A reminder call went unanswered: schedule the next retry, or after the second retry
    decide the outcome. Returns what was done (for tests and the audit)."""
    from .call_briefs import brief_key, item_for

    schedule = db.execute(
        "SELECT * FROM app.call_schedules WHERE call_id=%s ORDER BY due_at DESC LIMIT 1",
        (call["id"],),
    ).fetchone()
    if (
        not schedule
        or schedule["kind"] not in RETRYABLE
        or schedule["source_type"] not in ("event", "routine")
        or not schedule["source_key"]
    ):
        return None
    item = item_for(db, schedule)
    if item is None:
        return None
    kind, item_id, day = occurrence(item)
    if is_final(db, kind, item_id, day):
        return None
    original = brief_key(schedule["source_key"])
    tried = db.execute(
        "SELECT due_at FROM app.call_schedules WHERE kind='retry' AND source_key LIKE %s ORDER BY due_at",
        ("retry:%:" + original,),
    ).fetchall()
    if len(tried) < len(RETRIES):
        first_miss = tried[0]["due_at"] - RETRIES[0] if tried else now
        due = max(now, first_miss + RETRIES[len(tried)])
        db.execute(
            "INSERT INTO app.call_schedules(id,kind,due_at,reason,source_key,source_type,source_id,source_revision) "
            "VALUES (%s,'retry',%s,'Retry reminder',%s,%s,%s,%s)",
            (uuid4(), due, f"retry:{len(tried) + 1}:{original}", schedule["source_type"],
             schedule["source_id"], schedule["source_revision"]),
        )  # fmt: skip
        return f"retry {len(tried) + 1}"
    outcome = "completed" if kind == "event" else "not_answered"
    record(db, kind, item_id, day, outcome, "after_retries", call["id"],
           "Two retries went unanswered.")  # fmt: skip
    return outcome


# ------------------------------------------------------------------ slot end


def complete_ended(db, now: datetime) -> int:
    """Items whose time slot just ended count as completed (Manoj's rule): every event,
    and every task already started. Unstarted routines are left to the retry rule."""
    from .planning import execute_task
    from .planning_models import ExecutionInput

    done = 0
    since = now - SLOT_END_WINDOW
    for event in db.execute(
        "SELECT id,starts_at,timezone FROM app.calendar_events WHERE NOT cancelled "
        "AND ends_at<=%s AND ends_at>%s",
        (now, since),
    ).fetchall():
        day = event["starts_at"].astimezone(ZoneInfo(event["timezone"])).date()
        if not is_final(db, "event", str(event["id"]), day):
            record(db, "event", str(event["id"]), day, "completed", "slot_end")
            done += 1
    for task in db.execute(
        "SELECT t.*, (SELECT max(b.ends_at) FROM app.execution_blocks b WHERE b.task_id=t.id "
        "AND NOT b.cancelled) AS slot_end, r.window_end, r.timezone AS routine_zone "
        "FROM app.tasks t LEFT JOIN app.routine_templates r ON r.id=t.template_id "
        "WHERE t.state IN ('in_progress','paused') AND NOT t.done FOR UPDATE OF t"
    ).fetchall():
        end = task["slot_end"]
        if end is None and task["window_end"] is not None and task["occurrence_date"]:
            end = datetime.combine(
                task["occurrence_date"], task["window_end"], ZoneInfo(task["routine_zone"])
            )
        if end is None or not since < end <= now:
            continue
        try:
            execute_task(db, task, ExecutionInput(action="complete"))
        except Exception:  # noqa: BLE001, S112 -- e.g. open subtasks: leave it for Manoj
            continue
        kind = "routine" if task["template_id"] else "task"
        item_id = str(task["template_id"] or task["id"])
        day = task["occurrence_date"] or end.astimezone(ZoneInfo(task["timezone"])).date()
        record(db, kind, item_id, day, "completed", "slot_end")
        done += 1
    return done


# ------------------------------------------------------------------ the next routine call


def follow_up(db, template_id, today: date) -> dict | None:
    """The newest earlier occurrence of this routine left 'not answered' (last 14 days)."""
    row = db.execute(
        "SELECT DISTINCT ON (occurrence) occurrence,outcome FROM app.item_outcomes "
        "WHERE item_kind='routine' AND item_id=%s AND occurrence<%s AND occurrence>=%s "
        "ORDER BY occurrence DESC, at DESC",
        (str(template_id), today, today - timedelta(days=FOLLOW_UP_DAYS)),
    ).fetchall()
    for occ in row:  # newest occurrence first
        if occ["outcome"] == "not_answered":
            template = db.execute(
                "SELECT title,expected_minutes FROM app.routine_templates WHERE id=%s",
                (template_id,),
            ).fetchone()
            return {"day": occ["occurrence"], "title": template["title"],
                    "minutes": template["expected_minutes"]}  # fmt: skip
        return None
    return None


def resolve_follow_up(db, template_id, day: date, did_it: bool, call_id=None) -> None:
    from .planning import execute_task
    from .planning_models import ExecutionInput

    record(db, "routine", str(template_id), day, "completed" if did_it else "not_done",
           "follow_up", call_id, "Answered on the next call.")  # fmt: skip
    if did_it:
        task = db.execute(
            "SELECT * FROM app.tasks WHERE template_id=%s AND occurrence_date=%s AND NOT done",
            (template_id, day),
        ).fetchone()
        if task and task["state"] != "skipped":
            try:
                execute_task(db, task, ExecutionInput(action="complete"))
            except Exception:  # noqa: BLE001, S110 -- the outcome row is the record
                pass


def workload_note(db, missed: dict, today_minutes: int, now: datetime | None = None) -> str:
    """Spoken advice when a missed occurrence was not done: before + now, one suggestion."""
    from .free_slots import planned_minutes_left

    now = now or datetime.now(UTC)
    left = planned_minutes_left(db, now)
    total = missed["minutes"] + today_minutes
    weekday = missed["day"].strftime("%A")
    if total <= 60:
        advice = "You could do both now, back to back."
    else:
        advice = "I'd do today's now and find a free slot for the missed one."
    return (
        f"That leaves {missed['minutes']} minutes from {weekday} plus {today_minutes} today, "
        f"{total} in all, with {left} more minutes already planned today. {advice} "
        "Shall I start today's now?"
    )
