"""Free time on Manoj's calendar, computed by code (no model call).

Busy = calendar events + task time blocks + routine occurrences (their planned block, else
window start for the expected minutes), each padded by BUFFER. A day runs from the end of
quiet hours to their start (08:00-22:00 Europe/Berlin by default) and never before now.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

BUFFER = timedelta(minutes=10)
MAX_SLOTS = 8


def busy(db, start: datetime, end: datetime) -> list[tuple[datetime, datetime, str]]:
    rows = [
        (r["starts_at"], r["ends_at"], r["title"])
        for r in db.execute(
            "SELECT starts_at,ends_at,title FROM app.calendar_events "
            "WHERE NOT cancelled AND starts_at<%s AND ends_at>%s",
            (end, start),
        ).fetchall()
    ]
    rows += [
        (r["starts_at"], r["ends_at"], r["title"])
        for r in db.execute(
            "SELECT b.starts_at,b.ends_at,t.title FROM app.execution_blocks b "
            "JOIN app.tasks t ON t.id=b.task_id WHERE NOT b.cancelled AND NOT t.done "
            "AND t.state<>'skipped' AND b.starts_at<%s AND b.ends_at>%s",
            (end, start),
        ).fetchall()
    ]
    rows += routine_busy(db, start, end)
    return sorted(rows)


def routine_busy(db, start: datetime, end: datetime):
    """Routine occurrences without a planned block still take their window start."""
    from .planning import matches, wall_instant

    out = []
    for template in db.execute("SELECT * FROM app.routine_templates WHERE active").fetchall():
        zone = ZoneInfo(template["timezone"])
        day = start.astimezone(zone).date()
        while datetime.combine(day, time.min, zone) < end:
            if (
                matches(template, day)
                and not db.execute(
                    "SELECT 1 FROM app.routine_exceptions WHERE template_id=%s AND occurrence_date=%s",
                    (template["id"], day),
                ).fetchone()
            ):
                task = db.execute(
                    "SELECT id,state,done FROM app.tasks WHERE template_id=%s AND occurrence_date=%s",
                    (template["id"], day),
                ).fetchone()
                planned = (
                    db.execute(
                        "SELECT 1 FROM app.execution_blocks WHERE task_id=%s AND NOT cancelled",
                        (task["id"],),
                    ).fetchone()
                    if task
                    else None
                )
                if not planned and not (task and (task["done"] or task["state"] == "skipped")):
                    try:
                        at = wall_instant(
                            datetime.combine(day, template["window_start"]), template["timezone"]
                        )
                        out.append(
                            (
                                at,
                                at + timedelta(minutes=template["expected_minutes"]),
                                template["title"],
                            )
                        )
                    except Exception:  # noqa: BLE001, S110 -- a DST gap: no busy time that day
                        pass
            day += timedelta(days=1)
    return out


def free_slots(
    db,
    first: date,
    days: int,
    minutes: int,
    *,
    timezone: str = "Europe/Berlin",
    day_start: time = time(8, 0),
    day_end: time = time(22, 0),
    now: datetime | None = None,
) -> list[dict]:
    """Gaps of at least `minutes` between busy items, earliest first, at most MAX_SLOTS."""
    zone, now = ZoneInfo(timezone), (now or datetime.now(UTC))
    need = timedelta(minutes=max(1, minutes))
    slots = []
    for offset in range(max(1, min(days, 14))):
        day = first + timedelta(days=offset)
        opens = max(datetime.combine(day, day_start, zone), now)
        closes = datetime.combine(day, day_end, zone)
        if closes - opens < need:
            continue
        cursor = opens
        for starts, ends, _title in busy(db, opens - BUFFER, closes + BUFFER):
            if starts - BUFFER - cursor >= need:
                slots.append((cursor, starts - BUFFER))
            cursor = max(cursor, ends + BUFFER)
        if closes - cursor >= need:
            slots.append((cursor, closes))
        if len(slots) >= MAX_SLOTS:
            break
    return [
        {
            "start": a.astimezone(zone).isoformat(),
            "end": b.astimezone(zone).isoformat(),
            "minutes": int((b - a).total_seconds() // 60),
        }
        for a, b in slots[:MAX_SLOTS]
    ]


def planned_minutes_left(db, now: datetime, timezone: str = "Europe/Berlin") -> int:
    """Minutes of events, task blocks and routines still ahead today (for workload advice)."""
    zone = ZoneInfo(timezone)
    end = datetime.combine(now.astimezone(zone).date(), time(23, 59), zone)
    total = timedelta()
    for starts, ends, _title in busy(db, now, end):
        total += min(ends, end) - max(starts, now)
    return max(0, int(total.total_seconds() // 60))
