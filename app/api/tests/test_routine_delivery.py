"""Only invented browser subscriptions and a local disposable database."""

import base64
import secrets
from types import SimpleNamespace
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import FastAPI
from fastapi.testclient import TestClient

from yggdress_app.call_service import CallService
from yggdress_app.database import Database
from yggdress_app.routine_delivery import (
    delivery_router,
    drain_notices,
    queue_notice,
    ring_reminder,
)
from yggdress_app.routine_voice import dispatch_metadata
from yggdress_app.security import token_hash


@pytest.fixture
def channel(postgres, monkeypatch):
    database = Database(postgres["runtime"])
    fingerprint, csrf, session_hash = (secrets.token_hex(24) for _ in range(3))
    for name in ("PUBLIC_KEY", "PRIVATE_KEY", "SUBJECT"):
        monkeypatch.setenv("YGGDRAS_VAPID_" + name, "fixture-" + name)
    with database.connect() as db:
        db.execute(
            """INSERT INTO app.sessions(token_hash,csrf,password_fingerprint,expires_at)
                   VALUES (%s,%s,%s,now()+interval '1 hour')""",
            (session_hash, csrf, fingerprint),
        )
    actions = []
    app = FastAPI()
    calls = CallService(database, mode="simulated")
    calls.auth_fingerprint = fingerprint
    app.include_router(
        delivery_router(
            database,
            lambda: {"csrf": csrf},
            fingerprint,
            lambda db, eid, action: actions.append((eid, action)),
            calls=calls,
        )
    )
    client = TestClient(app)
    public = (
        ec.generate_private_key(ec.SECP256R1())
        .public_key()
        .public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    )

    def b64(value):
        return base64.urlsafe_b64encode(value).decode().rstrip("=")

    sub = {
        "endpoint": "https://web.push.apple.com/" + str(uuid4()),
        "keys": {"auth": b64(secrets.token_bytes(16)), "p256dh": b64(public)},
    }
    yield SimpleNamespace(
        database=database,
        client=client,
        actions=actions,
        sub=sub,
        fingerprint=fingerprint,
        calls=calls,
        csrf=csrf,
        session=session_hash,
    )
    with database.connect() as db:
        db.execute("DELETE FROM app.sessions WHERE token_hash=%s", (session_hash,))


BASE = "/v1/routine-delivery"


def send(channel, kind, code=201, key=None):
    eid, payloads = uuid4(), []
    with channel.database.connect() as db:
        queue_notice(db, key=key or str(uuid4()), kind=kind, escalation_id=eid)

    def fake(provider, payload, ttl):
        assert 0 < ttl <= 240
        assert provider == channel.sub
        payloads.append(payload)
        return code

    drain_notices(channel.database, channel.fingerprint, sender=fake)
    return eid, payloads


def test_subscription_bound_to_session_one_use_ack_and_generic_payload(channel):
    c = channel.client
    assert c.post(BASE + "/subscribe", json=channel.sub).status_code == 200
    assert c.get(BASE + "/status").json()["subscribed"]
    eid, (push,) = send(channel, "pre_task", key="one")
    assert set(push) == {"tag", "kind", "token"}
    assert send(channel, "pre_task", key="one")[1] == []
    body = {"token": push["token"], "action": "started"}
    tampered = "A" if body["token"][0] != "A" else "B"
    assert (
        c.post(BASE + "/respond", json={**body, "token": tampered + body["token"][1:]}).status_code
        == 403
    )
    assert c.post(BASE + "/respond", json=body).status_code == 200
    assert c.post(BASE + "/respond", json=body).status_code == 410
    assert channel.actions == [(eid, "started")]
    _, (morning,) = send(channel, "morning")
    assert set(morning) == {"tag", "kind"}
    _, (next_push,) = send(channel, "pre_task")
    with channel.database.connect() as db:
        db.execute("DELETE FROM app.sessions WHERE token_hash=%s", (channel.session,))
    assert c.post(BASE + "/respond", json={**body, "token": next_push["token"]}).status_code == 410


def test_dead_subscription_and_expiry(channel):
    c = channel.client
    for invalid in (
        "https://localhost/admin",
        "http://web.push.apple.com/a",
        "https://fcm.googleapis.com.other.test/a",
    ):
        assert (
            c.post(BASE + "/subscribe", json={**channel.sub, "endpoint": invalid}).status_code
            == 422
        )
    assert c.post(BASE + "/subscribe", json=channel.sub).status_code == 200
    _, (push,) = send(channel, "pre_task")
    with channel.database.connect() as db:
        db.execute(
            "UPDATE app.web_push_deliveries SET expires_at=now() WHERE id=%s", (push["tag"],)
        )
    assert (
        c.post(BASE + "/respond", json={"token": push["token"], "action": "not_yet"}).status_code
        == 410
    )
    send(channel, "morning", code=410)
    assert not c.get(BASE + "/status").json()["subscribed"]


def test_answered_voice_call_scoped_expiring_actions_and_lia(channel, monkeypatch):
    c, service, dbs = channel.client, channel.calls, channel.database
    escalation_id = uuid4()
    with dbs.connect() as db:
        cid = ring_reminder(db, service, escalation_id, "Sample task", "Synthetic context")
        row = db.execute(
            """UPDATE app.calls SET state='answered',answer_session=%s,answered_by='desk',
                         answered_at=now() WHERE id=%s RETURNING *""",
            (token_hash(channel.csrf), cid),
        ).fetchone()
    metadata = dispatch_metadata(dbs, row, channel.fingerprint)
    headers = {"Authorization": "Bearer " + metadata["capability"]}
    path = BASE + "/voice/" + str(cid)
    assert c.get(path).status_code == 403
    assert c.get(BASE + "/voice/" + str(uuid4()), headers=headers).status_code == 410
    assert c.get(path, headers=headers).json()["context"] == "Synthetic context"
    written = []
    monkeypatch.setattr(
        "yggdress_app.routine_jobs.acknowledge_voice", lambda db, e, a, m: written.append((e, a, m))
    )
    action = {"action": "snooze", "minutes": 5, "read_back": True}
    assert (
        c.post(path + "/respond", json={**action, "read_back": False}, headers=headers).status_code
        == 422
    )
    assert (
        c.post(
            path + "/respond", json={**action, "task_id": str(uuid4())}, headers=headers
        ).status_code
        == 422
    )
    for _ in range(2):
        assert c.post(path + "/respond", json=action, headers=headers).status_code == 200
    assert written == [(escalation_id, "snooze", 5)]
    service.briefs = SimpleNamespace(lia=SimpleNamespace(ask=lambda *args, **kw: "From Lia"))
    assert c.post(path + "/lookup", json={"question": "Where?"}, headers=headers).json() == {
        "answer": "From Lia"
    }
    assert c.post(path + "/lookup", json={"question": "Again?"}, headers=headers).status_code == 409
    assert c.post(path + "/end", json={}, headers=headers).json() == {"ended": True}
    assert c.get(path, headers=headers).status_code == 410


def test_reminder_agent_has_only_three_tools():
    pytest.importorskip("livekit.agents")
    from yggdress_app.routine_voice_agent import ReminderAgent

    agent = ReminderAgent({"summary": "A fixture", "context": "Invented"}, None)
    assert {tool.info.name for tool in agent.tools} == {"read_prepared", "mark_response", "ask_lia"}
