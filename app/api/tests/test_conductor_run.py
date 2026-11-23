"""Milestone 2: a run answers by streaming, survives the client leaving, and the
Assistant Transport endpoints stream, resume and rebuild the same state. FakeModels
only: no model spend."""

import json
import threading
import time
import uuid

import pytest
from fastapi.testclient import TestClient

from yggdress_app.application import create_app
from yggdress_app.conductor.history import ChatHistory
from yggdress_app.conductor.log import Op, RunLog, apply
from yggdress_app.conductor.models import FakeModels, ModelError, ReasoningDelta
from yggdress_app.conductor.orchestrator import Conductor
from yggdress_app.conductor.recorder import Recorder
from yggdress_app.conductor.state import TERMINAL, RunState
from yggdress_app.database import Database

ANSWER = "Pack sandwiches, water and a blanket for the invented picnic."


def wait_for(log, run_id, statuses=TERMINAL, timeout=10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state, seq = log.snapshot(run_id)
        if state.status in statuses:
            return state, seq
        time.sleep(0.05)
    raise AssertionError(f"run stayed {state.status}")


class SlowModels(FakeModels):
    """Streams one character at a time until released, to test mid-run behaviour."""

    def __init__(self):
        super().__init__({"orchestrator": [ANSWER]}, chunk=1)
        self.release = threading.Event()

    def stream(self, **kwargs):
        for event in super().stream(**kwargs):
            self.release.wait(5)
            time.sleep(0.02)
            yield event


@pytest.fixture
def database(setup, postgres):
    return Database(postgres["runtime"])


_LIVE: list[Conductor] = []


def make_conductor(database, models):
    conductor = Conductor(RunLog(database), models, ChatHistory(database), owner="test")
    _LIVE.append(conductor)
    return conductor


@pytest.fixture(autouse=True)
def _stop_conductors():
    """No run thread may outlive its test (the next test empties the tables)."""
    yield
    while _LIVE:
        conductor = _LIVE.pop()
        for run_id in list(conductor._cancels):
            conductor.cancel(run_id)
        conductor.shutdown()


# ---- recorder ------------------------------------------------------------------------
def test_recorder_coalesces_deltas_but_keeps_the_text(database):
    log = RunLog(database)
    run = RunState(run_id=str(uuid.uuid4()))
    log.start(run, "Invented request", "test")
    recorder = Recorder(log, run.run_id, "test", flush_seconds=60)
    for piece in ["Pa", "ck ", "lunch"]:
        recorder.text(["text"], piece)
    recorder.set(["mode"], "planning")  # structural change flushes pending text first
    events = log.events(run.run_id)
    assert [op.op for _, op in events] == ["append-text", "set"]
    assert log.snapshot(run.run_id)[0].text == "Pack lunch"


# ---- the run loop --------------------------------------------------------------------
def test_a_run_streams_reasoning_and_answer_and_saves_history(database):
    models = FakeModels({"orchestrator": [[ReasoningDelta("Thinking about food."), ANSWER]]})
    conductor = make_conductor(database, models)
    run = conductor.start("What should I bring to the invented picnic?")
    state, _ = wait_for(conductor.log, run.run_id)
    assert state.status == "completed" and state.text == ANSWER
    assert state.reasoning == "Thinking about food."
    assert state.model == "claude-sonnet-5-5"  # chat default (owner decision)
    assert [u.role for u in state.usage] == ["router", "orchestrator"] and state.cost_usd() > 0
    answered = [c for c in models.calls if c["role"] == "orchestrator"]
    assert answered[0]["messages"][-1]["content"].startswith("What should I bring")
    turns = ChatHistory(database).recent(state.conversation_id)
    assert [t["role"] for t in turns] == ["user", "assistant"] and turns[1]["content"] == ANSWER


def test_follow_ups_carry_the_conversation(database):
    models = FakeModels({"orchestrator": ["First answer.", "Second answer."]})
    conductor = make_conductor(database, models)
    first = conductor.start("Invented question one")
    state, _ = wait_for(conductor.log, first.run_id)
    second = conductor.start("Invented question two", state.conversation_id)
    wait_for(conductor.log, second.run_id)
    sent = [c for c in models.calls if c["role"] == "orchestrator"][1]["messages"]
    assert [m["role"] for m in sent] == ["user", "assistant", "user"]
    assert sent[1]["content"] == "First answer."


def test_a_model_failure_fails_the_run_plainly(database):
    conductor = make_conductor(database, FakeModels({"orchestrator": [ModelError("No key.")]}))
    run = conductor.start("Invented question")
    state, _ = wait_for(conductor.log, run.run_id)
    assert state.status == "failed" and state.error == "No key."
    assert [t["role"] for t in ChatHistory(database).recent(state.conversation_id)] == ["user"]


def test_a_unknown_model_choice_falls_back_to_the_default(database):
    conductor = make_conductor(database, FakeModels())
    run = conductor.start("Invented question", model="gpt-5")
    assert run.model == "claude-sonnet-5-5"


def test_cancel_stops_a_streaming_run(database):
    models = SlowModels()
    conductor = make_conductor(database, models)
    run = conductor.start("Invented long question")
    models.release.set()
    wait_for(conductor.log, run.run_id, statuses={"running"})
    while not conductor.log.snapshot(run.run_id)[0].text:
        time.sleep(0.01)
    assert conductor.cancel(run.run_id)
    state, _ = wait_for(conductor.log, run.run_id)
    assert state.status == "cancelled" and len(state.text) < len(ANSWER)


# ---- HTTP: Assistant Transport -------------------------------------------------------
@pytest.fixture
def http(setup, postgres):
    _, _, password, settings = setup
    database = Database(postgres["runtime"])
    models = SlowModels()
    conductor = make_conductor(database, models)
    client = TestClient(create_app(settings, conductor=conductor), base_url=settings.origin)
    login = client.post(
        "/v1/auth/login",
        json={"password": password},
        headers={"Origin": settings.origin, "X-Yggdress-Login": "1"},
    )
    client.headers.update({"Origin": settings.origin, "X-Yggdress-CSRF": login.json()["csrf"]})
    return client, conductor, models


def client_state(body: str, start: dict) -> dict:
    """Rebuild the browser's state from the SSE frames, as assistant-ui does."""
    state = json.loads(json.dumps(start))
    for line in body.splitlines():
        if not line.startswith("data: ") or line == "data: [DONE]":
            continue
        frame = json.loads(line[6:])
        if frame.get("type") != "update-state":
            continue
        for op in frame["operations"]:
            if not op["path"]:
                state = op["value"]
                continue
            # The wire sends every path element as a string; the client indexes lists.
            path, node = [], state
            for key in op["path"]:
                key = int(key) if isinstance(node, list) else key
                path.append(key)
                node = (
                    node[key]
                    if (isinstance(node, list) and key < len(node))
                    or (isinstance(node, dict) and key in node)
                    else None
                )
            apply(state, Op(op=op["type"], path=path, value=op.get("value")))
    return state


def add_message(text):
    return {
        "type": "add-message",
        "message": {"role": "user", "parts": [{"type": "text", "text": text}]},
    }


def test_post_streams_the_run_and_the_client_state_matches_the_server(http):
    client, _conductor, models = http
    models.release.set()
    response = client.post("/v1/assistant", json={"commands": [add_message("Invented question")]})
    assert response.status_code == 200
    assert response.text.rstrip().endswith("data: [DONE]")
    browser = client_state(response.text, {"conversationId": None, "messages": []})
    assert [m["role"] for m in browser["messages"]] == ["user", "assistant"]
    run = browser["messages"][1]["run"]
    assert run["status"] == "completed" and run["text"] == ANSWER
    server = client.get(f"/v1/assistant/threads/{browser['conversationId']}").json()
    assert server["messages"][1]["run"] == run  # same state, rebuilt two ways


def test_a_second_message_continues_the_same_thread(http):
    client, _conductor, models = http
    models.release.set()
    models.replies["orchestrator"] = [ANSWER, "Second invented answer."]
    first = client.post("/v1/assistant", json={"commands": [add_message("One")]})
    state = client_state(first.text, {"conversationId": None, "messages": []})
    second = client.post("/v1/assistant", json={"commands": [add_message("Two")], "state": state})
    state = client_state(second.text, state)
    assert [m["role"] for m in state["messages"]] == ["user", "assistant"] * 2
    assert state["messages"][3]["run"]["text"] == "Second invented answer."


def test_resume_rebuilds_a_run_still_in_progress(http):
    client, conductor, models = http
    run = conductor.start("Invented long question")  # streams slowly, not released yet
    conversation = run.conversation_id
    models.release.set()
    while not conductor.log.snapshot(run.run_id)[0].text:
        time.sleep(0.01)
    retained = client.post(f"/v1/assistant/resume-state?conversation={conversation}")
    if retained.status_code == 204:  # finished before we asked: nothing to resume
        return
    body = retained.json()
    assert body["runId"].startswith(run.run_id + "@")
    resumed = client.post("/v1/assistant/resume", json={"runId": body["runId"]})
    state = client_state(resumed.text, body["state"])
    final = wait_for(conductor.log, run.run_id)[0]
    index = next(i for i, m in enumerate(state["messages"]) if m["id"] == run.run_id)
    assert state["messages"][index]["run"]["text"] == final.text == ANSWER


def test_resume_state_is_204_when_nothing_runs(http):
    client, conductor, models = http
    models.release.set()
    run = conductor.start("Invented question")
    wait_for(conductor.log, run.run_id)
    assert (
        client.post(f"/v1/assistant/resume-state?conversation={run.conversation_id}").status_code
        == 204
    )


def test_cancel_command_and_auth(http, setup):
    client, conductor, models = http
    run = conductor.start("Invented long question")
    response = client.post(
        "/v1/assistant", json={"commands": [{"type": "cancel-run", "runId": run.run_id}]}
    )
    assert response.status_code == 204
    models.release.set()
    assert wait_for(conductor.log, run.run_id)[0].status == "cancelled"
    anonymous = TestClient(client.app, base_url=str(client.base_url))
    assert anonymous.post("/v1/assistant", json={"commands": []}).status_code == 401
    assert client.post("/v1/assistant", json={"commands": [add_message("")]}).status_code == 422


# ---- review fixes (Milestone 2) --------------------------------------------------------
def test_a_mid_stream_fallback_replaces_the_partial_text(database):
    from yggdress_app.conductor.models import Reset

    models = FakeModels({"orchestrator": [["Refused partial", Reset(), ANSWER]]})
    conductor = make_conductor(database, models)
    state, _ = wait_for(conductor.log, conductor.start("Invented question").run_id)
    assert state.text == ANSWER
    assert ChatHistory(database).recent(state.conversation_id)[-1]["content"] == ANSWER


def test_back_to_back_user_turns_are_merged():
    from yggdress_app.conductor.orchestrator import with_request

    merged = with_request([{"role": "user", "content": "First (no answer)"}], "Second")
    assert merged == [{"role": "user", "content": "First (no answer)\n\nSecond"}]


def test_bus_never_sleeps_after_a_run_closed():
    from yggdress_app.conductor.log import Bus

    bus = Bus()
    bus.close("r")
    assert bus.wait("r", 10_000, 0.01) is True  # a late waiter returns at once


def test_phone_messages_after_a_run_stay_in_the_thread(http, postgres):
    client, conductor, models = http
    models.release.set()
    run = conductor.start("Invented question from the laptop")
    wait_for(conductor.log, run.run_id)
    with Database(postgres["admin"]).connect() as db:  # the phone writes the old way
        db.execute(
            "INSERT INTO app.chat_messages(conversation_id,role,content) VALUES (%s,'user',%s)",
            (run.conversation_id, "Invented question from the phone"),
        )
    thread = client.get(f"/v1/assistant/threads/{run.conversation_id}").json()
    assert [m["text"] for m in thread["messages"] if m["role"] == "user"] == [
        "Invented question from the laptop",
        "Invented question from the phone",
    ]


def test_bad_ids_are_refused_cleanly(http):
    client, _, _ = http
    bad = {"commands": [{"type": "cancel-run", "runId": "nope"}]}
    assert client.post("/v1/assistant", json=bad).status_code == 422
    body = {"commands": [add_message("Hi")], "conversationId": "not-a-uuid"}
    assert client.post("/v1/assistant", json=body).status_code == 422
    assert client.post("/v1/assistant/resume", json={"runId": "x@1"}).status_code == 404
    unknown = {"runId": f"{uuid.uuid4()}@3"}
    assert client.post("/v1/assistant/resume", json=unknown).status_code == 404
    assert client.get("/v1/assistant/threads/abc").status_code == 404


def test_images_reach_the_model_and_bad_images_are_refused(http):
    client, _conductor, models = http
    models.release.set()
    pixel = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
    message = {"type": "add-message", "message": {"role": "user", "parts": [
        {"type": "image", "image": f"data:image/png;base64,{pixel}"},
        {"type": "text", "text": "What is in this invented picture?"}]}}  # fmt: skip
    response = client.post("/v1/assistant", json={"commands": [message]})
    assert response.status_code == 200
    sent = [c for c in models.calls if c["role"] == "orchestrator"][-1]["messages"][-1]["content"]
    assert sent[0]["type"] == "image" and sent[0]["source"]["media_type"] == "image/png"
    assert sent[-1] == {"type": "text", "text": "What is in this invented picture?"}
    bad = {"type": "add-message", "message": {"role": "user", "parts": [
        {"type": "image", "image": "data:application/pdf;base64,AAAA"}]}}  # fmt: skip
    assert client.post("/v1/assistant", json={"commands": [bad]}).status_code == 422


# ---- branching ("Try again", `< 2/3 >`) -----------------------------------------------
def test_try_again_answers_the_same_request_without_the_first_answer(database):
    models = FakeModels({"orchestrator": ["Earlier answer.", "First try.", "Second try."]})
    conductor = make_conductor(database, models)
    earlier = conductor.start("Invented earlier question")
    convo = wait_for(conductor.log, earlier.run_id)[0].conversation_id
    first = conductor.start("Invented question to retry", convo)
    wait_for(conductor.log, first.run_id)
    again = conductor.branch(first.run_id)
    state = wait_for(conductor.log, again.run_id)[0]
    assert state.branch_of == first.run_id and state.text == "Second try."
    sent = [c for c in models.calls if c["role"] == "orchestrator"][-1]["messages"]
    assert [m["role"] for m in sent] == ["user", "assistant", "user"]
    assert sent[1]["content"] == "Earlier answer." and "First try." not in json.dumps(sent)
    # one copy of the request in the chat; the next turn sees only the latest answer
    turns = ChatHistory(database).recent(convo)
    assert [t["content"] for t in turns][-2:] == ["Invented question to retry", "Second try."]


def test_a_branch_of_a_branch_joins_the_same_group(database):
    conductor = make_conductor(database, FakeModels({"orchestrator": ["A.", "B.", "C."]}))
    first = conductor.start("Invented question")
    wait_for(conductor.log, first.run_id)
    second = conductor.branch(first.run_id)
    wait_for(conductor.log, second.run_id)
    third = conductor.branch(second.run_id)
    assert wait_for(conductor.log, third.run_id)[0].branch_of == first.run_id


def test_try_again_is_refused_while_an_answer_is_running(database):
    models = SlowModels()
    conductor = make_conductor(database, models)
    run = conductor.start("Invented slow question")
    with pytest.raises(ValueError, match="still running"):
        conductor.branch(run.run_id)
    models.release.set()
    wait_for(conductor.log, run.run_id)


def test_regenerate_streams_into_branches_and_the_thread_rebuilds_them(http):
    client, _conductor, models = http
    models.release.set()
    models.replies["orchestrator"] = [ANSWER, "Another invented answer."]
    first = client.post("/v1/assistant", json={"commands": [add_message("Invented question")]})
    state = client_state(first.text, {"conversationId": None, "messages": []})
    root = state["messages"][1]["id"]
    again = client.post("/v1/assistant",
                        json={"commands": [{"type": "regenerate", "runId": root}], "state": state})  # fmt: skip
    assert again.status_code == 200
    state = client_state(again.text, state)
    assert [m["role"] for m in state["messages"]] == ["user", "assistant"]
    branches = state["messages"][1]["branches"]
    assert [b["run"]["text"] for b in branches] == [ANSWER, "Another invented answer."]
    server = client.get(f"/v1/assistant/threads/{state['conversationId']}").json()
    assert [b["run"] for b in server["messages"][1]["branches"]] == [b["run"] for b in branches]


def test_regenerate_of_an_unknown_run_is_404(http):
    client, _conductor, _models = http
    response = client.post("/v1/assistant",
                           json={"commands": [{"type": "regenerate", "runId": str(uuid.uuid4())}]})  # fmt: skip
    assert response.status_code == 404
