from uuid import uuid4

from test_agent_specialists import proposal, text, tool
from test_application_agents import fixture
from test_chat import command, conversation


def submit(client, agent, content):
    thread = conversation(client)
    thread = command(
        client, "conversation.route", {"agent_id": agent, "model_id": "default"}, thread
    )["conversation"]
    return command(client, "message.send", {"content": content, "deliver": True}, thread)


def test_direct_lia_uses_existing_read_adapter_and_not_application_model(signed_in):
    client, _, worker, model, _ = fixture(signed_in)
    sent = submit(client, "lia", "What does my saved note say?")
    worker.tick()
    assert model.calls == [] and len(worker.lia.calls) == 1
    assert "read-only" in worker.lia.calls[0][1]
    history = client.get("/v1/chat/conversations/" + sent["conversation"]["id"]).json()
    assert history["messages"][-1]["agent_id"] == "lia"
    assert history["requests"][0]["state"] == "completed"


def test_direct_calendar_preserves_date_only_precision(signed_in):
    item = proposal(
        operation="date_item.create",
        data={
            "title": "Synthetic review",
            "kind": "review",
            "starts_on": "2030-01-02",
            "ends_before": "2030-01-03",
        },
    )
    client, app, worker, _, _ = fixture(
        signed_in, tool("propose_change", item), text("Date-only review proposed")
    )
    submit(client, "calendar", "Create a date-only review on 2 January 2030.")
    worker.tick()
    review = client.get("/v1/application/agents/reviews").json()["reviews"][0]
    assert review["agent_id"] == "calendar" and "start" not in review["payload"]["data"]
    resolved = client.post(
        "/v1/application/agents/reviews/resolve",
        json={
            "key": str(uuid4()),
            "id": review["id"],
            "version": review["version"],
            "decision": "accept",
        },
    )
    assert resolved.status_code == 200, resolved.text
    assert (
        app.state.agent_store.tools.read("calendar", {})["date_item"]["items"][0]["starts_on"]
        == "2030-01-02"
    )
