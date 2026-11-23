from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import psycopg
import pytest

from yggdress_app.daily_routine_settings import anchor_times
from yggdress_app.routine_jobs import RoutineScheduler, anchor_instant


def test_custom_wakeup_moves_and_restart_does_not_repeat(signed_in, monkeypatch):
    _client, app, _ = signed_in
    database = app.state.database
    now = datetime(2026, 11, 25, 8, tzinfo=UTC)
    event = uuid4()
    with database.connect() as db:
        app.state.calls.preferences(db)
        db.execute("UPDATE app.daily_routine_settings SET enabled=true")
        db.execute(
            "INSERT INTO app.calendar_events(id,title,starts_at,ends_at,timezone) "
            "VALUES(%s,'Wake up',%s,%s,'Europe/Berlin')",
            (event, now + timedelta(minutes=10), now + timedelta(minutes=20)),
        )
    from yggdress_app.daily_routine_api import run_anchor

    monkeypatch.setattr("yggdress_app.daily_inputs.refresh", lambda *a: None)
    # Real anchor handler, database and worker, with provider delivery captured locally.
    captured = []

    def sender(database, fingerprint, **kwargs):
        with database.connect() as db:
            rows = db.execute(
                "SELECT dedupe_key FROM app.web_push_deliveries WHERE status='pending'"
            ).fetchall()
            captured.extend(r["dedupe_key"] for r in rows)
            db.execute(
                "UPDATE app.web_push_deliveries SET status='accepted' WHERE status='pending'"
            )

    monkeypatch.setattr("yggdress_app.routine_delivery.drain_notices", sender)
    with database.connect() as db:
        session = db.execute("SELECT token_hash FROM app.sessions LIMIT 1").fetchone()
        from psycopg.types.json import Jsonb

        db.execute(
            "INSERT INTO app.web_push_subscriptions(id,endpoint,keys,session_hash) VALUES(%s,%s,%s,%s)",
            (uuid4(), "https://fcm.googleapis.com/fixture", Jsonb({}), session["token_hash"]),
        )
        assert anchor_times(db, now.date(), "Europe/Berlin")["morning"] == "09:10"
    worker = RoutineScheduler(database, app.state.calls, now=lambda: now, anchor_handler=run_anchor)
    worker.tick()
    with database.connect() as db:
        db.execute(
            "UPDATE app.calendar_events SET starts_at=starts_at+interval '10 minutes',"
            "ends_at=ends_at+interval '10 minutes',version=version+1 WHERE id=%s",
            (event,),
        )
    now += timedelta(minutes=10)
    worker = RoutineScheduler(database, app.state.calls, now=lambda: now, anchor_handler=run_anchor)
    worker.tick()
    assert not captured
    now += timedelta(minutes=10)
    worker.tick()
    worker = RoutineScheduler(database, app.state.calls, now=lambda: now, anchor_handler=run_anchor)
    worker.tick()
    assert len(captured) == 1
    assert captured[0].startswith("anchor:morning:")
    with database.connect() as db:
        assert (
            db.execute("SELECT count(*) n FROM app.daily_briefs WHERE kind='morning'").fetchone()[
                "n"
            ]
            == 1
        )
        assert db.execute(
            "SELECT 1 FROM app.scheduled_jobs WHERE kind='morning' AND status='cancelled'"
        ).fetchone()


def test_routines_require_auth_and_preview_has_no_writes(setup):
    client, _app, *_ = setup
    assert (
        client.post("/v1/application/daily-routines/trigger", json={"kind": "morning"}).status_code
        == 401
    )


def test_preview_review_journal_and_prediction(signed_in):
    client, app, _ = signed_in
    root = "/v1/application/daily-routines"
    assert client.post(root + "/trigger", json={"kind": "morning"}).status_code == 200
    with app.state.database.connect() as db:
        assert not db.execute("SELECT 1 FROM app.daily_briefs").fetchone()
    key = str(uuid4())
    body = {
        "key": key,
        "outcome": "partial",
        "worked": "Opened the project",
        "lessons": ["If blocked, open the smallest file."],
    }
    response = client.post(root + "/review", json=body)
    assert response.status_code == 200, response.text
    assert client.post(root + "/review", json=body).status_code == 200
    lesson = response.json()["lessons"][0]
    assert lesson["status"] == "candidate"
    assert (
        client.post(root + "/lessons", json={"id": lesson["id"], "decision": "confirm"}).status_code
        == 200
    )
    with app.state.database.connect() as db:
        assert db.execute("SELECT count(*) n FROM app.journal_entries").fetchone()["n"] == 1
        with pytest.raises(psycopg.Error):
            db.execute("UPDATE app.journal_entries SET text='changed'")
    p = str(uuid4())
    pred = {
        "key": p,
        "domain": "planning",
        "claim": "Finish the draft",
        "probability": 0.7,
        "due_date": "2026-11-25",
    }
    assert client.post(root + "/predictions", json=pred).status_code == 200
    assert client.post(root + "/predictions/" + p, json={"result": True}).status_code == 200
    assert client.get(root + "/predictions").json()["calibration"][0]["brier"] is None


def test_dst_and_rest_day(signed_in):
    from datetime import time

    assert anchor_instant(date(2027, 3, 28), time(2, 30), "Europe/Berlin") == datetime(
        2027, 3, 28, 1, 30, tzinfo=UTC
    )
    assert anchor_instant(date(2027, 10, 31), time(2, 30), "Europe/Berlin") == datetime(
        2027, 10, 31, 0, 30, tzinfo=UTC
    )
    _, app, _ = signed_in
    with app.state.database.connect() as db:
        db.execute("UPDATE app.daily_routine_settings SET wake_time='09:00'")
        assert anchor_times(db, date(2026, 11, 22), "Europe/Berlin") == {"filing": "02:00"}
