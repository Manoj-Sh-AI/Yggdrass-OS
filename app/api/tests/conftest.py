import secrets

import pytest
from fastapi.testclient import TestClient
from postgres_fixture import isolated_database

from yggdress_app.application import create_app
from yggdress_app.config import Settings
from yggdress_app.database import Database
from yggdress_app.security import password_hash


@pytest.fixture(autouse=True)
def private_connector_vault(tmp_path, monkeypatch):
    """Tests never read or write the real connector vault or connector file on this laptop."""
    monkeypatch.setenv("YGGDRESS_CONNECTOR_STORE", str(tmp_path / "connector-vault"))
    monkeypatch.setenv("YGGDRESS_CONNECTORS_FILE", str(tmp_path / "connectors.json"))


@pytest.fixture(scope="session")
def postgres():
    with isolated_database() as database:
        yield database


@pytest.fixture
def setup(postgres):
    with Database(postgres["admin"]).connect() as db:
        # Bulk fixture cleanup is not an interactive application request.
        db.execute("SET LOCAL statement_timeout='60s'")
        db.execute(
            "TRUNCATE app.scheduled_jobs,app.routine_important_blocks,app.routine_escalations,"
            "app.journal_entries,app.daily_briefs,app.daily_inputs,app.daily_filing_runs,"
            "app.routine_checkins,app.routine_predictions,app.routine_pool,app.routine_editions,"
            "app.routine_hypotheses CASCADE"
        )
        db.execute(
            "UPDATE app.daily_routine_settings SET enabled=false,wake_time=NULL,midday_time=NULL,"
            "evening_time=NULL,open_channel=false,enabled_since=NULL,version=1 WHERE id=1"
        )
        db.execute("TRUNCATE app.agent_executions,app.agent_effects RESTART IDENTITY CASCADE")
        db.execute(
            "TRUNCATE app.conductor_events,app.conductor_runs,app.conductor_policy RESTART IDENTITY CASCADE"
        )
        db.execute("TRUNCATE app.links RESTART IDENTITY CASCADE")
        db.execute(
            "TRUNCATE app.agent_write_intents,app.agent_proposals,app.agent_steps,app.agent_runs,app.agent_note_events RESTART IDENTITY CASCADE"
        )
        db.execute(
            "TRUNCATE app.note_handoffs,app.workflow_sources,app.workflow_bindings,app.workflow_changes,app.workflow_reviews RESTART IDENTITY CASCADE"
        )
        db.execute(
            "TRUNCATE app.calendar_date_items,app.availability_windows,app.date_item_note_links,app.availability_note_links RESTART IDENTITY CASCADE"
        )
        db.execute(
            "TRUNCATE app.chat_conversations,app.chat_messages,app.chat_requests,app.chat_attachments,app.receiver_receipts RESTART IDENTITY CASCADE"
        )
        db.execute(
            "TRUNCATE app.sessions,app.tasks,app.routine_progress,app.routines,app.planning_goals,app.projects,app.routine_templates,app.task_dependencies,app.routine_exceptions,app.calendar_events,app.execution_blocks,app.execution_sessions,app.task_history,app.daily_plans,app.reminder_requests,app.planning_commands,app.note_refs,app.task_note_links,app.event_note_links,app.event_task_links,app.background_runs,app.workspace_changes RESTART IDENTITY CASCADE"
        )
        db.execute(
            "UPDATE app.login_guard SET failures=0,window_start=now(),locked_until=NULL WHERE id=1"
        )
    password = secrets.token_urlsafe(24)
    settings = Settings(postgres["runtime"], password_hash(password), "http://127.0.0.1", True)
    app = create_app(settings)
    client = TestClient(app, base_url=settings.origin)
    return client, app, password, settings


@pytest.fixture
def signed_in(setup):
    client, app, password, settings = setup
    login = client.post(
        "/v1/auth/login",
        json={"password": password},
        headers={"Origin": settings.origin, "X-Yggdress-Login": "1"},
    )
    assert login.status_code == 200
    client.headers.update({"Origin": settings.origin, "X-Yggdress-CSRF": login.json()["csrf"]})
    return client, app, settings
