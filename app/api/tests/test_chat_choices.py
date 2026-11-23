from fastapi.testclient import TestClient
from test_chat import command, conversation, event

from yggdress_app.application import create_app

CATALOG = {
    "agents": [
        {
            "id": "yggdras",
            "name": "Yggdras",
            "enabled": True,
            "models": ["default", "alpha", "beta"],
        },
        {"id": "lia", "name": "Lia", "enabled": False, "models": ["default", "alpha"]},
    ],
    "models": [
        {"id": "default", "name": "Provider default", "enabled": True},
        {"id": "alpha", "name": "Synthetic Alpha", "enabled": True},
        {"id": "beta", "name": "Synthetic Beta", "enabled": True},
    ],
}


def configured(signed_in, connected=True):
    original, _, settings = signed_in
    token = "synthetic-chat-adapter-" + "x" * 40
    app = create_app(
        settings, receiver_tokens={"chat": token} if connected else {}, chat_catalog=CATALOG
    )
    client = TestClient(app, base_url=settings.origin)
    client.cookies.update(original.cookies)
    client.headers.update(original.headers)
    return client, {"Authorization": "Bearer " + token}


def test_agent_model_choices_persist_and_each_request_keeps_its_own_destination(signed_in):
    client, auth = configured(signed_in)
    thread = conversation(client)
    chosen = command(
        client, "conversation.route", {"agent_id": "yggdras", "model_id": "alpha"}, thread
    )["conversation"]
    sent = command(
        client, "message.send", {"content": "First synthetic request", "deliver": True}, chosen
    )
    assert sent["request"]["model_id"] == "alpha" and sent["request"]["state"] == "queued"
    lia = command(
        client, "conversation.route", {"agent_id": "lia", "model_id": "alpha"}, sent["conversation"]
    )["conversation"]
    held = command(client, "message.send", {"content": "Saved for Lia", "deliver": True}, lia)
    assert held["request"]["state"] == "held" and held["message"]["agent_id"] == "lia"
    command(
        client,
        "conversation.route",
        {"agent_id": "yggdras", "model_id": "beta"},
        held["conversation"],
    )["conversation"]
    history = client.get("/v1/chat/conversations/" + thread["id"]).json()
    assert history["conversation"]["model_id"] == "beta"
    first = next(r for r in history["requests"] if r["id"] == sent["request"]["id"])
    assert first["model_id"] == "alpha"
    assert (
        next(r for r in history["requests"] if r["id"] == held["request"]["id"])["state"] == "held"
    )
    resent = command(client, "message.resend", {}, held["message"])["request"]
    assert resent["agent_id"] == "yggdras" and resent["model_id"] == "beta"
    event(client, auth, resent, 0, text="Synthetic answer")
    event(client, auth, resent, 1, kind="complete", text="")
    reply = client.get("/v1/chat/conversations/" + thread["id"]).json()["messages"][-1]
    assert reply["agent_id"] == "yggdras" and reply["model_id"] == "beta"
    command(
        client,
        "conversation.route",
        {"agent_id": "lia", "model_id": "beta"},
        client.get("/v1/chat/conversations/" + thread["id"]).json()["conversation"],
        status=422,
    )


def test_unavailable_choices_save_intent_without_invoking_or_replaying(signed_in):
    client, _ = configured(signed_in, False)
    catalog = client.get("/v1/chat/capabilities").json()["catalog"]
    assert all(not item["available"] for item in catalog["agents"] + catalog["models"])
    thread = conversation(client)
    chosen = command(
        client, "conversation.route", {"agent_id": "lia", "model_id": "alpha"}, thread
    )["conversation"]
    sent = command(
        client, "message.send", {"content": "Keep this draft destination", "deliver": True}, chosen
    )
    assert sent["request"]["state"] == "held" and sent["request"]["agent_id"] == "lia"
    command(client, "message.resend", {}, sent["message"], status=503)
    command(
        client,
        "conversation.route",
        {"agent_id": "unknown-agent", "model_id": "alpha"},
        sent["conversation"],
        status=422,
    )
