"""Milestone 4: safety layers (deny rules -> stakes -> classifier), durable approvals,
and the sensitive-note rule. FakeModels and invented data only."""

import time

import pytest
from fastapi.testclient import TestClient

from yggdress_app.application import create_app
from yggdress_app.conductor.catalog import build_toolbox, restricted_view
from yggdress_app.conductor.history import ChatHistory
from yggdress_app.conductor.log import RunLog
from yggdress_app.conductor.models import FakeModels, ToolUse
from yggdress_app.conductor.orchestrator import Conductor
from yggdress_app.conductor.planning import PlanDraft, StepDraft
from yggdress_app.conductor.policy import Policy, PolicySettings
from yggdress_app.conductor.state import TERMINAL
from yggdress_app.conductor.tools import StaticToolbox, ToolSpec
from yggdress_app.database import Database

EMPTY = {"type": "object", "properties": {}, "additionalProperties": False}


def spec(name="act", impact="low", reversible=True, run=lambda _: {"ok": True}):
    return ToolSpec(name, f"Invented tool {name}.", EMPTY, impact=impact,
                    reversible=reversible, run=run)  # fmt: skip


def policy(models, deny="", auto=""):
    return Policy(models, lambda: PolicySettings(deny_rules=deny, auto_policy=auto))


# ---- the policy layers ---------------------------------------------------------------
@pytest.mark.parametrize(
    ("impact", "reversible", "action", "notify"),
    [
        ("low", True, "run", False),  # auto, passive notice
        ("high", True, "run", True),  # notify + review trail
        ("low", False, "ask", False),  # confirm (no policy written)
        ("high", False, "ask", False),  # explicit approval
    ],
)
def test_the_stakes_matrix(impact, reversible, action, notify):
    decision = policy(FakeModels()).decide(spec(impact=impact, reversible=reversible), {})
    assert (decision.action, decision.notify) == (action, notify)


def test_denied_calls_never_reach_the_classifier():
    models = FakeModels()
    gate = policy(models, deny="change_calendar:*.remove", auto="Allow everything.")
    tool = spec("change_calendar", reversible=False)
    decision = gate.decide(tool, {"operation": "event.remove"})
    assert decision.action == "deny" and decision.decided_by == "rule"
    assert models.calls == []  # the classifier never saw it
    assert gate.decide(spec("send_email"), {}).action == "deny"  # built-in rule


def test_the_classifier_only_judges_low_irreversible_calls():
    models = FakeModels({"verifier": [{"verdict": "allow", "reason": "policy allows tasks"}]})
    gate = policy(models, auto="Creating tasks is fine.")
    allowed = gate.decide(spec("change_task", reversible=False), {"operation": "task.create"})
    assert (allowed.action, allowed.decided_by) == ("run", "classifier")
    high = gate.decide(spec("x", impact="high", reversible=False), {})
    assert high.action == "ask" and len(models.calls) == 1  # never auto-approved, not asked


def test_restricted_notes_never_carry_text():
    assert restricted_view(
        {"slug": "s", "title": "Invented", "sensitive": True, "body": "secret"}
    ) == {
        "slug": "s",
        "title": "Restricted note",
        "sensitivity": "restricted",
    }
    open_note = restricted_view({"slug": "p", "title": "Picnic", "body": "Bring bread."})
    assert open_note["excerpt"] == "Bring bread." and open_note["title"] == "Picnic"


def test_note_search_tool_filters_sensitive_notes(setup, postgres):
    class Notes:
        def search(self, owner, query):
            return {"notes": [{"slug": "a", "title": "Health", "sensitivity": "high",
                               "body": "Invented private detail"},
                              {"slug": "b", "title": "Picnic", "body": "Invented menu"}]}  # fmt: skip

    tool = build_toolbox(Database(postgres["runtime"]), Notes()).get("search_notes")
    result = tool.run({"query": "anything"})
    assert result[0] == {"slug": "a", "title": "Restricted note", "sensitivity": "restricted"}
    assert "Invented private detail" not in str(result)


# ---- approvals inside a run ----------------------------------------------------------
ORCHESTRATE = {"mode": "orchestrate", "reason": "needs a change"}


def one_step_plan():
    return PlanDraft(title="Invented change", steps=[
        StepDraft(id="s1", title="Create the invented task", check="created", depends_on=[],
                  worker="haiku")])  # fmt: skip


def acting_worker(messages):
    if len(messages) == 1:
        return [ToolUse("u1", "change_task", {"operation": "task.create", "explanation": "x"})]
    return "Done."


@pytest.fixture
def run_with_approval(setup, postgres):
    database = Database(postgres["runtime"])
    created = []
    models = FakeModels({"router": [ORCHESTRATE], "orchestrator": [one_step_plan(), "Answer."],
                         "worker": [acting_worker] * 6})  # fmt: skip
    toolbox = StaticToolbox([spec("change_task", reversible=False,
                                  run=lambda a: created.append(a) or {"id": "t1"})])  # fmt: skip
    conductor = Conductor(RunLog(database), models, ChatHistory(database), toolbox=toolbox,
                          policy=policy(models), owner="test")  # fmt: skip
    yield conductor, created
    for run_id in list(conductor._cancels):
        conductor.cancel(run_id)
    conductor.shutdown()


def until(conductor, run_id, check, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state, _ = conductor.log.snapshot(run_id)
        if check(state):
            return state
        time.sleep(0.05)
    raise AssertionError(f"condition not met; status {state.status}")


def test_a_run_waits_for_approval_then_continues(run_with_approval):
    conductor, created = run_with_approval
    run = conductor.start("Invented: add a task")
    waiting = until(conductor, run.run_id, lambda s: s.status == "waiting")
    card = waiting.tools[0]
    assert card.state == "approval-requested" and card.intent.startswith("task.create")
    assert created == []  # nothing ran before the answer
    answer = {"runId": run.run_id, "toolCallId": card.id, "approved": True}
    assert conductor.answer_approval(answer) == run.run_id
    done = until(conductor, run.run_id, lambda s: s.status in TERMINAL)
    assert done.status == "completed" and created == [
        {"operation": "task.create", "explanation": "x"}
    ]
    tool = done.tools[0]
    assert tool.state == "output-available" and tool.approval.approved and tool.decided_by == "user"


def test_a_declined_card_denies_the_call(run_with_approval):
    conductor, created = run_with_approval
    run = conductor.start("Invented: add a task")
    card = until(conductor, run.run_id, lambda s: s.status == "waiting").tools[0]
    conductor.answer_approval({"runId": run.run_id, "toolCallId": card.id, "approved": False,
                               "reason": "Not now."})  # fmt: skip
    done = until(conductor, run.run_id, lambda s: s.status in TERMINAL)
    assert created == [] and done.tools[0].state == "output-denied"
    assert "Not now." in done.tools[0].error and done.plan.steps[0].verdict == "failed"


def test_a_late_or_duplicate_answer_never_interrupts_a_live_run(run_with_approval):
    conductor, _ = run_with_approval
    run = conductor.start("Invented: add a task")
    card = until(conductor, run.run_id, lambda s: s.status == "waiting").tools[0]
    with conductor._lock:  # the card's waiter is gone, but the run is alive here
        conductor._approvals.clear()
    answer = {"runId": run.run_id, "toolCallId": card.id, "approved": True}
    assert conductor.answer_approval(answer) is None
    assert conductor.log.snapshot(run.run_id)[0].status == "waiting"


def test_an_answer_for_a_dead_run_is_recorded_and_interrupts_it(run_with_approval, postgres):
    conductor, _ = run_with_approval
    run = conductor.start("Invented: add a task")
    card = until(conductor, run.run_id, lambda s: s.status == "waiting").tools[0]
    with conductor._lock:  # simulate a restart: this process no longer has the run
        conductor._approvals.clear()
        conductor._cancels.pop(run.run_id)
    with Database(postgres["admin"]).connect() as db:
        db.execute(
            "UPDATE app.conductor_runs SET heartbeat_at=now()-interval '5 minutes' WHERE id=%s",
            (run.run_id,),
        )
    answer = {"runId": run.run_id, "toolCallId": card.id, "approved": True}
    assert conductor.answer_approval(answer) == run.run_id
    state, _ = conductor.log.snapshot(run.run_id)
    assert state.status == "interrupted" and state.tools[0].state == "approval-responded"


def test_untrusted_input_and_check_failures_always_ask():
    models = FakeModels({"verifier": [{"verdict": "allow", "reason": "fine"}]})
    gate = policy(models, auto="Allow everything.")
    tool = spec("change_task", reversible=False)
    asked = gate.decide(tool, {"operation": "task.create"}, untrusted=True)
    assert asked.action == "ask" and models.calls == []  # note text never auto-approved
    big = gate.decide(tool, {"operation": "task.create", "data": {"x": "y" * 7000}})
    assert big.action == "ask" and models.calls == []  # too large: never cut and judged
    assert policy(models, deny="CHANGE_TASK").decide(tool, {}).action == "deny"  # any case


def test_the_intent_preview_uses_the_real_fields():
    from yggdress_app.conductor.orchestrator import intent

    preview = intent(spec("change_calendar"), {"operation": "event.update", "id": "e-1",
                     "data": {"starts_at": "15:00"}, "explanation": "Move dentist"}, "why")  # fmt: skip
    assert preview.startswith('event.update on e-1 with {"starts_at": "15:00"}')
    assert "Model's note: Move dentist" in preview


# ---- HTTP ----------------------------------------------------------------------------
def test_answer_approval_command_streams_the_rest_and_policy_settings(run_with_approval, setup):
    conductor, _ = run_with_approval
    _, _, password, settings = setup
    client = TestClient(create_app(settings, conductor=conductor), base_url=settings.origin)
    login = client.post("/v1/auth/login", json={"password": password},
                        headers={"Origin": settings.origin, "X-Yggdress-Login": "1"})  # fmt: skip
    client.headers.update({"Origin": settings.origin, "X-Yggdress-CSRF": login.json()["csrf"]})
    run = conductor.start("Invented: add a task")
    waiting = until(conductor, run.run_id, lambda s: s.status == "waiting")
    state = client.get(f"/v1/assistant/threads/{run.conversation_id}").json()
    command = {"type": "answer-approval", "runId": run.run_id,
               "toolCallId": waiting.tools[0].id, "approved": True}  # fmt: skip
    response = client.post("/v1/assistant", json={"commands": [command], "state": state})
    assert response.status_code == 200 and "data: [DONE]" in response.text
    assert until(conductor, run.run_id, lambda s: s.status in TERMINAL).status == "completed"
    put = client.put("/v1/assistant/policy",
                     json={"denyRules": "change_calendar:*.remove", "autoPolicy": "Tasks are fine."})  # fmt: skip
    assert put.status_code == 200
    assert client.get("/v1/assistant/policy").json()["denyRules"] == "change_calendar:*.remove"
    assert client.put("/v1/assistant/policy", json={"denyRules": "x" * 5000}).status_code == 422


def test_shutdown_never_waits_out_an_open_approval_card(setup, postgres):
    """Found by the timed full suite (2026-11-22): a run the conductor no longer tracks,
    waiting on a card, kept shutdown() blocked for the 30-minute approval timeout."""
    database = Database(postgres["runtime"])
    models = FakeModels({"router": [ORCHESTRATE], "orchestrator": [one_step_plan(), "Answer."],
                         "worker": [acting_worker] * 6})  # fmt: skip
    toolbox = StaticToolbox([spec("change_task", reversible=False, run=lambda a: {"id": "t1"})])
    conductor = Conductor(RunLog(database), models, ChatHistory(database), toolbox=toolbox,
                          policy=policy(models), owner="test")  # fmt: skip
    run = conductor.start("Invented: add a task")
    until(conductor, run.run_id, lambda s: s.status == "waiting")
    with conductor._lock:
        conductor._cancels.pop(run.run_id)
    started = time.monotonic()
    conductor.shutdown()
    assert time.monotonic() - started < 15
