import threading
import uuid

import pytest
from pydantic import ValidationError

from yggdress_app.conductor.log import (
    Bus,
    Op,
    RunLog,
    RunNotFound,
    append_text,
    apply,
    run_uuid,
    set_,
)
from yggdress_app.conductor.state import RunState
from yggdress_app.database import Database


# ---- pure op semantics (shared with the web client) ---------------------------------
def test_set_and_append_text():
    state = {"text": "", "tools": [], "plan": None}
    apply(state, append_text(["text"], "Hel"))
    apply(state, append_text(["text"], "lo"))
    apply(state, set_(["tools", 0], {"id": "t1", "state": "input-streaming"}))
    apply(state, set_(["tools", 0, "state"], "input-available"))
    assert state == {
        "text": "Hello",
        "tools": [{"id": "t1", "state": "input-available"}],
        "plan": None,
    }


def test_append_text_refuses_non_strings():
    with pytest.raises(ValueError):
        apply({"n": 1}, append_text(["n"], "x"))


def test_ops_are_closed():
    with pytest.raises(ValidationError):
        Op(op="delete", path=["text"])
    with pytest.raises(ValidationError):
        Op(op="set", path=[])


def test_run_ids_are_validated():
    assert run_uuid(str(uuid.UUID(int=1)).upper()) == str(uuid.UUID(int=1))
    with pytest.raises(ValueError):
        run_uuid("../etc")


def test_bus_wakes_waiters():
    bus = Bus()
    woke = []
    waiter = threading.Thread(target=lambda: woke.append(bus.wait("r", 0, 2)))
    waiter.start()
    bus.publish("r", 1)
    waiter.join(3)
    assert woke == [True]
    assert bus.wait("r", 1, 0.01) is False  # nothing newer than seq 1


# ---- the durable log, as the application role ----------------------------------------
@pytest.fixture
def log(setup, postgres):
    return RunLog(Database(postgres["runtime"]))


def new_run(log, **fields):
    state = RunState(run_id=str(uuid.uuid4()), **fields)
    log.start(state, "Invented request: plan a picnic for Saturday")
    return state.run_id


def test_append_numbers_events_densely_and_replays(log):
    run = new_run(log)
    assert log.append(run, [append_text(["text"], "Pack "), append_text(["text"], "lunch")]) == 2
    assert log.append(run, [set_(["mode"], "planning")]) == 3
    events = log.events(run)
    assert [seq for seq, _ in events] == [1, 2, 3]
    assert [seq for seq, _ in log.events(run, after=2)] == [3]
    # Replaying the log from an empty state rebuilds the stored snapshot exactly.
    rebuilt = RunState(run_id=run).model_dump(mode="json")
    for _, op in events:
        apply(rebuilt, op)
    snapshot, last = log.snapshot(run)
    assert last == 3 and rebuilt == snapshot.model_dump(mode="json")
    assert snapshot.text == "Pack lunch" and snapshot.mode == "planning"


def test_an_invalid_op_is_rejected_and_nothing_is_written(log):
    run = new_run(log)
    with pytest.raises(ValidationError):
        log.append(run, [append_text(["text"], "ok"), set_(["mode"], "dancing")])
    snapshot, last = log.snapshot(run)
    assert last == 0 and snapshot.text == "" and log.events(run) == []


def test_unknown_run(log):
    with pytest.raises(RunNotFound):
        log.append(str(uuid.uuid4()), [set_(["mode"], "planning")])


def test_concurrent_appends_never_share_a_seq(log):
    run = new_run(log)
    threads = [
        threading.Thread(target=log.append, args=(run, [append_text(["text"], "x")]))
        for _ in range(8)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert [seq for seq, _ in log.events(run)] == list(range(1, 9))
    assert log.snapshot(run)[0].text == "x" * 8


def test_unfinished_runs_are_interrupted_at_startup(log):
    running = new_run(log)
    done = new_run(log)
    log.append(done, [set_(["status"], "completed")])
    assert log.interrupt_unfinished() == [running]
    assert log.snapshot(running)[0].status == "interrupted"
    assert log.snapshot(done)[0].status == "completed"


def test_runs_link_to_a_conversation(log, postgres):
    with Database(postgres["admin"]).connect() as db:
        conversation = db.execute(
            "INSERT INTO app.chat_conversations(title) VALUES ('Invented chat') RETURNING id"
        ).fetchone()["id"]
    run = new_run(log, conversation_id=str(conversation))
    assert log.snapshot(run)[0].conversation_id == str(conversation)
