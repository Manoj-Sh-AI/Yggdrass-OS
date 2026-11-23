"""The scheduled and optional routines share one edition per local day, week or task."""

import hashlib
import random
from datetime import timedelta
from statistics import median

from fastapi import HTTPException
from psycopg.types.json import Jsonb

from .daily_routine_settings import ease_off, settings
from .planning import day_bounds
from .routine_reflections import habit_data, propose_pattern

LABELS = {
    "shutdown": "Task shutdown",
    "rescue": "Stuck rescue",
    "midday": "Midday checkpoint",
    "radar": "Deadline radar",
    "weekly": "Weekly review",
    "intuition": "Intuition log",
    "scout": "Opportunity scout",
    "spark": "Spark (random)",
    "counter": "Counter-view",
    "outside": "Data",
    "wildcard": "Wildcard",
    "drift": "Drift check",
}
WEEKLY = {"weekly", "scout", "outside", "wildcard"}
OPEN = {"spark", "wildcard", "counter", "outside"}


def week_of(day):
    return day - timedelta(days=day.weekday())


def due_items(db, day, zone):
    rows = db.execute(
        """WITH due AS (SELECT t.id,t.title,coalesce((t.deadline_at AT TIME ZONE %s)::date,t.due_date) AS day,
        (SELECT count(DISTINCT (b.starts_at AT TIME ZONE %s)::date) FROM app.execution_blocks b
         WHERE b.task_id=t.id AND NOT b.cancelled AND (b.starts_at AT TIME ZONE %s)::date>=%s AND
         (b.starts_at AT TIME ZONE %s)::date<=coalesce((t.deadline_at AT TIME ZONE %s)::date,t.due_date)) AS planned_days
        FROM app.tasks t WHERE NOT t.done AND t.state<>'skipped')
        SELECT * FROM due WHERE day BETWEEN %s AND %s ORDER BY day,id LIMIT 5""",
        (zone, zone, zone, day, zone, zone, day, day + timedelta(days=90)),
    ).fetchall()
    return [
        f"{r['title']} · {r['day']:%d %b}"
        + (
            f" · {(r['day'] - day).days + 1 - r['planned_days']} days without a planned block"
            if r["planned_days"]
            else " · needs a time slot"
        )
        if (r["day"] - day).days <= 14
        else f"{r['title']} · {r['day']:%d %b}"
        for r in rows
    ]


def optional_guard(db, kind, day, zone, pref):
    if not pref["open_channel"]:
        return "The open channel is off."
    if reason := ease_off(db, day):
        return reason
    if kind == "spark":
        start, end = day_bounds(day, day + timedelta(days=1), zone)
        busy = db.execute(
            """SELECT 1 FROM app.tasks t WHERE NOT t.done AND t.state<>'skipped'
            AND (t.deadline_at BETWEEN %s AND %s OR (t.deadline_at IS NULL AND t.due_date BETWEEN %s AND %s)
            OR (t.effort='demanding' AND EXISTS (SELECT 1 FROM app.execution_blocks b WHERE b.task_id=t.id
                AND NOT b.cancelled AND b.starts_at < %s AND b.ends_at > %s))) LIMIT 1""",
            (start, end, day, day + timedelta(days=1), day_bounds(day, day, zone)[1], start),
        ).fetchone()
        if busy:
            return "The spark is paused for a demanding block or nearby deadline."
    return ""


def duration_summary(rows):
    if not rows:
        return []
    ratio = median(r["ratio"] for r in rows)
    return [f"{len(rows)} completed, timed tasks. Median time spent was {ratio:.2f}× the estimate."]


def energy_window(db, day):
    rows = db.execute(
        """SELECT anchor,avg(energy) AS energy,count(*) AS n FROM app.routine_checkins
        WHERE day BETWEEN %s AND %s GROUP BY anchor HAVING count(*)>=14 ORDER BY energy DESC,anchor""",
        (day - timedelta(days=20), day),
    ).fetchall()
    if len(rows) == 3 and rows[0]["energy"] > rows[1]["energy"]:
        return [
            f"Your highest reported energy was in the {rows[0]['anchor']} across these check-ins."
        ]
    return []


def render(db, kind, day, zone, *, task_id=None, subject=None, issue=False):
    if kind not in LABELS:
        raise HTTPException(422, "Unknown routine.")
    pref = settings(db)
    task = None
    if task_id:
        task = db.execute("SELECT * FROM app.tasks WHERE id=%s", (task_id,)).fetchone()
        if not task:
            raise HTTPException(404, "Task not found.")
    if kind in {"rescue", "shutdown", "drift", "counter"} and not task:
        raise HTTPException(422, "Choose a task or plan.")
    period = str(week_of(day) if kind in WEEKLY else day)
    if kind in {"rescue", "shutdown", "drift"}:
        period += ":" + str(subject or task_id)
    if kind == "counter":
        period = f"{task_id}:v{task['version']}"
    reason = optional_guard(db, kind, day, zone, pref) if kind in OPEN else ""
    if day.weekday() == pref["rest_day"] and kind in OPEN:
        reason = "It's your rest day."

    def result(lines, **extra):
        return {
            "kind": kind,
            "label": LABELS[kind],
            "for_date": day.isoformat(),
            "period": period,
            "lines": lines,
            "text": "\n".join(lines),
            **extra,
        }

    if reason:
        return result([], skipped=reason)
    existing = db.execute(
        "SELECT id,content FROM app.routine_editions WHERE kind=%s AND period=%s", (kind, period)
    ).fetchone()
    if existing and (issue or kind in OPEN):
        return {**existing["content"], "id": str(existing["id"])}
    lines = []
    short = ease_off(db, day)
    if kind == "radar":
        lines = due_items(db, day, zone)
    elif kind == "intuition":
        rows = db.execute(
            "SELECT domain,claim FROM app.routine_predictions WHERE resolved_at IS NULL AND due_date<=%s "
            "ORDER BY due_date,created_at LIMIT 3",
            (day,),
        ).fetchall()
        lines = [f"{r['domain']} · {r['claim']} — ready to resolve." for r in rows]
    elif kind in {"spark", "wildcard", "scout"}:
        pool = "opportunity" if kind == "scout" else kind
        rows = db.execute(
            "SELECT title,source_url,relevance FROM app.routine_pool WHERE kind=%s AND active ORDER BY id",
            (pool,),
        ).fetchall()
        if kind in {"wildcard", "spark"} and rows:
            # ASSUMPTION: fixed period seed makes retries reproducible without preference ranking.
            rng = random.Random(hashlib.sha256((kind + period).encode()).digest())
            rows = [rng.choice(rows)]
        lines = [
            " · ".join(s for s in (r["title"], r["relevance"], r["source_url"]) if s)
            for r in rows[:3]
        ]
    elif kind == "midday":
        plan = db.execute(
            "SELECT focus,intention FROM app.daily_plans WHERE day=%s AND timezone=%s", (day, zone)
        ).fetchone()
        focus = (plan["focus"] or plan["intention"]) if plan else ""
        lines = ([f"Today's focus: {focus}."] if focus else []) + [
            "How is your energy, from 1 to 5?"
        ]
    elif kind == "rescue":
        lines = [
            f"What is blocking {task['title']}?",
            "Choose a version you could finish in five minutes.",
            "Open the material for the first step.",
            "Choose a ten-minute focus block if it helps.",
            "If you're still stuck, pause and choose a lighter task.",
        ]
    elif kind == "shutdown":
        lines = [
            f"{task['title']} · {'completed' if task['done'] else 'block ended'}.",
            "Leave a one-line next step for when you return.",
        ]
    elif kind == "drift":
        lines = [f"The block for {task['title']} has passed. Keep its first step or move it?"]
    elif kind == "counter":
        deps = db.execute(
            "SELECT t.title FROM app.task_dependencies d JOIN app.tasks t ON t.id=d.depends_on "
            "WHERE d.task_id=%s AND NOT t.done ORDER BY t.title LIMIT 1",
            (task_id,),
        ).fetchone()
        lines = [
            f"For: the plan serves your stated objective, “{task['objective'] or task['title']}”.",
            f"Check the dependency “{deps['title']}” first."
            if deps
            else "Check whether any unrecorded dependency blocks the first step.",
            f"Time one small trial against the {task['estimated_minutes']}-minute estimate.",
            "Check whether the planned slot overlaps another commitment.",
            "A trial that fits the slot and clears its dependencies supports keeping the plan. Which check comes first?",
        ]
    elif kind == "outside":
        lines = duration_summary(habit_data(db, day, zone)) + energy_window(db, day)
    elif kind == "weekly":
        start, end = day_bounds(week_of(day), day, zone)
        done = db.execute(
            "SELECT DISTINCT ON (area) area,title FROM app.tasks WHERE completed_at>=%s AND completed_at<%s "
            "ORDER BY area,completed_at DESC LIMIT 5",
            (start, end),
        ).fetchall()
        lines = [f"{r['area']} · completed {r['title']}" for r in done]
        lines += due_items(db, day, zone)[:3]
        lines += ["Which outcome deserves the first available block next week?"]
        if issue and not short:
            propose_pattern(db, day, habit_data(db, day, zone))
    if short and lines:
        lines = [lines[0], short]
    output = result(lines)
    if issue and lines:
        edition = db.execute(
            "INSERT INTO app.routine_editions(kind,period,for_date,content) VALUES(%s,%s,%s,%s) "
            "ON CONFLICT(kind,period) DO NOTHING RETURNING id,content",
            (kind, period, day, Jsonb(output)),
        ).fetchone()
        if not edition:
            edition = db.execute(
                "SELECT id,content FROM app.routine_editions WHERE kind=%s AND period=%s",
                (kind, period),
            ).fetchone()
        output = {**edition["content"], "id": str(edition["id"])}
    return output
