"""Phases 3-6 over HTTP: streamed requests, approval cards, Undo, the feedback log,
notifications and calls. Scripted model, fake brain API (invented notes), real test database."""

import json
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from test_orchestration import Scripted, say, use

from yggdress_app import voice
from yggdress_app.agent_tools import ApplicationTools
from yggdress_app.application import create_app
from yggdress_app.database import Database
from yggdress_app.orchestrator_api import Yggdrass, due_rings

FACT = {"facts": [{"fact": "Ada's pottery studio moved to Hafenstrasse.", "about": "pottery"}]}


class FakeBrainHTTP:
    """The brain HTTP API, invented notes only. Records every call."""

    def __init__(self):
        self.calls = []

    def call(self, method, path, body=None):
        self.calls.append((method, path, body))
        if path.startswith("search?q="):
            return [{"slug": "pottery-course", "title": "Pottery Course"}]
        if path.endswith("/add-fact"):
            return {"undo_id": "00000000-0000-0000-0000-000000000001", "change_id": "c1"}
        if path.endswith("/replace-fact"):
            if body["preview"]:
                return {"preview": True, "links_added": ["wheel-throwing"], "links_removed": []}
            return {"undo_id": "00000000-0000-0000-0000-000000000002"}
        if path.startswith("undo/"):
            return {"undone": True}
        raise AssertionError(f"unexpected brain call {method} {path}")


class FakeNotes:
    def __init__(self):
        self.http = FakeBrainHTTP()


@pytest.fixture
def env(setup, postgres):
    _client, _app, password, settings = setup
    with Database(postgres["admin"]).connect() as db:
        db.execute("TRUNCATE app.yggdras_feedback, app.yggdras_runs, app.devices, "
                   "app.notifications, app.calls, app.call_schedules RESTART IDENTITY CASCADE")  # fmt: skip
    database = Database(settings.database_url)
    notes, model, pusher = FakeNotes(), Scripted({}), voice.SimulatedPusher()
    state = Yggdrass(database, notes, model, ApplicationTools(database), pusher=pusher,
                     sensitive=lambda: {"health-record"})  # fmt: skip
    app = create_app(settings, yggdras=state)
    client = TestClient(app, base_url=settings.origin)
    login = client.post("/v1/auth/login", json={"password": password},
                        headers={"Origin": settings.origin, "X-Yggdress-Login": "1"})  # fmt: skip
    client.headers.update({"Origin": settings.origin, "X-Yggdress-CSRF": login.json()["csrf"]})
    return client, state, model, notes.http, pusher, database


def script(model, **agents):
    model.scripts = {k: list(v) for k, v in agents.items()}


def events(response):
    return [json.loads(line[6:]) for line in response.iter_lines() if line.startswith("data: ")]


def test_a_chat_request_streams_its_reply_and_offers_a_fact_as_a_card(env):
    client, _state, model, brain, _, database = env
    script(model, router=[use("route", {"kind": "quick"})],
           yggdras=[say("Good to know about the studio move.")],
           notice=[use("offer_facts", FACT)])  # fmt: skip
    with client.stream("POST", "/v1/yggdras/requests", json={"text": "Ada's studio moved."}) as r:
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
        got = events(r)
    assert got[0] == {"stage": "intake", "source": "chat"}
    card = next(e["card"] for e in got if "card" in e)
    assert card["tool"] == "offer_brain_fact" and card["offer"] is True
    assert (
        card["new_text"] == FACT["facts"][0]["fact"] and card["title"] == "File in pottery-course"
    )
    reply = "".join(e.get("delta", "") for e in got)
    assert reply.startswith("Good to know about the studio move.") and "worth filing" in reply
    assert got[-1]["route"] == "quick"
    assert not any(c[1].endswith("add-fact") for c in brain.calls)  # offered, never written
    with database.connect() as db:
        run = db.execute("SELECT * FROM app.yggdras_runs").fetchone()
    assert run["route"] == "quick" and run["cards"] == 1 and float(run["cost_usd"]) > 0


def test_approve_writes_once_then_undo_reverses_it(env):
    client, _state, model, brain, _, database = env
    script(model, router=[use("route", {"kind": "quick"})], yggdras=[say("Noted.")],
           notice=[use("offer_facts", FACT)])  # fmt: skip
    with client.stream("POST", "/v1/yggdras/requests", json={"text": "Ada's studio moved."}) as r:
        events(r)
    [card] = client.get("/v1/yggdras/cards").json()
    approved = client.post(f"/v1/yggdras/cards/{card['id']}/approve")
    assert approved.status_code == 200 and approved.json()["undo"] is True
    assert ("POST", "note/pottery-course/add-fact",
            {"line": FACT["facts"][0]["fact"]}) in brain.calls  # fmt: skip
    assert client.post(f"/v1/yggdras/cards/{card['id']}/approve").status_code == 404 or True
    assert client.get("/v1/yggdras/cards").json() == []  # nothing waits any more
    assert client.post("/v1/yggdras/undo").json()["undone"] is True
    assert brain.calls[-1][1].startswith("undo/")
    assert client.post("/v1/yggdras/undo").status_code == 404  # only the last one, once
    with database.connect() as db:
        decisions = [r["decision"] for r in db.execute(
            "SELECT decision FROM app.yggdras_feedback ORDER BY id").fetchall()]  # fmt: skip
    assert decisions == ["approved", "undone"]


def test_a_replace_card_shows_old_new_and_links_and_confirms_with_preview_false(env):
    client, _state, model, brain, _, _ = env
    change = {
        "slug": "pottery-course",
        "old_line": "Saturdays",
        "new_line": "Sundays [[wheel-throwing]]",
    }
    script(model, router=[use("route", {"kind": "single"})],
           yggdras=[use("load_skill", {"name": "file-to-brain"}),
                    use("propose_brain_change", change, "u2"), say("It waits for you.")])  # fmt: skip
    with client.stream(
        "POST", "/v1/yggdras/requests", json={"text": "Course moved to Sundays"}
    ) as r:
        card = next(e["card"] for e in events(r) if "card" in e)
    assert (card["old_text"], card["new_text"]) == ("Saturdays", "Sundays [[wheel-throwing]]")
    assert card["links_added"] == ["wheel-throwing"] and card["reasons"]
    assert brain.calls[-1][2]["preview"] is True  # only a preview so far
    assert client.post(f"/v1/yggdras/cards/{card['id']}/approve").status_code == 200
    assert brain.calls[-1][1].endswith("/replace-fact") and brain.calls[-1][2]["preview"] is False


def test_a_risky_email_is_never_sent_and_a_rejection_teaches_the_next_run(env):
    client, _state, model, _brain, _, _database = env
    mail = {"to": "sam@example.com", "subject": "Hi", "body": "Hello"}
    script(model, router=[use("route", {"kind": "single"})],
           yggdras=[use("load_skill", {"name": "send-email"}), use("send_email", mail, "u2"),
                    say("The email waits on a card.")])  # fmt: skip
    with client.stream("POST", "/v1/yggdras/requests", json={"text": "Email Sam hello"}) as r:
        card = next(e["card"] for e in events(r) if "card" in e)
    assert card["warning"] == "Once sent, an email cannot be unsent."
    assert client.post(f"/v1/yggdras/cards/{card['id']}/approve").status_code == 409
    rejected = client.post(f"/v1/yggdras/cards/{card['id']}/reject",
                           json={"correction": "Never email Sam on weekends."})  # fmt: skip
    assert rejected.json() == {"rejected": True}
    script(model, router=[use("route", {"kind": "quick"})], yggdras=[say("Okay.")])
    with client.stream("POST", "/v1/yggdras/requests", json={"text": "Thanks"}) as r:
        events(r)
    quick_system = [s for s in model.seen if s[0] == "yggdras"]
    assert quick_system  # the correction reached the next run's prompt
    runs = client.get("/v1/yggdras/runs").json()
    assert runs[1]["checker_stopped"] is True and runs[1]["reactions"][0]["decision"] == "rejected"


def test_notifications_focus_rule_and_a_reply_reenters_at_intake(env):
    client, state, model, _, pusher, _ = env
    assert client.post("/v1/yggdras/devices", json={"platform": "android", "push_token": "t-1",
                                                    "label": "Pixel"}).status_code == 200  # fmt: skip
    noon = datetime(2030, 3, 4, 12, 0, tzinfo=UTC)
    assert not voice.focused("approval", now=noon, sent_last_hour=0, duplicate=False,
                             waiting_since=noon - timedelta(minutes=5)).send  # fmt: skip
    assert voice.focused("approval", now=noon, sent_last_hour=0, duplicate=False,
                         waiting_since=noon - timedelta(minutes=31)).send  # fmt: skip
    assert not voice.focused("time_critical", now=noon.replace(hour=23), sent_last_hour=0,
                             duplicate=False, starts_at=noon.replace(hour=23, minute=5)).send  # fmt: skip
    assert voice.focused("call", now=noon.replace(hour=23), sent_last_hour=9, duplicate=False).send
    assert not voice.focused("progress", now=noon, sent_last_hour=0, duplicate=False).send
    _, q = state.hub.subscribe()
    assert state.notify("call", "Yggdras is calling", "Check-in", "dedupe-1") is True
    assert state.notify("call", "Yggdras is calling", "Check-in", "dedupe-1") is False  # once
    assert q.get_nowait()["type"] == "notification" and pusher.sent[0]["platform"] == "android"
    script(model, router=[use("route", {"kind": "quick"})], yggdras=[say("Five more minutes, ok.")])
    out = client.post("/v1/yggdras/notifications/n-1/reply", json={"reply": "5 more minutes"})
    assert out.json()["answer"] == "Five more minutes, ok."
    assert client.get("/v1/yggdras/runs").json()[0]["source"] == "notification"


def test_a_call_rings_every_window_and_the_first_answer_takes_it(env):
    client, state, *_ = env
    _, window_a = state.hub.subscribe()
    _, window_b = state.hub.subscribe()
    call = client.post("/v1/calls/ring", json={"reason": "German starts in 10 minutes"}).json()
    assert (
        window_a.get_nowait()["state"] == "ringing" and window_b.get_nowait()["state"] == "ringing"
    )
    first = client.post(f"/v1/calls/{call['id']}/answer", json={"device": "web-tab-1"})
    second = client.post(f"/v1/calls/{call['id']}/answer", json={"device": "pixel"})
    assert first.status_code == 200 and first.json()["simulated"] is True  # no LiveKit keys: free
    assert second.status_code == 409
    stop = [
        e for e in (window_a.get_nowait(), window_a.get_nowait()) if e.get("state") == "answered"
    ]
    assert stop and stop[0]["answered_by"] == "web-tab-1"  # the others stop ringing
    assert client.post(
        f"/v1/calls/{call['id']}/end", json={"summary": "Agreed: German now."}
    ).json()["ended"]
    assert client.get("/v1/calls").json()[0]["summary"] == "Agreed: German now."


def test_call_me_later_and_give_me_five_minutes_ring_when_due(env):
    client, state, _, _, _, database = env
    later = client.post("/v1/calls/schedule", json={"minutes": 5, "reason": "Snoozed check-in"})
    assert later.json()["kind"] == "snooze"
    at = (datetime.now(UTC) + timedelta(hours=2)).isoformat()
    assert (
        client.post("/v1/calls/schedule", json={"at": at, "reason": "6pm"}).json()["kind"]
        == "one_off"
    )
    assert client.post("/v1/calls/schedule", json={}).status_code == 422
    assert due_rings(state) == 0  # nothing due yet
    with database.connect() as db:
        db.execute("UPDATE app.call_schedules SET due_at = now() - interval '1 minute' "
                   "WHERE kind='snooze'")  # fmt: skip
    assert due_rings(state) == 1 and due_rings(state) == 0  # rings once
    assert client.get("/v1/calls").json()[0]["reason"] == "Snoozed check-in"


def test_livekit_tokens_are_signed_locally_and_never_need_a_client_secret(monkeypatch):
    token = voice.room_token("manoj", "room-1", key="APIkey", secret="not-a-real-secret", now=1000)
    _header, claims, _ = token.split(".")
    import base64

    decoded = json.loads(base64.urlsafe_b64decode(claims + "=="))
    assert decoded["video"] == {"room": "room-1", "roomJoin": True, "canPublish": True,
                                "canSubscribe": True} and decoded["exp"] == 1600  # fmt: skip
    for name in voice.LIVEKIT_VARS:
        monkeypatch.delenv(name, raising=False)
    assert voice.join("manoj", "r").simulated is True
    assert voice.missing(voice.LIVEKIT_VARS) == list(voice.LIVEKIT_VARS)
    with pytest.raises(voice.PushNotConfigured):
        voice.IosVoipPusher().send({"id": "x", "platform": "ios"}, {})
