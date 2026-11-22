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
from yggdress_app.conductor.state import Plan, RunState, Step, ToolCall
from yggdress_app.database import Database

OWNER = "test-process"


def dump(model):
    return model.model_dump(mode="json")


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


@pytest.mark.parametrize(
    "op",
    [
        set_(["tools", 2], {}),  # past the end (only exactly one past the end appends)
        set_(["tools", -1], {}),  # negative index
        set_(["tools", "0"], {}),  # string index on a list
        append_text(["missing"], "x"),
        append_text(["n"], "x"),  # not a string target
    ],
)
def test_apply_refuses_what_a_js_client_would_do_differently(op):
    with pytest.raises(ValueError):
        apply({"tools": [], "n": 1}, op)


def test_ops_are_closed_and_storable():
    with pytest.raises(ValidationError):
        Op(op="delete", path=["text"])
    with pytest.raises(ValidationError):
        Op(op="set", path=[])
    assert append_text(["text"], "a\x00b").value == "ab"  # jsonb rejects NUL
    with pytest.raises(ValidationError):
        set_(["x"], {"score": float("nan")})


def test_run_ids_are_validated():
    assert run_uuid(str(uuid.UUID(int=1)).upper()) == str(uuid.UUID(int=1))
    with pytest.raises(ValueError):
        run_uuid("../etc")


def test_bus_wakes_waiters_and_forgets_finished_runs():
    bus = Bus()
    woke = []
    waiter = threading.Thread(target=lambda: woke.append(bus.wait("r", 0, 2)))
    waiter.start()
    bus.publish("r", 1)
    waiter.join(3)
    assert woke == [True]
    assert bus.wait("r", 1, 0.01) is False
    bus.close("r")
    assert bus.wait("r", 10, 0.01) is True  # closed: never sleeps
    bus.prune(older_than=0)
    assert "r" not in bus._runs


# ---- the durable log, as the application role ----------------------------------------
@pytest.fixture
def log(setup, postgres):
    return RunLog(Database(postgres["runtime"]))


def new_run(log, **fields):
    state = RunState(run_id=str(uuid.uuid4()), **fields)
    log.start(state, "Invented request: plan a picnic for Saturday", OWNER)
    return state.run_id


def test_append_numbers_events_densely_and_replays(log):
    run = new_run(log)
    assert log.append(run, [append_text(["text"], "Pack "), append_text(["text"], "lunch")]) == 2
    assert log.append(run, [set_(["mode"], "planning")]) == 3
    events = log.events(run)
    assert [seq for seq, _ in events] == [1, 2, 3]
    assert [seq for seq, _ in log.events(run, after=2)] == [3]
    # Replaying the log from the start state rebuilds the stored snapshot exactly.
    rebuilt = dump(RunState(run_id=run))
    for _, op in events:
        apply(rebuilt, op)
    snapshot, last = log.snapshot(run)
    assert last == 3 and rebuilt == dump(snapshot)
    assert snapshot.text == "Pack lunch" and snapshot.mode == "planning"


def test_an_invalid_op_is_rejected_and_nothing_is_written(log):
    run = new_run(log)
    with pytest.raises(ValidationError):
        log.append(run, [append_text(["text"], "ok"), set_(["mode"], "dancing")])
    snapshot, last = log.snapshot(run)
    assert last == 0 and snapshot.text == "" and log.events(run) == []


def test_partial_objects_are_refused_so_clients_never_diverge(log):
    run = new_run(log)
    with pytest.raises(ValueError, match="complete objects"):
        log.append(run, [set_(["tools", 0], {"id": "t1", "name": "read_tasks"})])
    seq = log.append(run, [set_(["tools", 0], dump(ToolCall(id="t1", name="read_tasks")))])
    assert seq == 1


def test_strict_types(log):
    run = new_run(log)
    plan = dump(Plan(title="P", steps=[Step(id="s1", title="Check", check="ok")]))
    log.append(run, [set_(["plan"], plan)])
    with pytest.raises(ValidationError):
        log.append(run, [set_(["plan", "steps", 0, "attempts"], "2")])


def test_moves_are_forward_only_and_finished_runs_are_frozen(log):
    run = new_run(log)
    plan = dump(Plan(title="P", steps=[Step(id="s1", title="Check", check="ok")]))
    log.append(run, [set_(["plan"], plan), set_(["tools", 0], dump(ToolCall(id="t", name="x")))])
    log.append(run, [set_(["plan", "steps", 0, "status"], "in_progress")])
    log.append(run, [set_(["plan", "steps", 0, "status"], "completed")])
    with pytest.raises(ValueError, match="cannot move"):
        log.append(run, [set_(["plan", "steps", 0, "status"], "in_progress")])
    with pytest.raises(ValueError, match="cannot move"):
        log.append(run, [set_(["tools", 0, "state"], "approval-responded")])
    with pytest.raises(ValueError, match="cannot drop"):
        other = dump(Step(id="s2", title="Other", check="ok"))
        log.append(run, [set_(["plan", "steps"], [other])])
    log.append(run, [set_(["status"], "completed")])
    with pytest.raises(ValueError, match="cannot change"):
        log.append(run, [append_text(["text"], "late")])


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


def test_only_stale_running_runs_are_interrupted(log, postgres):
    live = new_run(log)
    stale = new_run(log)
    waiting = new_run(log)
    done = new_run(log)
    log.append(waiting, [set_(["status"], "waiting")])
    log.append(done, [set_(["status"], "completed")])
    with Database(postgres["admin"]).connect() as db:
        db.execute(
            "UPDATE app.conductor_runs SET heartbeat_at=now()-interval '5 minutes' WHERE id<>%s",
            (live,),
        )
    assert sorted(log.interrupt_stale()) == sorted([stale, waiting])
    assert log.snapshot(stale)[0].status == "interrupted"
    assert log.snapshot(live)[0].status == "running"  # another process is still on it
    # A waiting run's worker heartbeats too: stale while waiting means it is orphaned.
    assert log.snapshot(waiting)[0].status == "interrupted"
    assert log.is_stale(waiting) and not log.is_stale(live)
    assert log.snapshot(done)[0].status == "completed"
    log.append(stale, [set_(["status"], "running")], owner=OWNER)  # resume is allowed


def test_runs_link_to_a_conversation(log, postgres):
    with Database(postgres["admin"]).connect() as db:
        conversation = db.execute(
            "INSERT INTO app.chat_conversations(title) VALUES ('Invented chat') RETURNING id"
        ).fetchone()["id"]
    run = new_run(log, conversation_id=str(conversation))
    assert log.snapshot(run)[0].conversation_id == str(conversation)
    assert [s.run_id for s, _ in log.runs_for(str(conversation))] == [run]
