"""Agent tool tests never instantiate a real model connection."""

import json
from io import BytesIO
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from yggdress_app.agent_models import AgentError, Claude, ModelReply
from yggdress_app.agent_specialists import Budget, Specialist
from yggdress_app.agent_tools import ApplicationTools, Proposal, allowed


class ScriptedModel:
    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = []

    def complete(self, system, messages, tools):
        self.calls.append((system, list(messages), tools))
        return ModelReply(self.replies.pop(0), 10, 5)


def text(value):
    return [{"type": "text", "text": value}]


def tool(name, values):
    return [{"type": "tool_use", "id": "synthetic-tool", "name": name, "input": values}]


def proposal(**changes):
    return {
        "operation": "task.create",
        "data": {
            "title": "Invented work",
            "objective": "Keep this goal.",
            "due_date": "2030-01-02",
        },
        "explanation": "Requested in the synthetic message.",
        **changes,
    }


def test_specialist_reads_and_proposes_but_does_not_write(signed_in):
    _, app, _ = signed_in
    tools = ApplicationTools(app.state.database)
    model = ScriptedModel(
        tool("read_current", {}),
        tool("propose_change", proposal()),
        text("One task is ready for review."),
    )
    result = Specialist("tasks", model, tools).run("Create the invented task.")
    assert len(result.proposals) == 1
    assert tools.read("tasks", {})["task"]["items"] == []
    assert len(model.calls) == 3


def test_specialist_cannot_cross_domain_or_gain_shell(signed_in):
    _, app, _ = signed_in
    model = ScriptedModel(
        tool("propose_change", proposal()),
        tool("shell", {"command": "anything"}),
        text("I cannot apply this task from Calendar."),
    )
    result = Specialist("calendar", model, ApplicationTools(app.state.database)).run(
        "Synthetic request"
    )
    assert result.proposals == []
    assert all(item["is_error"] for call in model.calls[1:] for item in call[1][-1]["content"])
    with pytest.raises(ValueError):
        allowed("calendar", Proposal.model_validate(proposal()))


def test_budgets_and_cancellation_stop_before_model_calls(signed_in):
    _, app, _ = signed_in
    model = ScriptedModel(text("Should not be called"))
    specialist = Specialist("tasks", model, ApplicationTools(app.state.database))
    with pytest.raises(AgentError, match="limit"):
        specialist.run("Synthetic", budget=Budget(remaining=0))
    with pytest.raises(AgentError, match="cancelled"):
        specialist.run("Synthetic", cancelled=lambda: True)
    assert model.calls == []


def test_version_and_original_goal_are_enforced_before_execution(signed_in):
    _, app, _ = signed_in
    tools = ApplicationTools(app.state.database)
    initial = Proposal.model_validate(proposal())
    with app.state.database.connect() as db:
        created = tools.execute(initial, uuid4(), db)
    bad = Proposal.model_validate(
        proposal(
            operation="task.update",
            id=created["id"],
            version=created["version"],
            data={"title": "Changed", "objective": "Different goal"},
        )
    )
    with pytest.raises(HTTPException) as error:
        tools.inspect(bad)
    assert error.value.status_code == 409
    stale = bad.model_copy(update={"version": created["version"] + 1})
    with pytest.raises(HTTPException) as error:
        tools.inspect(stale)
    assert error.value.status_code == 409
    assert tools.read("tasks", {})["task"]["items"][0]["objective"] == "Keep this goal."


def test_no_timer_tools_and_no_invented_appointment_midnight():
    with pytest.raises(ValidationError):
        Proposal.model_validate(
            proposal(operation="task.execute", id=uuid4(), version=1, data={"action": "start"})
        )
    with pytest.raises(ValidationError, match="timezone"):
        Proposal.model_validate(
            proposal(
                operation="event.create",
                data={
                    "title": "Meeting",
                    "start": "2030-01-02T12:00:00+01:00",
                    "duration_minutes": 30,
                },
            )
        )
    with pytest.raises(ValidationError):
        Proposal.model_validate(
            proposal(
                operation="event.create",
                data={"title": "Meeting", "start": "2030-01-02T12:00:00", "duration_minutes": 30},
            )
        )
    with pytest.raises(ValidationError):
        Proposal.model_validate(
            proposal(
                operation="event.create",
                data={"title": "Meeting", "start": "2030-01-02T12:00:00+01:00"},
            )
        )


def test_calendar_reads_each_kind_and_uses_date_precision(signed_in):
    _, app, _ = signed_in
    tools = ApplicationTools(app.state.database)
    item = Proposal.model_validate(
        proposal(
            operation="date_item.create",
            data={"title": "Date only", "starts_on": "2030-01-02", "ends_before": "2030-01-03"},
        )
    )
    with app.state.database.connect() as db:
        tools.execute(item, uuid4(), db)
    result = tools.read("calendar", {"start": "2030-01-01", "end": "2030-01-04"})
    assert result["date_item"]["items"][0]["starts_on"] == "2030-01-02"
    assert result["availability"]["items"] == []
    assert tools.read("calendar", {"query": "%"})["date_item"]["items"] == []


def test_claude_transport_keeps_key_in_header_and_never_retries():
    class Opener:
        def __init__(self):
            self.calls = []

        def open(self, request, timeout):
            self.calls.append(request)
            assert "private-synthetic-key" not in request.data.decode()
            return BytesIO(
                json.dumps(
                    {
                        "stop_reason": "end_turn",
                        "content": text("Synthetic answer"),
                        "usage": {"input_tokens": 1, "output_tokens": 2},
                    }
                ).encode()
            )

    opener = Opener()
    result = Claude("private-synthetic-key", "synthetic-model", opener=opener).complete(
        "System", [{"role": "user", "content": "Synthetic"}], []
    )
    assert result.output_tokens == 2 and len(opener.calls) == 1

    class Interrupted:
        calls = 0

        def open(self, *_args, **_kwargs):
            self.calls += 1
            raise TimeoutError

    interrupted = Interrupted()
    with pytest.raises(AgentError, match="not retried"):
        Claude("synthetic", "synthetic-model", opener=interrupted).complete("System", [], [])
    assert interrupted.calls == 1


def test_updates_preserve_unmentioned_metadata_dependencies_and_goal(signed_in):
    _, app, _ = signed_in
    tools = ApplicationTools(app.state.database)
    goal = uuid4()
    with app.state.database.connect() as db:
        db.execute(
            "INSERT INTO app.planning_goals(id,title) VALUES (%s,'Existing synthetic goal')",
            (goal,),
        )
        first = tools.execute(Proposal.model_validate(proposal()), uuid4(), db)
        second = tools.execute(
            Proposal.model_validate(
                proposal(
                    data={
                        "title": "Dependent work",
                        "objective": "Keep my goal",
                        "description": "Keep my context",
                        "tags": ["keep"],
                        "goal_id": str(goal),
                        "dependencies": [first["id"]],
                    }
                )
            ),
            uuid4(),
            db,
        )
    edited = Proposal.model_validate(
        proposal(
            operation="task.update",
            id=second["id"],
            version=second["version"],
            data={"title": "Renamed work", "objective": "Keep my goal"},
        )
    )
    with app.state.database.connect() as db:
        tools.execute(edited, uuid4(), db)
    task = next(
        row for row in tools.read("tasks", {})["task"]["items"] if row["id"] == second["id"]
    )
    assert task["description"] == "Keep my context" and task["tags"] == ["keep"]
    assert task["goal_id"] == str(goal) and task["dependencies"] == [first["id"]]


def test_reviewed_task_cancellation_preserves_goal_and_history(signed_in):
    _, app, _ = signed_in
    tools = ApplicationTools(app.state.database)
    with app.state.database.connect() as db:
        created = tools.execute(Proposal.model_validate(proposal()), uuid4(), db)
        cancelled = tools.execute(
            Proposal.model_validate(
                proposal(
                    operation="task.cancel", id=created["id"], version=created["version"], data={}
                )
            ),
            uuid4(),
            db,
        )
        row = db.execute(
            "SELECT objective,state FROM app.tasks WHERE id=%s", (cancelled["id"],)
        ).fetchone()
        assert row["objective"] == "Keep this goal." and row["state"] == "skipped"
        assert (
            db.execute(
                "SELECT count(*) AS n FROM app.task_history WHERE task_id=%s", (created["id"],)
            ).fetchone()["n"]
            >= 2
        )


def test_application_skills_cannot_read_arbitrary_paths_or_other_roles():
    from yggdress_app.agent_skills import index, load

    assert "task-management" in index("tasks")
    assert "fixed goals" in load("tasks", {"name": "task-management"})["instructions"]
    with pytest.raises(ValueError):
        load("tasks", {"name": "../../private"})
    with pytest.raises(ValueError):
        load("calendar", {"name": "task-management"})


def test_missing_agent_setup_does_not_block_the_application(monkeypatch):
    from yggdress_app import agent_worker

    def unavailable(_config):
        raise AgentError("Private connection unavailable")

    monkeypatch.setattr(agent_worker, "private_agent_configuration", unavailable)
    connection, issue = agent_worker.prepare_agent_configuration({"agents": {"enabled": True}})
    assert connection is None and "preserved" in issue
