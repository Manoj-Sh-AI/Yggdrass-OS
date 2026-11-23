"""Milestone 3: plan, run independent steps in parallel, verify each, retry failures with
the judge's reason, skip what depends on a failure, compose one answer. FakeModels only."""

import threading
import time

import pytest

from yggdress_app.conductor.history import ChatHistory
from yggdress_app.conductor.log import RunLog
from yggdress_app.conductor.models import FakeModels, ToolUse
from yggdress_app.conductor.orchestrator import Conductor
from yggdress_app.conductor.planning import PlanDraft, StepDraft, to_plan
from yggdress_app.conductor.state import TERMINAL
from yggdress_app.conductor.tools import StaticToolbox, ToolSpec
from yggdress_app.database import Database

ORCHESTRATE = {"mode": "orchestrate", "reason": "several lookups"}


def draft(*steps):
    return PlanDraft(
        title="Invented picnic plan",
        steps=[
            StepDraft(id=i, title=f"Do {i}", check=f"{i} done", depends_on=d, worker="haiku")
            for i, d in steps
        ],
    )


def task_of(messages) -> str:
    first = messages[0]["content"]
    return first.split("Your task: Do ")[1].split("\n")[0]


def worker_reply(results: dict, barrier: threading.Barrier | None = None):
    def reply(messages):
        if barrier is not None and task_of(messages) in ("s1", "s2"):
            barrier.wait(timeout=5)  # only passes if s1 and s2 run at the same time
        return results[task_of(messages)]

    return reply


@pytest.fixture
def make(setup, postgres):
    database = Database(postgres["runtime"])
    made = []

    def build(models, toolbox=None):
        conductor = Conductor(RunLog(database), models, ChatHistory(database),
                              toolbox=toolbox, owner="test")  # fmt: skip
        made.append(conductor)
        return conductor

    yield build
    for conductor in made:
        for run_id in list(conductor._cancels):
            conductor.cancel(run_id)
        conductor.shutdown()


def finish(conductor, run, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state, _ = conductor.log.snapshot(run.run_id)
        if state.status in TERMINAL:
            return state
        time.sleep(0.05)
    raise AssertionError(f"still {state.status}")


def test_orchestrates_in_parallel_and_composes_from_verified_results(make):
    barrier = threading.Barrier(2)
    results = {"s1": "Saturday 10:00-14:00 is free.", "s2": "Rain 10%.", "s3": "Go at 11:00."}
    reply = worker_reply(results, barrier)
    models = FakeModels({
        "router": [ORCHESTRATE],
        "orchestrator": [draft(("s1", []), ("s2", []), ("s3", ["s1", "s2"])),
                         "Go to the invented picnic at 11:00."],
        "worker": [reply, reply, reply],
    })  # fmt: skip
    conductor = make(models)
    state = finish(conductor, conductor.start("Plan the invented picnic"))
    assert state.status == "completed", state.error
    assert state.mode == "executing" and state.text == "Go to the invented picnic at 11:00."
    steps = {s.id: s for s in state.plan.steps}
    assert all(s.status == "completed" and s.verdict == "passed" for s in steps.values())
    assert steps["s3"].result == "Go at 11:00."
    s3_brief = next(
        c for c in models.calls if c["role"] == "worker" and "Do s3" in c["messages"][0]["content"]
    )
    assert results["s1"] in s3_brief["messages"][0]["content"]  # dependency results flow in
    compose = [c for c in models.calls if c["role"] == "orchestrator"][-1]["messages"][-1][
        "content"
    ]
    assert "[verified]" in compose and results["s2"] in compose
    assert {u.role for u in state.usage} >= {"router", "orchestrator", "worker", "verifier"}


def test_a_failed_check_is_retried_with_the_judges_reason(make):
    models = FakeModels({
        "router": [ORCHESTRATE],
        "orchestrator": [draft(("s1", [])), "Answer."],
        "worker": ["A vague result.", "Saturday 10:00 to 14:00."],
        "verifier": [{"passed": False, "reason": "No times were given."},
                     {"passed": True, "reason": "ok"}],
    })  # fmt: skip
    conductor = make(models)
    state = finish(conductor, conductor.start("Invented request"))
    step = state.plan.steps[0]
    assert step.verdict == "passed" and step.attempts == 2
    retry = [c for c in models.calls if c["role"] == "worker"][1]["messages"][0]["content"]
    assert "did not pass the check: No times were given." in retry


def test_gives_up_after_three_attempts_and_skips_dependents(make):
    fail = {"passed": False, "reason": "Still wrong."}
    models = FakeModels({
        "router": [ORCHESTRATE],
        "orchestrator": [draft(("s1", []), ("s2", ["s1"])), "Could not finish."],
        "worker": ["x", "y", "z"],
        "verifier": [fail, fail, fail],
    })  # fmt: skip
    conductor = make(models)
    state = finish(conductor, conductor.start("Invented request"))
    s1, s2 = state.plan.steps
    assert (s1.status, s1.verdict, s1.attempts) == ("completed", "failed", 3)
    assert s1.reason.startswith("Gave up after 3 attempts")
    assert (s2.status, s2.verdict) == ("completed", "failed") and s2.reason.startswith("Skipped")
    assert len([c for c in models.calls if c["role"] == "worker"]) == 3  # s2 never ran
    compose = [c for c in models.calls if c["role"] == "orchestrator"][-1]["messages"][-1][
        "content"
    ]
    assert "NOT DONE" in compose and "(no verified result)" in compose
    assert "\nz" not in compose and state.status == "completed"  # rejected text left out


def tool_then_text(messages):
    """First turn calls the step's tool; the turn after the tool result answers."""
    s1 = task_of(messages) == "s1"
    if len(messages) == 1:
        return [ToolUse("t-1", "read_calendar", {})] if s1 else [ToolUse("t-2", "broken", {})]
    return "Lunch at noon." if s1 else "Could not read."


def test_workers_call_tools_and_tool_failures_fail_the_check(make):
    tools = StaticToolbox([
        ToolSpec("read_calendar", "Read invented events.", {"type": "object", "properties": {},
                 "additionalProperties": False}, run=lambda _: {"events": ["Invented lunch"]}),
        ToolSpec("broken", "Always fails.", {"type": "object", "properties": {},
                 "additionalProperties": False}, run=lambda _: 1 / 0),
    ])  # fmt: skip
    models = FakeModels({
        "router": [ORCHESTRATE],
        "orchestrator": [draft(("s1", []), ("s2", [])), "Answer."],
        "worker": [tool_then_text] * 10,
    })  # fmt: skip
    conductor = make(models, tools)
    state = finish(conductor, conductor.start("Invented request"))
    calls = {t.name: t for t in state.tools}
    assert calls["read_calendar"].state == "output-available"
    assert calls["read_calendar"].output == {"events": ["Invented lunch"]}
    assert calls["broken"].state == "output-error" and "ZeroDivisionError" in calls["broken"].error
    s2 = next(s for s in state.plan.steps if s.id == "s2")
    assert s2.verdict == "failed" and "A tool failed" in s2.reason


def test_an_unusable_plan_fails_the_run_plainly(make):
    models = FakeModels({"router": [ORCHESTRATE],
                         "orchestrator": [draft(("s1", ["s2"]), ("s2", ["s1"]))]})  # fmt: skip
    conductor = make(models)
    state = finish(conductor, conductor.start("Invented request"))
    assert state.status == "failed" and "plan was not usable" in state.error


def test_plans_are_normalised():
    plan = to_plan(PlanDraft(title="T", steps=[
        StepDraft(id="Step 1!", title="Look up", check="found", depends_on=["ghost"], worker="sonnet"),
        StepDraft(id="Step 1!", title="Compare", check="compared", depends_on=["Step 1!"], worker="haiku"),
    ]))  # fmt: skip
    assert [s.id for s in plan.steps] == ["Step-1", "Step-1-2"]
    assert plan.steps[0].depends_on == []  # unknown dependency dropped
    assert plan.steps[1].depends_on == ["Step-1"]  # resolves to the first "Step 1!"
    assert plan.steps[0].model == "claude-sonnet-5-5" and plan.steps[1].model == "claude-haiku-5-5"


def test_a_step_that_made_a_change_is_never_retried(make):
    created = []
    tools = StaticToolbox([ToolSpec(
        "change_task", "Create an invented task.",
        {"type": "object", "properties": {}, "additionalProperties": False},
        impact="low", reversible=True, classify=lambda _: ("high", True),  # runs + notifies
        run=lambda a: created.append(a) or {"id": "t1"})])  # fmt: skip

    def worker(messages):
        return [ToolUse("u1", "change_task", {})] if len(messages) == 1 else "Done, maybe."

    models = FakeModels({
        "router": [ORCHESTRATE],
        "orchestrator": [draft(("s1", [])), "Answer."],
        "worker": [worker] * 6,
        "verifier": [{"passed": False, "reason": "Unclear."}] * 3,
    })  # fmt: skip
    conductor = make(models, tools)
    state = finish(conductor, conductor.start("Invented request"))
    step = state.plan.steps[0]
    assert len(created) == 1 and step.attempts == 1  # no second task
    assert step.verdict == "failed" and "already made a change" in step.reason
