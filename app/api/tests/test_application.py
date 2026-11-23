import secrets
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient

from yggdress_app.application import COOKIE, create_app
from yggdress_app.brain import SHELVES, UnavailableBrain
from yggdress_app.database import Database
from yggdress_app.security import password_hash, token_hash, valid_hash, verify_password


def test_fail_closed_configuration(setup):
    _, _, _, config = setup
    for change in (
        {"password_hash": ""},
        {"database_url": ""},
        {"origin": "http://public.example"},
        {"origin": "https://public.example", "local_http": True},
        {"brain_mode": "real"},
        {"origin": config.origin + "/path"},
    ):
        with pytest.raises(ValueError):
            create_app(replace(config, **change))


def test_password_hash_has_random_salt():
    value = secrets.token_urlsafe(24)
    first, second = password_hash(value), password_hash(value)
    assert first != second and value not in first
    assert valid_hash(first) and verify_password(value, first)
    assert not verify_password(value + "x", first)
    assert not valid_hash("not-a-hash")


@pytest.mark.parametrize(
    "path",
    [
        "auth/session",
        "application/tasks",
        "application/routine",
        "brain/tree",
        "brain/notes",
        "brain/notes/credit-report",
    ],
)
def test_private_reads_require_auth(setup, path):
    client, _, _, _ = setup
    response = client.get("/v1/" + path)
    assert response.status_code == 401
    assert response.headers["cache-control"] == "no-store"
    assert "Credit Risk" not in response.text


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("POST", "application/tasks", {"title": "Synthetic", "area": "work", "date": "2026-11-08"}),
        ("POST", "application/routine/actions", {"type": "start"}),
        ("POST", "brain/notes", {"title": "Synthetic", "shelfId": "14-inbox"}),
        (
            "PUT",
            "brain/notes/credit-report",
            {"version": "fake", "title": "Synthetic", "content": "fiction"},
        ),
        ("POST", "brain/notes/credit-report/delete-preview", {"version": "fake"}),
        (
            "POST",
            "brain/notes/credit-report/delete-confirm",
            {"version": "fake", "token": "fake", "confirmed": True},
        ),
    ],
)
def test_private_mutations_require_auth(setup, method, path, body):
    assert setup[0].request(method, "/v1/" + path, json=body).status_code == 401


def test_login_origin_rate_limit_and_safe_errors(setup):
    client, _, password, config = setup
    assert client.post("/v1/auth/login", json={"password": password}).status_code == 403
    headers = {"Origin": config.origin, "X-Yggdress-Login": "1"}
    invalid = client.post(
        "/v1/auth/login", json={"password": password, "extra": password}, headers=headers
    )
    assert invalid.status_code == 422 and password not in invalid.text
    for _ in range(5):
        assert (
            client.post(
                "/v1/auth/login", json={"password": password + "wrong"}, headers=headers
            ).status_code
            == 401
        )
    assert (
        client.post("/v1/auth/login", json={"password": password}, headers=headers).status_code
        == 429
    )


def test_csrf_expiry_rotation_and_logout(signed_in):
    client, _, settings = signed_in
    body = {"type": "start"}
    assert (
        client.post(
            "/v1/application/routine/actions", json=body, headers={"X-Yggdress-CSRF": "wrong"}
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/v1/application/routine/actions",
            json=body,
            headers={"Origin": "https://other.example"},
        ).status_code
        == 403
    )
    cookie = client.cookies.get(COOKIE)
    with Database(settings.database_url).connect() as db:
        row = db.execute("SELECT token_hash FROM app.sessions").fetchone()
        assert row["token_hash"] == token_hash(cookie) and row["token_hash"] != cookie
    rotated = TestClient(
        create_app(replace(settings, password_hash=password_hash(secrets.token_urlsafe(24)))),
        base_url=settings.origin,
    )
    rotated.cookies.update(client.cookies)
    assert rotated.get("/v1/auth/session").status_code == 401
    assert client.post("/v1/auth/logout").status_code == 200
    assert client.get("/v1/auth/session").status_code == 401


def test_secure_cookie_and_session_expiry(setup, postgres):
    _, _, password, config = setup
    settings = replace(config, origin="https://private.example", local_http=False)
    client = TestClient(create_app(settings), base_url=settings.origin)
    response = client.post(
        "/v1/auth/login",
        json={"password": password},
        headers={"Origin": settings.origin, "X-Yggdress-Login": "1"},
    )
    cookie = response.headers["set-cookie"]
    assert all(word in cookie.lower() for word in ("secure", "httponly", "samesite=strict"))
    with Database(postgres["admin"]).connect() as db:
        db.execute("UPDATE app.sessions SET expires_at=now()-interval '1 second'")
    assert client.get("/v1/auth/session").status_code == 401


def test_routine_and_tasks_survive_service_restart_without_changing_goal(signed_in):
    client, _, settings = signed_in
    original = client.get("/v1/application/routine").json()
    assert original["definition"]["description"]
    assert (
        client.post(
            "/v1/application/routine/actions", json={"type": "progress", "percent": 25}
        ).status_code
        == 409
    )
    for command in ({"type": "start"}, {"type": "progress", "percent": 45}):
        assert client.post("/v1/application/routine/actions", json=command).status_code == 200
    task = client.post(
        "/v1/application/tasks",
        json={
            "title": "Synthetic task",
            "description": "Application record only",
            "area": "work",
            "date": "2026-11-08",
        },
    ).json()["task"]
    assert (
        client.patch(f"/v1/application/tasks/{task['id']}", json={"done": True}).status_code == 200
    )
    restarted = TestClient(create_app(settings), base_url=settings.origin)
    restarted.cookies.update(client.cookies)
    restarted.headers.update(client.headers)
    read = restarted.get("/v1/application/routine").json()
    assert read["definition"] == original["definition"]
    assert read["execution"]["progress"] == 45 and read["execution"]["startedAt"]
    assert restarted.get("/v1/application/tasks").json()["tasks"][0]["done"]
    reported = restarted.post(
        "/v1/application/routine/actions", json={"type": "progress", "percent": 100}
    ).json()
    assert reported["execution"]["status"] == "in_progress"
    assert reported["execution"]["completedAt"] is None
    assert reported["definition"] == original["definition"]
    finished = restarted.post("/v1/application/routine/actions", json={"type": "complete"}).json()
    assert finished["definition"] == original["definition"]
    assert finished["execution"]["status"] == "completed"
    assert finished["execution"]["progress"] == 100 and finished["execution"]["completedAt"]
    assert [p["percent"] for p in finished["execution"]["progressHistory"]] == [45, 100]
    assert (
        restarted.post(
            "/v1/application/routine/actions", json={"type": "progress", "percent": 10}
        ).status_code
        == 409
    )
    assert (
        restarted.post(
            "/v1/application/routine/actions", json={"type": "start", "goal": "reduced"}
        ).status_code
        == 422
    )


@pytest.mark.parametrize("percent", [-1, 101, 4.5, True, "50"])
def test_invalid_routine_progress_is_rejected(signed_in, percent):
    assert (
        signed_in[0]
        .post("/v1/application/routine/actions", json={"type": "progress", "percent": percent})
        .status_code
        == 422
    )


def test_mock_tree_create_replace_stale_and_permanent_delete(signed_in):
    client, app, _ = signed_in
    tree = client.get("/v1/brain/tree").json()
    assert tree["mode"] == "mock" and tree["integrationBlocked"] is True
    assert [s["id"] for s in tree["shelves"]] == list(SHELVES)
    note = client.post(
        "/v1/brain/notes",
        json={"title": "Synthetic river", "content": "Invented first text", "shelfId": "14-inbox"},
    ).json()["note"]
    path = f"/v1/brain/notes/{note['id']}"
    assert client.get(path).json()["note"]["content"] == "Invented first text"
    body = {"version": note["version"], "title": note["title"], "content": "Replacement text"}
    updated = client.put(path, json=body).json()["note"]
    assert updated["content"] == "Replacement text" and updated["version"] != note["version"]
    assert "Invented first text" not in repr(app.state.brain.__dict__)
    assert client.put(path, json=body).status_code == 409
    assert (
        client.post(path + "/delete-preview", json={"version": note["version"]}).status_code == 409
    )
    assert (
        client.post(
            path + "/delete-confirm",
            json={"version": updated["version"], "token": "none", "confirmed": True},
        ).status_code
        == 409
    )
    preview = client.post(path + "/delete-preview", json={"version": updated["version"]}).json()[
        "preview"
    ]
    assert preview["content"] == "Replacement text"
    confirm = {"version": updated["version"], "token": preview["token"], "confirmed": False}
    assert client.post(path + "/delete-confirm", json=confirm).status_code == 409
    assert (
        client.post(path + "/delete-confirm", json={**confirm, "confirmed": True}).status_code
        == 200
    )
    assert client.get(path).status_code == 404
    assert "Replacement text" not in repr(app.state.brain.__dict__)
    assert (
        client.post(path + "/delete-confirm", json={**confirm, "confirmed": True}).status_code
        == 404
    )


def test_delete_preview_expires_and_is_invalidated_by_edit(signed_in):
    client, app, _ = signed_in
    path = "/v1/brain/notes/credit-report"
    note = client.get(path).json()["note"]
    preview = client.post(path + "/delete-preview", json={"version": note["version"]}).json()[
        "preview"
    ]
    app.state.brain.previews[preview["token"]]["expires"] = datetime.now(UTC) - timedelta(seconds=1)
    confirm = {"version": note["version"], "token": preview["token"], "confirmed": True}
    assert client.post(path + "/delete-confirm", json=confirm).status_code == 409
    client.put(
        path,
        json={
            "version": note["version"],
            "title": note["title"],
            "content": "A different synthetic text",
        },
    )
    assert client.post(path + "/delete-confirm", json=confirm).status_code == 409


def test_brain_outage_does_not_block_application(signed_in):
    original, _, settings = signed_in
    client = TestClient(create_app(settings, UnavailableBrain()), base_url=settings.origin)
    client.cookies.update(original.cookies)
    client.headers.update(original.headers)
    assert client.get("/v1/brain/tree").status_code == 503
    assert client.get("/v1/brain/notes").status_code == 503
    assert client.get("/v1/application/routine").status_code == 200
    assert (
        client.post(
            "/v1/application/tasks",
            json={"title": "Synthetic outage task", "area": "work", "date": "2026-11-08"},
        ).status_code
        == 201
    )


def test_migrations_are_application_only_and_runtime_cannot_create_tables(postgres):
    Database(postgres["admin"]).migrate()
    with Database(postgres["admin"]).connect() as db:
        tables = {
            r["tablename"]
            for r in db.execute("SELECT tablename FROM pg_catalog.pg_tables WHERE schemaname='app'")
        }
        assert tables == {
            "schema_migrations",
            "sessions",
            "login_guard",
            "routines",
            "routine_progress",
            "tasks",
            "planning_goals",
            "projects",
            "routine_templates",
            "task_dependencies",
            "routine_exceptions",
            "calendar_events",
            "execution_blocks",
            "execution_sessions",
            "task_history",
            "daily_plans",
            "reminder_requests",
            "planning_commands",
            "note_refs",
            "task_note_links",
            "event_note_links",
            "event_task_links",
            "background_runs",
            "workspace_changes",
            "chat_conversations",
            "chat_messages",
            "chat_requests",
            "chat_attachments",
            "receiver_receipts",
            "calendar_date_items",
            "availability_windows",
            "date_item_note_links",
            "availability_note_links",
            "workflow_sources",
            "workflow_bindings",
            "workflow_changes",
            "workflow_reviews",
            "note_handoffs",
            "agent_runs",
            "agent_steps",
            "agent_proposals",
            "agent_note_events",
            "agent_write_intents",
            "agent_executions",
            "agent_effects",
            "yggdras_runs",
            "yggdras_feedback",
            "devices",
            "notifications",
            "calls",
            "call_schedules",
            "call_preferences",
            "call_events",
            "call_delivery",
            "voice_worker_lease",
            "call_commands",
            "call_reviews",
            "call_briefs",
            "item_outcomes",
            "conductor_runs",
            "conductor_events",
            "conductor_policy",
            "routine_important_blocks",
            "scheduled_jobs",
            "scheduled_job_attempts",
            "routine_escalations",
            "daily_routine_settings",
            "routine_checkins",
            "routine_predictions",
            "routine_pool",
            "routine_editions",
            "routine_hypotheses",
            "journal_entries",
            "daily_reviews",
            "daily_lessons",
            "daily_briefs",
            "daily_inputs",
            "daily_filing_runs",
            "daily_filing_actions",
            "web_push_subscriptions",
            "web_push_deliveries",
            "web_push_tokens",
            "routine_voice_bindings",
        }
    with (
        pytest.raises(psycopg.errors.InsufficientPrivilege),
        Database(postgres["runtime"]).connect() as db,
    ):
        db.execute("CREATE TABLE app.forbidden(id integer)")
    source = Path(__file__).parents[1] / "src" / "yggdress_app"
    assert all(
        "from yggdras" not in p.read_text(encoding="utf-8")
        and "import yggdras" not in p.read_text(encoding="utf-8")
        for p in source.glob("*.py")
    )


def test_runtime_role_cannot_reduce_goal_or_rewrite_progress_history(postgres):
    for query in (
        "UPDATE app.routines SET goal='reduced'",
        "DELETE FROM app.routine_progress",
        "SELECT * FROM app.schema_migrations",
    ):
        with (
            pytest.raises(psycopg.errors.InsufficientPrivilege),
            Database(postgres["runtime"]).connect() as db,
        ):
            db.execute(query)


def test_the_hosted_and_the_laptop_web_app_may_both_call_the_backend(setup):
    """YGGDRESS_ORIGIN lists the allowed web apps; anything else is refused, and plain HTTP
    is only for a loopback web app. An HTTPS one makes cookies secure."""
    from dataclasses import replace

    _, _, password, settings = setup
    both = replace(settings, origin="https://web.example.up.railway.app,http://127.0.0.1:3000",
                   local_http=False)  # fmt: skip
    both.validate()
    assert both.origins == ("https://web.example.up.railway.app", "http://127.0.0.1:3000")
    client = TestClient(create_app(both), base_url="https://web.example.up.railway.app")
    for origin, allowed in (("https://web.example.up.railway.app", True),
                            ("http://127.0.0.1:3000", True), ("https://evil.example", False)):  # fmt: skip
        answer = client.post("/v1/auth/login", json={"password": password},
                             headers={"Origin": origin, "X-Yggdress-Login": "1"})  # fmt: skip
        assert (answer.status_code != 403) is allowed, (origin, answer.status_code)
        if allowed:
            assert "secure" in answer.headers.get("set-cookie", "").lower()
    with pytest.raises(ValueError):
        replace(settings, origin="http://web.example.com", local_http=False).validate()
    with pytest.raises(ValueError):
        replace(
            settings, origin="https://a.example,http://127.0.0.1:3000", local_http=True
        ).validate()
