"""Exercise the real queue and call lifecycle on an isolated PostgreSQL database."""

from datetime import UTC, date, datetime, time, timedelta
from uuid import uuid4

import pytest
from fastapi import HTTPException

from yggdress_app.call_service import CallService
from yggdress_app.database import Database
from yggdress_app.routine_jobs import (
    RoutineScheduler,
    acknowledge,
    acknowledge_voice,
    anchor_instant,
    claim,
    finish,
    mark,
    put,
    renew,
)

WHEN = datetime(2026, 11, 24, 13, tzinfo=UTC)


@pytest.fixture
def runner(postgres, monkeypatch):
    dbs = Database(postgres["runtime"])
    with Database(postgres["admin"]).connect() as db:
        db.execute(
            "TRUNCATE app.scheduled_jobs,app.tasks,app.calls,app.call_preferences,"
            "app.daily_briefs,app.calendar_events CASCADE"
        )
        db.execute(
            "UPDATE app.daily_routine_settings SET enabled=true,wake_time=NULL,"
            "midday_time=NULL,evening_time=NULL WHERE id=1"
        )
    monkeypatch.setattr("yggdress_app.routine_delivery.drain_notices", lambda *args: 0)
    now = [WHEN]
    calls = CallService(dbs, mode="simulated", now=lambda: now[0])
    return RoutineScheduler(dbs, calls, now=lambda: now[0], anchor_handler=lambda *args: None), now


def add_block(db, when, title="Fixture goal"):
    task, block = uuid4(), uuid4()
    db.execute(
        "INSERT INTO app.tasks(id,title,area,objective) VALUES (%s,%s,'test',%s)",
        (task, title, title),
    )
    db.execute(
        "INSERT INTO app.execution_blocks(id,task_id,starts_at,ends_at,timezone,reason) "
        "VALUES (%s,%s,%s,%s,'Europe/Berlin','Test')",
        (block, task, when, when + timedelta(hours=1)),
    )
    return task, block


def prepare(runner, offset=10):
    scheduler, now = runner
    at = now[0] + timedelta(minutes=offset)
    with scheduler.database.connect() as db:
        task, block = add_block(db, at)
        mark(db, block, True, now[0])
    scheduler.tick()
    now[0] = at
    scheduler.tick()
    with scheduler.database.connect() as db:
        row = db.execute(
            "SELECT * FROM app.routine_escalations WHERE block_id=%s", (block,)
        ).fetchone()
    return task, block, row


def test_prepared_summary_and_early_ack_prevents_call(runner):
    scheduler, now = runner
    _, _, row = prepare(runner)
    assert row and "Fixture goal" in row["summary"]
    with scheduler.database.connect() as db:
        assert db.execute("SELECT 1 FROM app.daily_briefs WHERE kind='pre_task'").fetchone()
        ack = acknowledge(db, row["id"], "started", now[0])
        assert acknowledge(db, row["id"], "started", now[0]) == ack
    now[0] += timedelta(minutes=5)
    scheduler.tick()
    with scheduler.database.connect() as db:
        assert not db.execute("SELECT 1 FROM app.calls").fetchone()
        assert (
            db.execute("SELECT status FROM app.scheduled_jobs WHERE kind='call'").fetchone()[
                "status"
            ]
            == "cancelled"
        )


def test_claimed_call_then_started_cannot_ring(runner):
    scheduler, now = runner
    _, _, row = prepare(runner)
    now[0] += timedelta(minutes=5)
    with scheduler.database.connect() as db:
        job = claim(db, now[0])
        assert job["kind"] == "call"
    with scheduler.database.connect() as db:
        acknowledge(db, row["id"], "started", now[0])
    scheduler.run_job(job)
    with scheduler.database.connect() as db:
        assert not db.execute("SELECT 1 FROM app.calls").fetchone()


def test_not_yet_keeps_call_time_and_voice_snooze_is_bounded(runner):
    scheduler, now = runner
    _, _, row = prepare(runner, offset=1)  # stale prep intentionally exercises the fallback
    assert row["summary"].startswith("Fixture goal is scheduled at ")
    with scheduler.database.connect() as db:
        assert acknowledge(db, row["id"], "not_yet", now[0])["state"] == "sent"
    now[0] += timedelta(minutes=5)
    scheduler.tick()
    scheduler.tick()
    with scheduler.database.connect() as db:
        call = db.execute("SELECT * FROM app.calls").fetchall()
        assert len(call) == 1 and call[0]["simulated"]
        assert (
            db.execute("SELECT summary FROM app.routine_voice_bindings").fetchone()["summary"]
            == row["summary"]
        )
        state = acknowledge_voice(db, row["id"], "snooze", 999, now[0])
        assert state == acknowledge_voice(db, row["id"], "snooze", 999, now[0])
        retry = db.execute("SELECT * FROM app.scheduled_jobs WHERE kind='retry'").fetchall()
        assert len(retry) == 1 and retry[0]["run_at"] == now[0] + timedelta(minutes=30)


def test_missed_twice_sends_final_fallback_without_third_call(runner):
    scheduler, now = runner
    _, _, row = prepare(runner)
    for minutes in (5, 1, 5, 1, 5):
        now[0] += timedelta(minutes=minutes)
        scheduler.tick()
    with scheduler.database.connect() as db:
        assert db.execute("SELECT count(*) n FROM app.calls").fetchone()["n"] == 2
        esc = db.execute(
            "SELECT * FROM app.routine_escalations WHERE id=%s", (row["id"],)
        ).fetchone()
        assert esc["attempts"] == 2 and esc["state"] == "call_failed"


def test_atomic_move_cancel_and_three_task_limit(runner):
    scheduler, now = runner
    with scheduler.database.connect() as db:
        at = now[0] + timedelta(minutes=10)
        blocks = [add_block(db, at) for _ in range(4)]
        for _, block in blocks[:3]:
            mark(db, block, True, now[0])
        with pytest.raises(HTTPException, match="three"):
            mark(db, blocks[3][1], True, now[0])
        block = blocks[0][1]
        db.execute(
            "UPDATE app.execution_blocks SET starts_at=starts_at+interval '5 minutes',"
            "version=version+1 WHERE id=%s",
            (block,),
        )
        jobs = db.execute(
            "SELECT kind,status,run_at FROM app.scheduled_jobs WHERE source_ref=%s",
            ("block:" + str(block),),
        ).fetchall()
        assert sum(j["status"] == "cancelled" for j in jobs) == 2
        assert sum(j["status"] == "pending" for j in jobs) == 2
        new = next(j for j in jobs if j["kind"] == "notify" and j["status"] == "pending")
        assert new["run_at"] == at + timedelta(minutes=5)
        db.execute(
            "UPDATE app.tasks SET done=true,state='completed',version=version+1 WHERE id=%s",
            (blocks[0][0],),
        )
        assert not db.execute(
            "SELECT 1 FROM app.scheduled_jobs WHERE source_ref=%s AND status='pending'",
            ("block:" + str(block),),
        ).fetchone()


def test_clock_change_and_quiet_early_wakeup(runner):
    assert anchor_instant(date(2026, 3, 29), time(2, 30), "Europe/Berlin") == datetime(
        2026, 3, 29, 1, 30, tzinfo=UTC
    )
    assert anchor_instant(date(2026, 10, 25), time(2, 30), "Europe/Berlin") == datetime(
        2026, 10, 25, 0, 30, tzinfo=UTC
    )
    scheduler, now = runner
    now[0] = datetime(2026, 11, 24, 4, 30, tzinfo=UTC)
    delivered = []
    scheduler.anchor_handler = lambda database, lia, kind, *args: delivered.append(kind)
    with scheduler.database.connect() as db:
        db.execute("UPDATE app.daily_routine_settings SET wake_time='05:30' WHERE id=1")
    scheduler.tick()
    assert "morning" not in delivered
    with scheduler.database.connect() as db:
        assert (
            db.execute(
                "SELECT outcome FROM app.scheduled_jobs WHERE kind='morning' AND status='done'"
            ).fetchone()["outcome"]
            == "quiet hours"
        )


def test_expired_lease_with_old_owner_fenced(runner):
    scheduler, now = runner
    with scheduler.database.connect() as db:
        put(db, "fixture", now[0], "lease:test", "fixture", {})
        first = claim(db, now[0])
    now[0] += timedelta(minutes=3)
    with scheduler.database.connect() as db:
        assert renew(db, first, now[0])
        assert claim(db, now[0] + timedelta(minutes=2)) is None
    now[0] += timedelta(minutes=5)
    with scheduler.database.connect() as db:
        second = claim(db, now[0])
        assert second["id"] == first["id"] and second["attempts"] == 2
        assert not renew(db, first, now[0])
        finish(db, first, now[0], "late worker")
        assert (
            db.execute(
                "SELECT status FROM app.scheduled_jobs WHERE id=%s", (first["id"],)
            ).fetchone()["status"]
            == "running"
        )
        finish(db, second, now[0], "completed")
        assert [
            a["outcome"]
            for a in db.execute(
                "SELECT outcome FROM app.scheduled_job_attempts ORDER BY attempt"
            ).fetchall()
        ] == ["lease expired", "completed"]
