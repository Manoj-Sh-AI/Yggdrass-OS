"""Read the existing timetable before falling back to owner-selected local times."""

from datetime import date, datetime, time, timedelta
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .planning import day_bounds, matches


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class RoutineSettings(Strict):
    version: int = Field(ge=1)
    enabled: bool
    wake_time: time | None = None
    midday_time: time | None = None
    evening_time: time | None = None
    weekly_day: int = Field(default=5, ge=0, le=6)
    rest_day: int = Field(default=6, ge=0, le=6)
    city: str = Field(default="", max_length=100)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    approved_feeds: list[Annotated[str, Field(max_length=100)]] = Field(
        default_factory=list, max_length=12
    )
    open_channel: bool = False
    low_energy: int = Field(default=2, ge=1, le=5)
    low_days: int = Field(default=3, ge=1, le=5)
    skipped_days: int = Field(default=5, ge=1, le=30)

    @model_validator(mode="after")
    def coherent(self):
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("Provide both coordinates.")
        if self.rest_day == self.weekly_day:
            raise ValueError("Choose a weekly review day outside the rest day.")
        for value in (self.wake_time, self.midday_time, self.evening_time):
            if value and (value.tzinfo or value.second or value.microsecond):
                raise ValueError("Choose a local hour and minute.")
        return self


def settings(db):
    return db.execute("SELECT * FROM app.daily_routine_settings WHERE id=1").fetchone()


def timezone(db):
    row = db.execute("SELECT timezone FROM app.call_preferences WHERE singleton").fetchone()
    return row["timezone"] if row else "Europe/Berlin"


def save_settings(db, body, day):
    values = body.model_dump(exclude={"version"})
    # Column names come only from this fixed Pydantic model.
    columns = ", ".join(name + "=%s" for name in values)
    row = db.execute(
        "UPDATE app.daily_routine_settings SET "
        + columns
        + ", enabled_since=CASE WHEN NOT %s THEN NULL WHEN NOT enabled THEN %s ELSE enabled_since END,"
        "version=version+1 WHERE id=1 AND version=%s RETURNING *",
        (*values.values(), body.enabled, day, body.version),
    ).fetchone()
    if not row:
        raise HTTPException(
            409, "Routine settings changed on another device. Reload and try again."
        )
    return row


# ASSUMPTION: exact named timetable entries are anchors; a generic early task is never a wake-up.
ANCHORS = {
    "morning": ("wake up", "wake-up", "morning brief"),
    "midday": ("midday checkpoint",),
    "evening": ("evening review", "evening review and tomorrow setup"),
    "weekly": ("weekly review",),
}


def anchor_times(db, day: date, zone: str):
    pref = settings(db)
    times = {"filing": "02:00"}
    if day.weekday() == pref["rest_day"]:
        return times
    start, end = day_bounds(day, day, zone)
    rows = db.execute(
        "SELECT title, starts_at FROM app.calendar_events WHERE NOT cancelled "
        "AND starts_at>=%s AND starts_at<%s UNION ALL SELECT t.title,b.starts_at FROM app.execution_blocks b "
        "JOIN app.tasks t ON t.id=b.task_id WHERE NOT b.cancelled AND t.state<>'skipped' "
        "AND b.starts_at>=%s AND b.starts_at<%s ORDER BY starts_at",
        (start, end, start, end),
    ).fetchall()
    # Evaluate recurrence in the template's own time zone, including exceptions.
    templates = db.execute(
        "SELECT * FROM app.routine_templates WHERE active AND lower(trim(title))=ANY(%s)",
        ([name for names in ANCHORS.values() for name in names],),
    ).fetchall()
    for template in templates:
        tz = ZoneInfo(template["timezone"])
        for local_day in {
            start.astimezone(tz).date(),
            (end - timedelta(microseconds=1)).astimezone(tz).date(),
        }:
            when = datetime.combine(local_day, template["window_start"], tz)
            if (
                start <= when < end
                and matches(template, local_day)
                and not db.execute(
                    "SELECT 1 FROM app.routine_exceptions WHERE template_id=%s AND occurrence_date=%s",
                    (template["id"], local_day),
                ).fetchone()
            ):
                rows.append({"title": template["title"], "starts_at": when})
    fallback = {
        "morning": pref["wake_time"],
        "midday": pref["midday_time"],
        "evening": pref["evening_time"],
    }
    for kind, names in ANCHORS.items():
        match = min(
            (r["starts_at"] for r in rows if r["title"].strip().casefold() in names), default=None
        )
        selected = match.astimezone(ZoneInfo(zone)).time() if match else fallback.get(kind)
        if kind == "weekly" and selected is None and day.weekday() == pref["weekly_day"]:
            selected = pref["evening_time"]
        if selected:
            times[kind] = selected.strftime("%H:%M")
    return times


def ease_off(db, day):
    pref = settings(db)
    recent = db.execute(
        "SELECT day,avg(energy) AS energy FROM app.routine_checkins "
        "WHERE day BETWEEN %s AND %s GROUP BY day",
        (day - timedelta(days=4), day),
    ).fetchall()
    if sum(row["energy"] <= pref["low_energy"] for row in recent) >= pref["low_days"]:
        return "Your recent energy check-ins selected the shorter routine."
    since = pref["enabled_since"]
    if since:
        last = db.execute(
            "SELECT max(day) AS day FROM app.routine_checkins WHERE day<=%s", (day,)
        ).fetchone()["day"]
        if (day - max(since, last or since)).days >= pref["skipped_days"]:
            return "Your routine is in its shorter form. Resume whenever you like."
    return ""
