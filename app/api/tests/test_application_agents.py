"""End-to-end agent workflow using actual API rules and a synthetic model only."""

from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from notes_fixture import SyntheticBrain
from test_agent_specialists import ScriptedModel, proposal, text, tool
from test_chat import command, conversation

from yggdress_app.agent_api import AgentDecision
from yggdress_app.agent_models import AgentError
from yggdress_app.agent_orchestrator import Yggdras
from yggdress_app.agent_specialists import Budget
from yggdress_app.agent_tools import ApplicationTools
from yggdress_app.agent_worker import AgentWorker
from yggdress_app.application import create_app
from yggdress_app.notes_proxy import NotesProxy

CATALOG = {
    "agents": [
        {"id": name, "name": name, "enabled": True}
        for name in ("yggdras", "lia", "tasks", "calendar")
    ],
    "models": [{"id": "default", "name": "Synthetic model", "enabled": True}],
}


class Lia:
    def __init__(self):
        self.calls = []

    def ask(self, question, context="", model="default"):
        self.calls.append((question, context, model))
        return "The synthetic note says Finish on 2 January."


class Receivers:
    def __init__(self, client, tokens):
        self.client, self.tokens = client, tokens

    def call(self, scope, path, payload=None):
        response = self.client.request(
            "POST" if payload is not None else "GET",
            "/v1/receivers/" + path,
            json=payload,
            headers={"Authorization": "Bearer " + self.tokens[scope]},
        )
        if response.status_code >= 400:
            raise AgentError(response.text)
        return response.json()


def fixture(signed_in, *replies):
    original, _, settings = signed_in
    brain = SyntheticBrain()
    brain.notes["sample"]["body"] = brain.notes["sample"]["body"].replace(
        "## Links", "- Finish on 2 January\n## Links"
    )
    tokens = {
        name: "synthetic-private-" + name + "x" * 40
        for name in ("chat", "note_signals", "workflow_dispatch", "workflow", "background")
    }
    app = create_app(
        settings,
        notes=NotesProxy(brain),
        receiver_tokens=tokens,
        chat_catalog=CATALOG,
        agents_enabled=True,
    )
    client = TestClient(app, base_url=settings.origin)
    client.cookies.update(original.cookies)
    client.headers.update(original.headers)
    model = ScriptedModel(*replies)
    lia = Lia()
    worker = AgentWorker(
        app.state.agent_store,
        Receivers(client, tokens),
        app.state.notes_proxy,
        lia,
        lambda _model: model,
        "synthetic-model",
    )
    return client, app, worker, model, brain


def send(client, agent="tasks", deliver=True):
    thread = conversation(client)
    thread = command(
        client, "conversation.route", {"agent_id": agent, "model_id": "default"}, thread
    )["conversation"]
    return command(
        client, "message.send", {"content": "Create the invented task", "deliver": deliver}, thread
    )


def test_chat_runs_specialist_and_review_executes_once(signed_in):
    client, app, worker, model, _ = fixture(
        signed_in, tool("propose_change", proposal()), text("A proposed task is ready.")
    )
    sent = send(client)
    assert worker.tick()
    history = client.get("/v1/chat/conversations/" + sent["conversation"]["id"]).json()
    assert history["requests"][0]["state"] == "completed"
    assert "proposed" in history["messages"][-1]["content"].lower()
    assert app.state.agent_store.tools.read("tasks", {})["task"]["items"] == []
    review = client.get("/v1/application/agents/reviews").json()["reviews"][0]
    payload = {
        "key": str(uuid4()),
        "id": review["id"],
        "version": review["version"],
        "decision": "accept",
    }
    result = client.post("/v1/application/agents/reviews/resolve", json=payload)
    assert result.status_code == 200, result.text
    assert (
        client.post("/v1/application/agents/reviews/resolve", json=payload).json() == result.json()
    )
    assert len(app.state.agent_store.tools.read("tasks", {})["task"]["items"]) == 1
    assert not worker.tick()
    assert len(model.calls) == 2


def test_held_history_never_replays_and_one_worker_claims(signed_in):
    client, app, worker, model, _ = fixture(signed_in)
    send(client, deliver=False)
    assert not worker.tick()
    assert model.calls == []
    send(client)
    store = app.state.agent_store
    store.enqueue("synthetic-model")
    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(pool.map(lambda _: store.claim(), range(2)))
    assert sum(claim is not None for claim in claims) == 1
    run = next(item for item in claims if item)
    with store.database.connect() as db:
        db.execute(
            "UPDATE app.agent_runs SET lease_until=now()-interval '1 second' WHERE id=%s",
            (run["id"],),
        )
    assert store.claim() is None
    assert model.calls == []
    assert client.get("/v1/application/agents/status").json()["runs"][0]["state"] == "failed"


def test_edited_message_invalidates_approval(signed_in):
    client, app, worker, _, _ = fixture(
        signed_in, tool("propose_change", proposal()), text("Ready for review")
    )
    sent = send(client)
    worker.tick()
    review = client.get("/v1/application/agents/reviews").json()["reviews"][0]
    command(client, "message.edit", {"content": "Do something different"}, sent["message"])
    result = client.post(
        "/v1/application/agents/reviews/resolve",
        json={"key": str(uuid4()), "id": review["id"], "version": 1, "decision": "accept"},
    )
    assert result.status_code == 409
    assert app.state.agent_store.tools.read("tasks", {})["task"]["items"] == []


def test_saved_note_lia_handoff_specialists_shared_records(signed_in):
    interpretation = {
        "commitment_identity": "finish-synthetic",
        "meaning": "deadline",
        "precision": "date",
        "disposition": "clear",
        "entity_type": "task",
        "original_phrase": "Finish on 2 January",
        "data": {
            "title": "Invented deadline",
            "objective": "Finish the synthetic goal",
            "due_date": "2030-01-02",
        },
    }
    client, app, worker, model, brain = fixture(
        signed_in,
        tool("return_interpretations", {"items": [interpretation]}),
        tool("return_interpretations", {"items": []}),
    )
    note = app.state.notes_proxy.get("synthetic-worker", "sample")["note"]
    saved_id = app.state.agent_store.note_saved(note)
    assert app.state.agent_store.note_saved(note) == saved_id
    assert worker.tick()  # Existing Lia reads; no application work yet.
    assert len(worker.lia.calls) == 1
    assert app.state.agent_store.tools.read("tasks", {})["task"]["items"] == []
    assert worker.tick()  # The separate specialist command changes canonical work.
    tasks = app.state.agent_store.tools.read("tasks", {})["task"]["items"]
    assert len(tasks) == 1 and tasks[0]["due_date"] == "2030-01-02"
    assert client.get("/v1/application/workflow/reviews").json()["reviews"] == []
    assert client.get("/v1/application/agents/reviews").json()["reviews"] == []
    assert not worker.tick()
    assert len(model.calls) == 2
    assert all(method == "GET" for method, _, _ in brain.calls)
    assert client.get("/v1/application/connections/notes/sample").status_code == 200


def test_hallucinated_source_quote_cannot_change_records(signed_in):
    item = {
        "commitment_identity": "made-up",
        "meaning": "deadline",
        "precision": "date",
        "disposition": "clear",
        "entity_type": "task",
        "original_phrase": "Not in the synthetic source",
        "data": {"title": "No", "objective": "No", "due_date": "2030-01-02"},
    }
    client, app, worker, _, _ = fixture(
        signed_in, tool("return_interpretations", {"items": [item]})
    )
    app.state.agent_store.note_saved(app.state.notes_proxy.get("worker", "sample")["note"])
    worker.tick()
    worker.tick()
    assert app.state.agent_store.tools.read("tasks", {})["task"]["items"] == []
    assert any(
        "quotation" in row["error"]
        for row in client.get("/v1/application/agents/status").json()["runs"]
    )


def test_yggdras_delegates_isolated_helpers_and_shared_budget(signed_in):
    _, app, _ = signed_in
    model = ScriptedModel(
        tool("tasks", {"request": "Inspect synthetic tasks"}),
        tool("read_current", {}),
        text("No synthetic tasks"),
        text("There are no tasks."),
    )
    result = Yggdras(model, ApplicationTools(app.state.database), Lia()).run(
        "What tasks are here?", budget=Budget(remaining=4)
    )
    assert result.answer == "There are no tasks."
    assert model.calls[1][1][0]["content"] == "Inspect synthetic tasks"
    assert len(model.calls) == 4
    exhausted = ScriptedModel(tool("tasks", {"request": "Inspect tasks"}))
    with pytest.raises(AgentError, match="limit"):
        Yggdras(exhausted, ApplicationTools(app.state.database), Lia()).run(
            "Synthetic", budget=Budget(remaining=1)
        )
    assert len(exhausted.calls) == 1


def test_failed_delivery_reuses_saved_answer_without_another_model_call(signed_in):
    client, _app, worker, model, _ = fixture(signed_in, text("Saved synthetic answer"))
    sent = send(client)
    original = worker.receivers.call
    failed = []

    def interrupted(scope, path, payload=None):
        if path == "chat/events" and not failed:
            failed.append(True)
            raise AgentError("Synthetic lost delivery")
        return original(scope, path, payload)

    worker.receivers.call = interrupted
    worker.tick()
    assert len(model.calls) == 1
    worker.tick()
    assert len(model.calls) == 1
    history = client.get("/v1/chat/conversations/" + sent["conversation"]["id"]).json()
    assert history["requests"][0]["state"] == "completed"
    assert len([m for m in history["messages"] if m["role"] == "assistant"]) == 1


def test_dismissed_proposal_cannot_be_accepted_with_a_new_key(signed_in):
    client, app, worker, _model, _ = fixture(
        signed_in, tool("propose_change", proposal()), text("Proposed")
    )
    send(client)
    worker.tick()
    review = client.get("/v1/application/agents/reviews").json()["reviews"][0]
    decision = AgentDecision(key=uuid4(), id=review["id"], version=1, decision="dismiss")
    assert app.state.agent_store.resolve(decision)["state"] == "dismissed"
    with pytest.raises(HTTPException):
        app.state.agent_store.resolve(
            decision.model_copy(update={"key": uuid4(), "decision": "accept"})
        )


def test_private_endpoints_require_scope_tokens(signed_in):
    client, _, _, _, _ = fixture(signed_in)
    assert client.get("/v1/receivers/chat/pending").status_code == 401
    client.cookies.clear()
    assert client.get("/v1/application/agents/reviews").status_code == 401


def test_prepared_write_recovers_after_restart_without_a_second_brain_write(signed_in):
    _, app, _worker, model, brain = fixture(signed_in)
    store = app.state.agent_store
    intent = store.prepare_write("sample", "1", "save")
    brain.notes["sample"]["version"] = 2
    with store.database.connect() as db:
        db.execute(
            "UPDATE app.agent_write_intents SET created_at=now()-interval '1 minute' WHERE id=%s",
            (intent,),
        )
    restarted = type(store)(store.database)
    restarted.recover_writes(app.state.notes_proxy)
    restarted.recover_writes(app.state.notes_proxy)
    with store.database.connect() as db:
        assert (
            db.execute(
                "SELECT state FROM app.agent_write_intents WHERE id=%s", (intent,)
            ).fetchone()["state"]
            == "completed"
        )
        assert db.execute("SELECT count(*) AS n FROM app.agent_note_events").fetchone()["n"] == 1
    assert model.calls == []
    assert all(method == "GET" for method, _, _ in brain.calls)


def test_rejected_or_still_active_write_is_not_reconciled_as_a_saved_edit(signed_in):
    _, app, _, _, brain = fixture(signed_in)
    store = app.state.agent_store
    active = store.prepare_write("sample", "1", "save")
    rejected = store.prepare_write("sample", "1", "save")
    store.write_failed(rejected, definitive=True)
    brain.notes["sample"]["version"] = 2
    with store.database.connect() as db:
        db.execute("UPDATE app.agent_write_intents SET created_at=now()-interval '1 minute'")
    store.recover_writes(app.state.notes_proxy)
    with store.database.connect() as db:
        assert db.execute("SELECT count(*) AS n FROM app.agent_note_events").fetchone()["n"] == 0
        assert (
            db.execute(
                "SELECT state FROM app.agent_write_intents WHERE id=%s", (active,)
            ).fetchone()["state"]
            == "prepared"
        )


def test_activation_cutoff_does_not_process_preexisting_queued_requests(signed_in):
    client, app, _, model, _ = fixture(signed_in)
    send(client)
    app.state.agent_store.enqueue("synthetic-model", "2099-01-01T00:00:00+00:00")
    assert app.state.agent_store.claim() is None
    assert model.calls == []


def test_cancellation_during_a_model_call_discards_its_proposals(signed_in):
    client, app, worker, model, _ = fixture(signed_in, tool("propose_change", proposal()))
    sent = send(client)
    complete = model.complete

    def cancel_then_return(*args):
        result = complete(*args)
        command(client, "request.cancel", {}, sent["request"])
        return result

    model.complete = cancel_then_return
    worker.tick()
    assert len(model.calls) == 1
    assert client.get("/v1/application/agents/reviews").json()["reviews"] == []
    assert app.state.agent_store.tools.read("tasks", {})["task"]["items"] == []


def test_temporary_helper_is_read_only_and_cannot_delegate_recursively(signed_in):
    _, app, _ = signed_in
    model = ScriptedModel(
        tool("consult_helper", {"request": "Inspect calendar"}),
        tool("propose_change", proposal()),
        tool("consult_helper", {"request": "Spawn another"}),
        text("Read-only consultation"),
        text("No changes made"),
    )
    from yggdress_app.agent_specialists import Specialist

    result = Specialist("tasks", model, ApplicationTools(app.state.database)).run(
        "Inspect related information"
    )
    assert result.proposals == [] and len(model.calls) == 5
    assert {tool["name"] for tool in model.calls[1][2]} == {"read_current", "load_skill"}


def test_saved_note_survives_dispatch_failure_and_returns_an_explicit_warning(signed_in):
    client, app, _, _, brain = fixture(signed_in)
    note = client.get("/v1/notes/items/sample").json()["note"]
    preview = client.post(
        "/v1/notes/items/sample/preview",
        json={
            "fetchToken": note["fetchToken"],
            "body": note["rawBody"].replace("- First (", "- Changed first ("),
        },
    ).json()
    original = app.state.agent_store.note_saved

    def interrupted(*_args):
        raise RuntimeError("Synthetic dispatch outage")

    app.state.agent_store.note_saved = interrupted
    saved = client.post("/v1/notes/previews/" + preview["token"] + "/confirm")
    assert saved.status_code == 200, saved.text
    assert "saved" in saved.json()["reviewWarning"]
    assert "Changed first" in brain.notes["sample"]["body"]
    app.state.agent_store.note_saved = original
    with app.state.database.connect() as db:
        db.execute("UPDATE app.agent_write_intents SET created_at=now()-interval '1 minute'")
    app.state.agent_store.recover_writes(app.state.notes_proxy)
    with app.state.database.connect() as db:
        assert (
            db.execute("SELECT state FROM app.agent_write_intents").fetchone()["state"]
            == "completed"
        )


def test_resend_supersedes_old_unapplied_proposals(signed_in):
    client, app, worker, _, _ = fixture(
        signed_in, tool("propose_change", proposal()), text("Proposed")
    )
    sent = send(client)
    worker.tick()
    old = client.get("/v1/application/agents/reviews").json()["reviews"][0]
    command(client, "message.resend", {}, sent["message"])
    rejected = client.post(
        "/v1/application/agents/reviews/resolve",
        json={
            "key": str(uuid4()),
            "id": old["id"],
            "version": old["version"],
            "decision": "accept",
        },
    )
    assert rejected.status_code == 409
    app.state.agent_store.enqueue("synthetic-model")
    assert client.get("/v1/application/agents/reviews").json()["reviews"] == []
    assert app.state.agent_store.tools.read("tasks", {})["task"]["items"] == []


def test_interactive_chat_and_background_reviews_have_separate_lanes(signed_in):
    client, app, _, model, _ = fixture(signed_in)
    store = app.state.agent_store
    store.note_saved(app.state.notes_proxy.get("worker", "sample")["note"])
    sent = send(client)
    store.enqueue("synthetic-model")
    background = store.claim("background")
    chat = store.claim("chat")
    assert background["note_event_id"] is not None and background["chat_request_id"] is None
    assert str(chat["chat_request_id"]) == sent["request"]["id"]
    assert model.calls == []
    with store.database.connect() as db:
        assert db.execute("SELECT count(*) AS n FROM app.execution_sessions").fetchone()["n"] == 0


def test_undo_revisiting_an_old_revision_is_a_new_observation_not_a_replay(signed_in):
    _, app, _, _, _ = fixture(signed_in)
    store = app.state.agent_store
    original = app.state.notes_proxy.get("worker", "sample")["note"]
    first = store.note_saved(original)
    save = store.prepare_write("sample", original["version"], "save")
    changed = store.note_saved({**original, "version": "newer"}, save)
    undo = store.prepare_write("sample", "newer", "undo")
    reverted = store.note_saved(original, undo)
    assert len({first, changed, reverted}) == 3
    assert store.note_saved(original, undo) == reverted
    with store.database.connect() as db:
        assert db.execute("SELECT count(*) AS n FROM app.agent_note_events").fetchone()["n"] == 3
