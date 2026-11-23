"""Call lifecycle and scheduling against invented records; no external calls or speech."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from yggdress_app.call_briefs import LiaForVoice
from yggdress_app.call_service import quiet
from yggdress_app.database import Database


@pytest.fixture
def calls(signed_in, postgres):
    client, app, _settings = signed_in
    with Database(postgres["admin"]).connect() as db:
        db.execute(
            "TRUNCATE app.calls,app.call_commands,app.devices,app.call_schedules,app.voice_worker_lease RESTART IDENTITY CASCADE"
        )
        db.execute(
            "INSERT INTO app.call_preferences(singleton) VALUES (true) ON CONFLICT DO NOTHING"
        )
        db.execute(
            "UPDATE app.call_preferences SET scheduled=true,calendar_starts=true,calendar_ends=true,routines=true,timezone='Europe/Berlin',quiet_start='22:00',quiet_end='08:00',version=1"
        )
    service = app.state.calls
    service.mode = "simulated"
    clock = [datetime(2030, 4, 10, 10, tzinfo=UTC)]
    service.now = lambda: clock[0]
    return client, service, clock


def command(device="phone", **extra):
    return {"key": str(uuid4()), "device": device, **extra}


def test_start_is_retry_safe_and_does_not_claim_media_connected(calls):
    client, service, _ = calls
    payload = command()
    first = client.post("/v1/calls", json=payload)
    assert first.status_code == 200, first.text
    assert first.json()["state"] == "answered" and first.json()["media_state"] == "connecting"
    assert first.json()["simulated"] and not first.json()["token"]
    retry = client.post("/v1/calls", json=payload)
    assert retry.json()["id"] == first.json()["id"]
    with service.database.connect() as db:
        assert db.execute("SELECT count(*) AS n FROM app.calls").fetchone()["n"] == 1
        assert (
            "token"
            not in db.execute("SELECT response FROM app.call_commands").fetchone()["response"]
        )


def test_first_device_wins_and_second_cannot_get_audio(calls):
    client, service, _ = calls
    with service.database.connect() as db:
        ring = service.create(db, direction="outbound")
    path = f"/v1/calls/{ring['id']}/answer"
    payload = command("phone")
    assert client.post(path, json=payload).status_code == 200
    assert client.post(path, json=command("desktop")).status_code == 409
    assert client.post(path, json=payload).status_code == 200


def test_expired_push_cannot_answer_or_replay(calls):
    client, service, clock = calls
    with service.database.connect() as db:
        ring = service.create(db, direction="outbound")
    clock[0] += timedelta(seconds=46)
    assert client.post(f"/v1/calls/{ring['id']}/answer", json=command()).status_code == 409
    data = client.get("/v1/calls").json()
    assert data["calls"][0]["state"] == "missed"
    assert data["events"][-1]["state"] == "missed"


def test_media_updates_require_answering_device_and_current_version(calls):
    client, _, _ = calls
    call = client.post("/v1/calls", json=command()).json()
    path = f"/v1/calls/{call['id']}/media"
    assert (
        client.post(
            path, json=command("other", version=call["version"], state="connected")
        ).status_code
        == 409
    )
    updated = client.post(path, json=command(version=call["version"], state="connected"))
    assert updated.status_code == 200
    assert (
        client.post(path, json=command(version=call["version"], state="ended")).status_code == 409
    )
    ended = client.post(path, json=command(version=updated.json()["version"], state="ended"))
    assert ended.json()["state"] == "ended"


def test_disabled_calls_are_honest_and_never_place_a_call(calls):
    client, service, _ = calls
    service.mode = "disabled"
    assert not client.get("/v1/calls/capabilities").json()["voice_ready"]
    assert client.post("/v1/calls", json=command()).status_code == 503
    with service.database.connect() as db:
        assert db.execute("SELECT count(*) AS n FROM app.calls").fetchone()["n"] == 0


def test_preferences_validate_timezone_and_reject_stale_edits(calls):
    client, _, _ = calls
    pref = client.get("/v1/calls/preferences")
    assert pref.status_code == 200, pref.text
    body = pref.json()
    body.pop("singleton", None)
    assert body["quiet_start"] == "22:00" and body["quiet_end"] == "08:00"
    assert client.put("/v1/calls/preferences", json=body).status_code == 200
    assert client.put("/v1/calls/preferences", json=body).status_code == 409
    body["timezone"] = "not/a-zone"
    assert client.put("/v1/calls/preferences", json=body).status_code == 422


def test_quiet_hours_use_selected_zone_across_daylight_saving(calls):
    _, service, _ = calls
    with service.database.connect() as db:
        pref = db.execute("SELECT * FROM app.call_preferences").fetchone()
    assert quiet(datetime(2030, 4, 10, 20, tzinfo=UTC), pref)  # 22:00 summer
    assert quiet(datetime(2030, 1, 10, 21, tzinfo=UTC), pref)  # 22:00 winter
    assert not quiet(datetime(2030, 4, 10, 6, tzinfo=UTC), pref)  # 08:00


def test_snooze_is_idempotent_and_rejects_quiet_or_naive_time(calls):
    client, _service, clock = calls
    body = {"key": str(uuid4()), "minutes": 5}
    one = client.post("/v1/calls/schedule", json=body)
    assert one.status_code == 200
    assert client.post("/v1/calls/schedule", json=body).json() == one.json()
    assert (
        client.post(
            "/v1/calls/schedule", json={"key": str(uuid4()), "at": "2030-04-10T14:00:00"}
        ).status_code
        == 422
    )
    clock[0] = datetime(2030, 4, 10, 20, tzinfo=UTC)
    assert (
        client.post("/v1/calls/schedule", json={"key": str(uuid4()), "minutes": 5}).status_code
        == 409
    )


def test_calendar_checks_reconcile_changed_source_and_ring_once(calls):
    client, service, clock = calls
    made = client.post(
        "/v1/application/planning/commands",
        json={
            "key": str(uuid4()),
            "op": "event.create",
            "data": {
                "title": "Invented meeting",
                "start": (clock[0] + timedelta(minutes=6)).isoformat(),  # rings 5 min early
                "end": (clock[0] + timedelta(hours=1)).isoformat(),
                "timezone": "Europe/Berlin",
            },
        },
    )
    assert made.status_code == 200, made.text
    service.tick()
    clock[0] += timedelta(minutes=1, seconds=1)
    service.tick()
    service.tick()
    with service.database.connect() as db:
        assert (
            db.execute("SELECT count(*) AS n FROM app.calls WHERE state='ringing'").fetchone()["n"]
            == 1
        )
        assert (
            db.execute(
                "SELECT count(*) AS n FROM app.call_schedules WHERE state='rung'"
            ).fetchone()["n"]
            == 1
        )


def test_notifications_are_revoked_on_logout(calls):
    client, service, _ = calls
    registered = client.post("/v1/calls/devices", json={"push_token": "invented-token-for-device"})
    assert registered.status_code == 200
    assert client.post("/v1/auth/logout").status_code == 200
    with service.database.connect() as db:
        assert db.execute("SELECT revoked_at FROM app.devices").fetchone()["revoked_at"]


def test_voice_knowledge_goes_through_lia_and_may_speak_sensitive_notes():
    class Notes:
        def search(self, owner, q):
            raise AssertionError("voice calls never search notes; Lia is the only door")

        def get(self, owner, slug):
            return {"note": {"sensitive": slug == "secret", "title": slug}}

    class Lia:
        def __init__(self, answer):
            self.answer, self.asked = answer, []

        def ask(self, question, context="", model="default"):
            self.asked.append(question)
            return self.answer

    public = Lia("Invented public fact.[1]\n[1] [[public]] «fact»")
    assert (
        LiaForVoice(public, Notes()).ask(question="A fixture query") == "Invented public fact.[1]"
    )
    assert public.asked == ["A fixture query"]
    secret = LiaForVoice(Lia("SECRET_FIXTURE[1]\n[1] [[secret]] «x»"), Notes())
    assert secret.ask("A fixture query") == "SECRET_FIXTURE[1]"


def test_routine_checkin_does_not_require_opening_the_daily_planner(calls):
    client, service, clock = calls
    made = client.post(
        "/v1/application/planning/commands",
        json={
            "key": str(uuid4()),
            "op": "routine.create",
            "data": {
                "title": "Invented stretch",
                "objective": "Take a pause",
                "starts_on": "2030-04-10",
                "window_start": "12:06",  # rings 5 min early
                "window_end": "12:30",
                "timezone": "Europe/Berlin",
            },
        },
    )
    assert made.status_code == 200, made.text
    service.tick()
    clock[0] += timedelta(minutes=1, seconds=1)
    service.tick()
    with service.database.connect() as db:
        assert (
            db.execute("SELECT count(*) AS n FROM app.calls WHERE state='ringing'").fetchone()["n"]
            == 1
        )
        assert db.execute("SELECT count(*) AS n FROM app.tasks").fetchone()["n"] == 0
        assert (
            db.execute("SELECT source_type FROM app.call_schedules WHERE state='rung'").fetchone()[
                "source_type"
            ]
            == "routine"
        )


def test_cancelled_calendar_item_stops_its_outstanding_ring(calls):
    client, service, clock = calls
    made = client.post(
        "/v1/application/planning/commands",
        json={
            "key": str(uuid4()),
            "op": "event.create",
            "data": {
                "title": "Invented meeting",
                "start": (clock[0] + timedelta(minutes=6)).isoformat(),  # rings 5 min early
                "end": (clock[0] + timedelta(hours=1)).isoformat(),
                "timezone": "Europe/Berlin",
            },
        },
    ).json()
    service.tick()
    clock[0] += timedelta(minutes=1, seconds=1)
    service.tick()
    assert (
        client.post(
            "/v1/application/planning/commands",
            json={
                "key": str(uuid4()),
                "op": "event.remove",
                "id": made["id"],
                "version": made["version"],
                "data": {},
            },
        ).status_code
        == 200
    )
    service.tick()
    assert client.get("/v1/calls").json()["calls"][0]["state"] == "ended"


def test_only_current_devices_receive_generic_expiring_push_payloads(calls):
    client, service, clock = calls
    clock[0] = datetime.now(UTC)
    sent = []

    class Pusher:
        def send(self, device, message):
            sent.append(message)

    service.pusher = Pusher()
    service.mode = "live"
    assert (
        client.post("/v1/calls/devices", json={"push_token": "invented-device-token"}).status_code
        == 200
    )
    with service.database.connect() as db:
        service.create(db, direction="outbound")
    service.deliver()
    service.deliver()
    assert len(sent) == 1
    assert set(sent[0]) == {"callId", "state", "expiresAt"}
    assert sent[0]["state"] == "ringing"
    assert "title" not in sent[0] and "body" not in sent[0]
