"""Leased, restart-safe scheduling of the owner's daily routines and important blocks."""

from __future__ import annotations

import logging
from contextlib import contextmanager
from datetime import UTC, date, datetime, time, timedelta
from threading import Event, Thread
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from psycopg.types.json import Jsonb

from .call_service import quiet

DAY_LOCK = 719218432
LEASE = timedelta(minutes=4)
STALE_AFTER = {
    "prep": 120,
    "notify": 120,
    "call": 120,
    "retry": 120,
    "outcome": 3600,
    "morning": 1800,
    "evening": 3600,
    "midday": 1800,
    "weekly": 7200,
}
ANCHORS = ("morning", "midday", "evening", "weekly", "filing")


def anchor_instant(day: date, wall: time, zone: str) -> datetime:
    """ASSUMPTION: first fold in autumn; a missing spring hour moves forward by its gap."""
    return datetime.combine(day, wall, ZoneInfo(zone)).replace(fold=0).astimezone(UTC)


def put(db, kind, run_at, key, source, payload):
    return db.execute(
        "INSERT INTO app.scheduled_jobs(kind,payload,run_at,available_at,dedupe_key,source_ref) "
        "VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT(dedupe_key) DO NOTHING RETURNING id",
        (kind, Jsonb(payload), run_at, run_at, key, source),
    ).fetchone()


def mark(db, block_id, enabled, now=None):
    now = now or datetime.now(UTC)
    db.execute("SELECT pg_advisory_xact_lock(%s)", (DAY_LOCK,))
    row = db.execute(
        "SELECT b.*,t.state,t.done FROM app.execution_blocks b JOIN app.tasks t ON t.id=b.task_id "
        "WHERE b.id=%s FOR UPDATE OF b",
        (block_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(404, "The scheduled block could not be found.")
    if not enabled:
        db.execute("DELETE FROM app.routine_important_blocks WHERE block_id=%s", (block_id,))
    elif not db.execute(
        "SELECT 1 FROM app.routine_important_blocks WHERE block_id=%s", (block_id,)
    ).fetchone():
        if row["cancelled"] or row["starts_at"] <= now or row["state"] not in ("todo", "paused"):
            raise HTTPException(409, "Choose an upcoming block for an open task.")
        pref = db.execute("SELECT timezone FROM app.call_preferences").fetchone()
        zone = pref["timezone"] if pref else "Europe/Berlin"
        day = row["starts_at"].astimezone(ZoneInfo(zone)).date()
        rows = db.execute(
            "SELECT b.task_id FROM app.routine_important_blocks i JOIN app.execution_blocks b "
            "ON b.id=i.block_id JOIN app.tasks t ON t.id=b.task_id WHERE NOT b.cancelled "
            "AND NOT t.done AND (b.starts_at AT TIME ZONE %s)::date=%s "
            "UNION SELECT task_id FROM app.routine_escalations WHERE local_day=%s",
            (zone, day, day),
        ).fetchall()
        if row["task_id"] in {r["task_id"] for r in rows}:
            raise HTTPException(409, "This task already has an important reminder for the day.")
        if len(rows) >= 3:
            raise HTTPException(409, "Choose up to three important tasks per day.")
        db.execute("INSERT INTO app.routine_important_blocks(block_id) VALUES (%s)", (block_id,))
    return {"block_id": str(block_id), "important": enabled}


def acknowledge(db, escalation_id, action, now=None):
    if action not in ("started", "not_yet"):
        raise HTTPException(422, "Choose Started or Not yet.")
    now = now or datetime.now(UTC)
    row = _escalation(db, escalation_id)
    if row["state"] == "started" and action == "started":
        return {"id": str(row["id"]), "state": "started"}
    if row["state"] not in ("sent", "called", "snoozed", "call_failed"):
        raise HTTPException(409, "This reminder is no longer current.")
    if action == "not_yet":
        # ASSUMPTION: Not yet records the tap and keeps the original call deadline.
        db.execute(
            "UPDATE app.routine_escalations SET not_yet_at=coalesce(not_yet_at,%s) WHERE id=%s",
            (now, row["id"]),
        )
        return {"id": str(row["id"]), "state": row["state"]}
    db.execute("UPDATE app.routine_escalations SET state='started' WHERE id=%s", (row["id"],))
    if row["call_id"]:
        # A tap racing a ring should also dismiss the ring already visible on another device.
        ended = db.execute(
            "UPDATE app.calls SET state='ended',media_state='ended',ended_at=%s,"
            "version=version+1 WHERE id=%s AND state='ringing' RETURNING id",
            (now, row["call_id"]),
        ).fetchone()
        if ended:
            db.execute(
                "INSERT INTO app.call_events(call_id,state) VALUES (%s,'ended')", (row["call_id"],)
            )
            db.execute(
                "INSERT INTO app.call_delivery(call_id,device_id,event_state) "
                "SELECT call_id,device_id,'ended' FROM app.call_delivery WHERE call_id=%s "
                "AND event_state='ringing' ON CONFLICT DO NOTHING",
                (row["call_id"],),
            )
    db.execute(
        "UPDATE app.scheduled_jobs SET status='cancelled',outcome='started' "
        "WHERE source_ref=%s AND payload->>'escalation_id'=%s AND status='pending'",
        ("block:" + str(row["block_id"]), str(row["id"])),
    )
    return {"id": str(row["id"]), "state": "started"}


def _escalation(db, identifier):
    row = db.execute(
        "SELECT * FROM app.routine_escalations WHERE id=%s FOR UPDATE", (identifier,)
    ).fetchone()
    if not row:
        raise HTTPException(404, "Reminder not found.")
    return row


def _follow_up(db, row, kind, at, suffix):
    payload = {
        "escalation_id": str(row["id"]),
        "starts_at": row["starts_at"].isoformat(),
        "block_id": str(row["block_id"]),
    }
    put(db, kind, at, f"{row['id']}:{suffix}", "block:" + str(row["block_id"]), payload)


def acknowledge_voice(db, escalation_id, action, minutes=5, now=None):
    now = now or datetime.now(UTC)
    if action == "confirm":
        return acknowledge(db, escalation_id, "started", now)
    if action != "snooze":
        raise HTTPException(422, "Choose confirm or snooze.")
    row = _escalation(db, escalation_id)
    if row["state"] == "snoozed":
        return {"id": str(row["id"]), "state": "snoozed"}
    if row["state"] != "called" or row["attempts"] >= 2:
        raise HTTPException(409, "This reminder cannot ring again.")
    delay = timedelta(minutes=max(1, min(30, minutes)))
    db.execute("UPDATE app.routine_escalations SET state='snoozed' WHERE id=%s", (escalation_id,))
    _follow_up(db, row, "retry", now + delay, "snooze")
    return {"id": str(row["id"]), "state": "snoozed"}


def claim(db, now):
    """Claim committed separately. A reclaimed job gets a fresh attempt as a fencing token."""
    for job in db.execute(
        "SELECT * FROM app.scheduled_jobs WHERE status='running' AND locked_until<=%s "
        "ORDER BY locked_until LIMIT 30 FOR UPDATE SKIP LOCKED",
        (now,),
    ).fetchall():
        db.execute(
            "UPDATE app.scheduled_job_attempts SET outcome='lease expired',finished_at=%s "
            "WHERE job_id=%s AND attempt=%s",
            (now, job["id"], job["attempts"]),
        )
        state = "failed" if job["attempts"] >= job["max_attempts"] else "pending"
        db.execute(
            "UPDATE app.scheduled_jobs SET status=%s,locked_until=NULL,outcome='lease expired' "
            "WHERE id=%s",
            (state, job["id"]),
        )
    job = db.execute(
        "WITH picked AS (SELECT id FROM app.scheduled_jobs WHERE status='pending' AND "
        "available_at<=%s ORDER BY available_at,id LIMIT 1 FOR UPDATE SKIP LOCKED) "
        "UPDATE app.scheduled_jobs j SET status='running',attempts=attempts+1,locked_until=%s "
        "FROM picked WHERE j.id=picked.id RETURNING j.*",
        (now, now + LEASE),
    ).fetchone()
    if job:
        db.execute(
            "INSERT INTO app.scheduled_job_attempts(job_id,attempt,started_at) VALUES (%s,%s,%s)",
            (job["id"], job["attempts"], now),
        )
    return job


def renew(db, job, now):
    return (
        db.execute(
            "UPDATE app.scheduled_jobs SET locked_until=%s WHERE id=%s AND status='running' "
            "AND attempts=%s AND locked_until>%s",
            (now + LEASE, job["id"], job["attempts"], now),
        ).rowcount
        == 1
    )


@contextmanager
def keep_lease(database, job, now):
    """Keep slow context/filing requests leased without pinning a pooled DB connection."""
    done = Event()

    def heartbeat():
        while not done.wait(30):
            try:
                with database.connect() as db:
                    if not renew(db, job, now()):
                        return
            except Exception:  # noqa: BLE001 -- retry on the next beat within the existing lease
                continue

    thread = Thread(target=heartbeat, daemon=True, name="routine-lease")
    thread.start()
    try:
        yield
    finally:
        done.set()
        thread.join(timeout=1)


def finish(db, job, now, outcome, retry=False):
    state = "done"
    if retry:
        state = "pending" if job["attempts"] < job["max_attempts"] else "failed"
    db.execute(
        "UPDATE app.scheduled_jobs SET status=%s,outcome=%s,available_at=%s,locked_until=NULL "
        "WHERE id=%s AND status='running' AND attempts=%s",
        (state, outcome, now + timedelta(seconds=15 * job["attempts"]), job["id"], job["attempts"]),
    )
    db.execute(
        "UPDATE app.scheduled_job_attempts SET outcome=%s,finished_at=%s "
        "WHERE job_id=%s AND attempt=%s AND finished_at IS NULL",
        (outcome, now, job["id"], job["attempts"]),
    )


class RoutineScheduler:
    def __init__(self, database, calls, lia=None, *, now=None, anchor_handler=None):
        self.database, self.calls, self.lia = database, calls, lia
        self.now = now or (lambda: datetime.now(UTC))
        self.anchor_handler = anchor_handler
        self.stopped = Event()
        self.thread = None

    def start(self):
        self.thread = Thread(target=self.loop, daemon=True, name="yggdras-daily-routines")
        self.thread.start()

    def stop(self):
        self.stopped.set()
        if self.thread:
            self.thread.join(timeout=3)

    def loop(self):
        while not self.stopped.is_set():
            try:
                self.tick()
            except Exception as exc:  # noqa: BLE001 -- only the failure class may leave the worker
                logging.getLogger(__name__).error("Routine sweep failed (%s)", type(exc).__name__)
            self.stopped.wait(15)

    @staticmethod
    def enabled(db):
        return bool(db.execute("SELECT 1 FROM app.daily_routine_settings WHERE enabled").fetchone())

    def seed(self, db, zone, now):
        from .daily_routine_settings import anchor_times

        today = now.astimezone(ZoneInfo(zone)).date()
        # One open occurrence per kind. Filing catches up after outages; obsolete notifications
        # are never replayed. Recompute local intent on every sweep so timetable edits take effect.
        open_rows = {
            r["kind"]: r
            for r in db.execute(
                "SELECT * FROM app.scheduled_jobs WHERE source_ref='anchors' AND status IN "
                "('pending','running') ORDER BY run_at"
            ).fetchall()
        }
        last = {
            r["kind"]: r["last_day"]
            for r in db.execute(
                "SELECT kind,max((payload->>'day')::date) AS last_day FROM app.scheduled_jobs "
                "WHERE source_ref='anchors' AND status IN ('done','failed') GROUP BY kind"
            ).fetchall()
        }
        timetable = {}
        for kind in ANCHORS:
            start = today
            if kind in last:
                following = last[kind] + timedelta(days=1)
                start = following if kind == "filing" else max(start, following)
            current = open_rows.get(kind)
            if current and kind == "filing":
                start = min(start, date.fromisoformat(current["payload"]["day"]))
            desired = None
            for offset in range(8):
                day = start + timedelta(days=offset)
                if day not in timetable:
                    timetable[day] = anchor_times(db, day, zone)
                wall = timetable[day].get(kind)
                if wall is not None:
                    at = anchor_instant(day, time.fromisoformat(wall), zone)
                    desired = (day, at)
                    break
            if current:
                if (
                    desired
                    and desired[1] == current["run_at"]
                    and zone == current["payload"]["zone"]
                ):
                    continue
                db.execute(
                    "UPDATE app.scheduled_jobs SET status='cancelled',outcome='anchor moved' WHERE id=%s "
                    "AND status='pending'",
                    (current["id"],),
                )
                if current["status"] == "running":
                    continue
            if desired:
                day, at = desired
                key = f"anchor:{kind}:{zone}:{day}:{at.isoformat()}"
                put(db, kind, at, key, "anchors", {"day": day.isoformat(), "zone": zone})
                db.execute(
                    "UPDATE app.scheduled_jobs SET status='pending',outcome='',available_at=run_at "
                    "WHERE dedupe_key=%s AND status='cancelled' AND outcome='anchor moved'",
                    (key,),
                )

    def tick(self):
        from .daily_routine_api import sweep_blocks
        from .routine_delivery import drain_notices

        with self.database.connect() as db:
            if not self.enabled(db):
                return
            db.execute("SELECT pg_advisory_xact_lock(%s)", (DAY_LOCK,))
            self.seed(db, self.calls.preferences(db)["timezone"], self.now())
        sweep_blocks(self.database, self.now())
        for _ in range(30):
            if self.stopped.is_set():
                break
            with self.database.connect() as db:
                job = claim(db, self.now())
            if not job:
                break
            try:
                self.run_job(job)
            except Exception as exc:  # noqa: BLE001 -- record a sanitized failure, then retry
                with self.database.connect() as db:
                    finish(db, job, self.now(), type(exc).__name__, retry=True)
        drain_notices(self.database, self.calls.auth_fingerprint)

    def run_job(self, job):
        now = self.now()
        with self.database.connect() as db:
            # Use the same lock order as mark(). Ack locks its escalation first; never retain
            # a SELECT FOR UPDATE on the job while waiting for that escalation.
            db.execute("SELECT pg_advisory_xact_lock(%s)", (DAY_LOCK,))
            current = db.execute(
                "SELECT status,attempts FROM app.scheduled_jobs WHERE id=%s", (job["id"],)
            ).fetchone()
            if current["status"] != "running" or current["attempts"] != job["attempts"]:
                finish(db, job, now, "superseded")
                return
            kind = job["kind"]
            pref = self.calls.preferences(db)
            ttl = STALE_AFTER.get(kind)
            skip = ""
            if not self.enabled(db):
                skip = "disabled"
            elif ttl and (now - job["run_at"]).total_seconds() > ttl:
                skip = "stale"
            elif kind not in ("prep", "filing", "outcome") and quiet(now, pref):
                skip = "quiet hours"
            elif kind in ANCHORS:
                from .daily_routine_settings import anchor_times

                day = date.fromisoformat(job["payload"]["day"])
                zone = pref["timezone"]
                wall = anchor_times(db, day, zone).get(kind)
                if (
                    not wall
                    or zone != job["payload"]["zone"]
                    or anchor_instant(day, time.fromisoformat(wall), zone) != job["run_at"]
                ):
                    db.execute(
                        "UPDATE app.scheduled_jobs SET status='cancelled',outcome='anchor moved' "
                        "WHERE id=%s",
                        (job["id"],),
                    )
                    skip = "anchor moved"
            elif (
                now.astimezone(ZoneInfo(pref["timezone"])).weekday()
                == db.execute(
                    "SELECT rest_day FROM app.daily_routine_settings WHERE id=1"
                ).fetchone()["rest_day"]
            ):
                skip = "rest day"
            if skip:
                if job["payload"].get("escalation_id"):
                    db.execute(
                        "UPDATE app.routine_escalations SET state='expired' WHERE id=%s "
                        "AND state IN ('sent','snoozed')",
                        (job["payload"]["escalation_id"],),
                    )
                finish(db, job, now, skip)
                return
            if kind not in ANCHORS:
                result = self.run_task_job(db, job, pref, now)
                finish(db, job, now, result)
                return
        # Filing can call Lia. Do not hold a connection while awaiting an external service.
        from .daily_routine_api import run_anchor

        payload = job["payload"]
        with keep_lease(self.database, job, self.now):
            (self.anchor_handler or run_anchor)(
                self.database,
                self.lia,
                kind,
                date.fromisoformat(payload["day"]),
                payload["zone"],
                now,
            )
        with self.database.connect() as db:
            finish(db, job, self.now(), "completed")

    def run_task_job(self, db, job, pref, now):
        from .daily_content import persist_brief, preview
        from .routine_delivery import queue_notice, ring_reminder

        kind, payload = job["kind"], job["payload"]
        block = db.execute(
            "SELECT b.*,t.version AS task_version,t.title,t.deadline_at,t.state,t.done "
            "FROM app.execution_blocks b JOIN app.tasks t ON t.id=b.task_id "
            "JOIN app.routine_important_blocks i ON i.block_id=b.id WHERE b.id=%s",
            (payload["block_id"],),
        ).fetchone()
        if (
            not block
            or block["done"]
            or block["cancelled"]
            or block["state"] not in ("todo", "paused")
            or block["starts_at"] != datetime.fromisoformat(payload["starts_at"])
        ):
            return "timetable changed"
        day = block["starts_at"].astimezone(ZoneInfo(pref["timezone"])).date()
        if kind in ("prep", "notify") and (
            block["version"] != payload["block_version"]
            or block["task_version"] != payload["task_version"]
        ):
            return "superseded"
        if kind == "prep":
            brief = preview(
                db,
                "pre_task",
                day,
                pref["timezone"],
                task_id=block["task_id"],
                starts_at=block["starts_at"],
            )
            persist_brief(db, brief)
            return "prepared"
        if kind == "notify":
            sent = db.execute(
                "SELECT task_id FROM app.routine_escalations WHERE local_day=%s", (day,)
            ).fetchall()
            if len(sent) >= 3 or block["task_id"] in {r["task_id"] for r in sent}:
                return "daily limit or already sent"
            summary, context = self.prepared(db, block, day, pref["timezone"])
            row = db.execute(
                "INSERT INTO app.routine_escalations(id,block_id,task_id,starts_at,local_day,zone,state,summary,context) "
                "VALUES (%s,%s,%s,%s,%s,%s,'sent',%s,%s) ON CONFLICT DO NOTHING RETURNING *",
                (
                    uuid4(),
                    block["id"],
                    block["task_id"],
                    block["starts_at"],
                    day,
                    pref["timezone"],
                    summary,
                    context,
                ),
            ).fetchone()
            if row:
                queue_notice(
                    db, key=f"important:{row['id']}", escalation_id=row["id"], kind="pre_task"
                )
                _follow_up(db, row, "call", block["starts_at"] + timedelta(minutes=5), "call")
            return "notification queued"
        row = _escalation(db, payload["escalation_id"])
        if kind == "outcome":
            if row["state"] != "called":
                return "already handled"
            state = db.execute(
                "SELECT state FROM app.calls WHERE id=%s", (row["call_id"],)
            ).fetchone()
            if state and state["state"] == "ringing":
                self.calls.expire(db)
                state = db.execute(
                    "SELECT state FROM app.calls WHERE id=%s", (row["call_id"],)
                ).fetchone()
            if state and state["state"] == "missed" and row["attempts"] < 2:
                _follow_up(db, row, "retry", now + timedelta(minutes=5), "retry")
            elif state and state["state"] in ("missed", "declined"):
                self.fallback(db, row)
            return "call outcome recorded"
        valid = (
            row["state"] == "sent"
            if kind == "call"
            else row["state"] in ("snoozed", "called", "call_failed")
        )
        if not valid or row["attempts"] >= 2:
            return "already handled"
        if not pref["scheduled"] or not self.calls.capabilities()["voice_ready"]:
            self.fallback(db, row)
            return "voice unavailable"
        try:
            with db.transaction():
                cid = ring_reminder(db, self.calls, row["id"], row["summary"], row["context"])
        except HTTPException as exc:
            if exc.status_code not in (409, 503):
                raise
            if kind == "call" and exc.status_code == 503:
                db.execute(
                    "UPDATE app.routine_escalations SET state='call_failed',attempts=1 WHERE id=%s",
                    (row["id"],),
                )
                _follow_up(db, row, "retry", now + timedelta(minutes=5), "transport-retry")
            else:
                self.fallback(db, row)
            return "call unavailable"
        db.execute(
            "UPDATE app.routine_escalations SET call_id=%s,state='called',attempts=attempts+1 WHERE id=%s",
            (cid, row["id"]),
        )
        _follow_up(db, row, "outcome", now + timedelta(seconds=60), f"outcome:{cid}")
        return "call requested"

    @staticmethod
    def prepared(db, block, day, zone):
        from .daily_content import get_brief

        prepared = db.execute(
            "SELECT 1 FROM app.scheduled_jobs WHERE dedupe_key=%s AND "
            "status='done' AND outcome='prepared'",
            (f"block:{block['id']}:{block['task_version']}:{block['version']}:prep",),
        ).fetchone()
        if prepared:
            saved = get_brief(
                db, "pre_task", day, task_id=block["task_id"], starts_at=block["starts_at"]
            )
            if saved:
                return saved["text"], saved["context"]
        when = block["starts_at"].astimezone(ZoneInfo(zone)).strftime("%H:%M")
        due = block["deadline_at"]
        tail = f" Deadline {due.astimezone(ZoneInfo(zone)):%d %b at %H:%M}." if due else ""
        return f"{block['title']} is scheduled at {when}.{tail} Open the task to begin.", ""

    @staticmethod
    def fallback(db, row):
        from .routine_delivery import queue_notice

        db.execute(
            "UPDATE app.routine_escalations SET state='call_failed' WHERE id=%s", (row["id"],)
        )
        queue_notice(db, key=f"fallback:{row['id']}", escalation_id=row["id"], kind="fallback")
