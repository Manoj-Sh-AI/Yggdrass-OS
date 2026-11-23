import pytest
from pydantic import ValidationError

from yggdress_app.conductor.state import (
    TOOL_STATES,
    TOOL_TRANSITIONS,
    Plan,
    RunState,
    Step,
    Usage,
    check_step_move,
    check_tool_move,
)


def step(id, depends_on=(), **extra):
    return Step(
        id=id, title=f"Check {id}", check="It exists.", depends_on=list(depends_on), **extra
    )


def test_exactly_the_seven_tool_states():
    assert TOOL_STATES == (
        "input-streaming",
        "input-available",
        "approval-requested",
        "approval-responded",
        "output-available",
        "output-error",
        "output-denied",
    )
    assert set(TOOL_TRANSITIONS) == set(TOOL_STATES)


def test_plan_rejects_duplicates_unknown_self_and_cycles():
    with pytest.raises(ValidationError, match="unique"):
        Plan(title="x", steps=[step("a"), step("a")])
    with pytest.raises(ValidationError, match="unknown"):
        Plan(title="x", steps=[step("a", ["b"])])
    with pytest.raises(ValidationError, match="itself"):
        Plan(title="x", steps=[step("a", ["a"])])
    with pytest.raises(ValidationError, match="cycle"):
        Plan(title="x", steps=[step("a", ["c"]), step("b", ["a"]), step("c", ["b"])])


def test_ready_steps_follow_dependencies_and_verdicts():
    plan = Plan(title="Plan", steps=[step("a"), step("b"), step("c", ["a", "b"])])
    assert [s.id for s in plan.ready()] == ["a", "b"]  # independent steps run together
    plan.steps[0].status, plan.steps[0].verdict = "completed", "passed"
    plan.steps[1].status, plan.steps[1].verdict = "completed", "failed"
    assert plan.ready() == []  # a failed dependency blocks c
    plan.steps[1].verdict = "passed"
    assert [s.id for s in plan.ready()] == ["c"]


def test_transitions_only_move_forward():
    check_step_move("pending", "in_progress")
    check_step_move("in_progress", "pending")  # sent back after a failed check
    with pytest.raises(ValueError):
        check_step_move("completed", "in_progress")
    check_tool_move("input-available", "approval-requested")
    check_tool_move("approval-requested", "output-denied")
    with pytest.raises(ValueError):
        check_tool_move("output-available", "input-available")
    with pytest.raises(ValueError):
        check_tool_move("input-available", "approval-responded")  # must ask first


def test_schema_is_closed_and_bounded():
    with pytest.raises(ValidationError):
        Step(id="Bad Id", title="t", check="c")
    with pytest.raises(ValidationError):
        RunState(run_id="r", surprise=1)
    with pytest.raises(ValidationError):
        Step(id="a", title="t", check="c", attempts=4)


def test_run_cost_sums_usage():
    run = RunState(
        run_id="r",
        usage=[
            Usage(role="router", model="m", input_tokens=1, output_tokens=1, cost_usd=0.0001),
            Usage(role="answer", model="m", input_tokens=1, output_tokens=1, cost_usd=0.0201),
        ],
    )
    assert run.cost_usd() == 0.0202
