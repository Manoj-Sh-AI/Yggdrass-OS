"""The web client mirrors RunState in app/web/src/features/chat/runtime/types.ts. This
test owns a fully populated sample (app/web/tests/fixtures/run-state.json); the web test
checks its TypeScript types against the same file. Regenerate on purpose with
YGGDRAS_WRITE_CONTRACT=1 after changing the schema, then update types.ts."""

import json
import os
from pathlib import Path

from yggdress_app.conductor.state import Approval, Plan, RunState, Step, ToolCall, Usage

FIXTURE = Path(__file__).resolve().parents[2] / "web" / "tests" / "fixtures" / "run-state.json"


def sample() -> dict:
    return RunState(
        run_id="00000000-0000-4000-8000-000000000001",
        conversation_id="00000000-0000-4000-8000-000000000002",
        status="waiting",
        mode="executing",
        plan=Plan(
            title="Invented picnic",
            steps=[
                Step(
                    id="s1",
                    title="Find free Saturday slots",
                    check="slots listed",
                    status="completed",
                    verdict="passed",
                    attempts=1,
                    model="claude-haiku-5-5",
                    result="10:00-14:00",
                ),
                Step(
                    id="s2",
                    title="Create the picnic task",
                    check="task exists",
                    depends_on=["s1"],
                    status="in_progress",
                    attempts=1,
                ),
            ],
        ),
        tools=[
            ToolCall(
                id="0-toolu_1",
                name="change_task",
                state="approval-requested",
                step_id="s2",
                input={"operation": "task.create"},
                stakes="low-irreversible",
                decided_by="user",
                intent="task.create: invented",
                approval=Approval(approved=True, reason=""),
            )
        ],
        reasoning="Thinking about the invented picnic.",
        text="Here is the plan.",
        model="claude-sonnet-5-5",
        usage=[
            Usage(
                role="router",
                model="claude-haiku-5-5",
                input_tokens=10,
                output_tokens=5,
                cost_usd=0.000004,
            )
        ],
        error="",
    ).model_dump(mode="json")


def test_the_web_contract_fixture_matches_the_schema():
    current = sample()
    if os.environ.get("YGGDRAS_WRITE_CONTRACT") == "1" or not FIXTURE.exists():
        FIXTURE.write_text(json.dumps(current, indent=2) + "\n", encoding="utf-8")
    assert json.loads(FIXTURE.read_text(encoding="utf-8")) == current, (
        "RunState changed: regenerate the fixture and update the web types."
    )


def test_health_reports_commit_and_needs_the_database(setup, monkeypatch):
    from fastapi.testclient import TestClient

    from yggdress_app.application import create_app

    _, _, _, settings = setup
    monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", "abc123")
    healthy = TestClient(create_app(settings), base_url=settings.origin).get("/health")
    assert healthy.status_code == 200 and healthy.json()["commit"] == "abc123"
    broken = settings.__class__(
        **{**settings.__dict__, "database_url": "postgresql://x@127.0.0.1:1/none"}
    )
    down = TestClient(create_app(broken), base_url=settings.origin).get("/health")
    assert down.status_code == 503
