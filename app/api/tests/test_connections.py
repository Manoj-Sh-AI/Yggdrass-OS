from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from notes_fixture import SyntheticBrain

from yggdress_app.application import create_app
from yggdress_app.database import Database

ROOT = "/v1/application/connections"
PLANNING = "/v1/application/planning"


def plan(client, op, data, identifier=None, version=None, key=None):
    response = client.post(
        PLANNING + "/commands",
        json={
            "key": key or str(uuid4()),
            "op": op,
            "data": data,
            "id": identifier,
            "version": version,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def task(client):
    return plan(
        client,
        "task.create",
        {"title": "Synthetic garden plan", "objective": "Keep three decisions unchanged."},
    )


def event(client):
    return plan(
        client,
        "event.create",
        {"title": "Synthetic meeting", "start": "2030-01-02T10:00", "end": "2030-01-02T11:00"},
    )


def link(client, operation, item, *, status=200, **fields):
    body = {
        "key": str(uuid4()),
        "operation": operation,
        "entity_id": item["id"],
        "version": item["version"],
        **fields,
    }
    response = client.post(ROOT + "/commands", json=body)
    assert response.status_code == status, response.text
    return response.json(), body


def wire(app):
    brain = SyntheticBrain()
    app.state.notes_proxy.http = brain
    return brain


def test_links_share_source_context_and_survive_completion_restart_and_unlink(signed_in):
    client, app, settings = signed_in
    wire(app)
    work, meeting = task(client), event(client)
    first, _ = link(client, "task.link_note", work, note_slug="sample", relation="source")
    work["version"] = first["version"]
    second, _ = link(client, "event.link_note", meeting, note_slug="sample", relation="context")
    meeting["version"] = second["version"]
    paired, _ = link(
        client, "event.link_task", meeting, task_id=work["id"], task_version=work["version"]
    )
    meeting["version"], work["version"] = paired["version"], paired["task_version"]
    context = client.get(ROOT + "/notes/sample").json()
    assert context["tasks"][0]["objective"] == "Keep three decisions unchanged."
    assert context["events"][0]["id"] == meeting["id"]
    assert client.get(ROOT + "/tasks/" + work["id"]).json()["events"][0]["id"] == meeting["id"]
    assert client.get(ROOT + "/events/" + meeting["id"]).json()["tasks"][0]["id"] == work["id"]
    completed = plan(client, "task.execute", {"action": "complete"}, work["id"], work["version"])
    work["version"] = completed["version"]
    restarted = TestClient(create_app(settings), base_url=settings.origin)
    restarted.cookies.update(client.cookies)
    assert restarted.get(ROOT + "/notes/sample").json()["tasks"][0]["state"] == "completed"
    link(client, "task.unlink_note", work, note_slug="sample", relation="source")
    after = client.get(ROOT + "/notes/sample").json()
    assert after["tasks"] == [] and len(after["events"]) == 1
    with Database(settings.database_url).connect() as db:
        saved = db.execute("SELECT * FROM app.tasks WHERE id=%s", (work["id"],)).fetchone()
        assert saved["done"] and saved["objective"] == "Keep three decisions unchanged."
        assert (
            db.execute(
                "SELECT count(*) AS n FROM app.task_history WHERE task_id=%s", (work["id"],)
            ).fetchone()["n"]
            >= 2
        )


def test_replay_is_independent_of_brain_and_duplicates_do_not_bump_versions(signed_in):
    client, app, settings = signed_in
    wire(app)
    work = task(client)
    saved, body = link(client, "task.link_note", work, note_slug="sample")
    with Database(settings.database_url).connect() as db:
        before = db.execute("SELECT count(*) AS n FROM app.workspace_changes").fetchone()["n"]

    class Offline:
        def call(self, *args):
            raise AssertionError("Replay/unlink must not call Brain")

    app.state.notes_proxy.http = Offline()
    assert client.post(ROOT + "/commands", json=body).json() == saved
    with Database(settings.database_url).connect() as db:
        assert (
            db.execute("SELECT count(*) AS n FROM app.workspace_changes").fetchone()["n"] == before
        )
    changed_body = {**body, "relation": "result"}
    assert client.post(ROOT + "/commands", json=changed_body).status_code == 409
    wire(app)
    work["version"] = saved["version"]
    noop, _ = link(client, "task.link_note", work, note_slug="sample")
    assert not noop["changed"] and noop["version"] == work["version"]
    app.state.notes_proxy.http = Offline()
    link(client, "task.unlink_note", work, note_slug="sample")


def test_missing_source_target_and_stale_versions_never_create_connections(signed_in):
    client, app, settings = signed_in
    wire(app)
    work = task(client)
    link(client, "task.link_note", work, note_slug="missing", status=404)
    link(client, "task.link_note", {**work, "id": str(uuid4())}, note_slug="sample", status=404)
    updated = plan(
        client, "task.execute", {"action": "progress", "percent": 10}, work["id"], work["version"]
    )
    link(client, "task.link_note", work, note_slug="sample", status=409)
    assert updated["version"] > work["version"]
    with Database(settings.database_url).connect() as db:
        assert db.execute("SELECT count(*) AS n FROM app.note_refs").fetchone()["n"] == 0
        assert db.execute("SELECT count(*) AS n FROM app.task_note_links").fetchone()["n"] == 0


def test_cancelled_events_and_stale_second_target_are_rejected(signed_in):
    client, app, settings = signed_in
    wire(app)
    work, meeting = task(client), event(client)
    plan(client, "task.execute", {"action": "progress", "percent": 5}, work["id"], work["version"])
    link(
        client,
        "event.link_task",
        meeting,
        task_id=work["id"],
        task_version=work["version"],
        status=409,
    )
    removed = plan(client, "event.remove", {}, meeting["id"], meeting["version"])
    meeting["version"] = removed["version"]
    link(client, "event.link_note", meeting, note_slug="sample", status=409)
    with Database(settings.database_url).connect() as db:
        assert db.execute("SELECT count(*) AS n FROM app.event_task_links").fetchone()["n"] == 0


def test_local_foreign_keys_and_runtime_journal_permissions(signed_in, postgres):
    client, app, settings = signed_in
    wire(app)
    with (
        pytest.raises(psycopg.errors.ForeignKeyViolation),
        Database(settings.database_url).connect() as db,
    ):
        db.execute(
            "INSERT INTO app.event_task_links(event_id,task_id) VALUES (%s,%s)",
            (uuid4(), uuid4()),
        )
    task(client)
    for operation in (
        "DELETE FROM app.workspace_changes",
        "UPDATE app.workspace_changes SET actor='forged'",
        "INSERT INTO app.workspace_changes(entity_type,entity_id,operation,actor,detail) VALUES('fake','fake','INSERT','fake','{}')",
    ):
        with (
            pytest.raises(psycopg.errors.InsufficientPrivilege),
            Database(settings.database_url).connect() as db,
        ):
            db.execute(operation)
    with Database(postgres["admin"]).connect() as db:
        assert not db.execute(
            "SELECT 1 FROM information_schema.schemata WHERE schema_name='brain'"
        ).fetchone()


def test_journal_rolls_back_and_receipt_replay_does_not_repeat_changes(signed_in, postgres):
    client, _, settings = signed_in
    key = str(uuid4())
    created = plan(
        client, "task.create", {"title": "Synthetic atomic", "objective": "Exactly once"}, key=key
    )
    with Database(settings.database_url).connect() as db:
        first = db.execute(
            "SELECT * FROM app.workspace_changes WHERE command_id=%s", (key,)
        ).fetchall()
        assert len(first) == 1 and first[0]["entity_id"] == created["id"]
        assert "title" in first[0]["detail"]["changed_fields"]
        assert "Exactly once" not in str(first[0]["detail"])
    plan(client, "task.create", {"title": "Synthetic atomic", "objective": "Exactly once"}, key=key)
    try:
        with Database(postgres["admin"]).connect() as db:
            db.execute("UPDATE app.tasks SET version=version+1 WHERE id=%s", (created["id"],))
            raise RuntimeError("Synthetic rollback")
    except RuntimeError:
        pass
    with Database(settings.database_url).connect() as db:
        assert (
            len(
                db.execute(
                    "SELECT * FROM app.workspace_changes WHERE entity_id=%s", (created["id"],)
                ).fetchall()
            )
            == 1
        )


def test_background_elapsed_is_not_human_focus_time(signed_in, postgres):
    client, _, settings = signed_in
    work = task(client)
    now = datetime.now(UTC)
    with Database(postgres["admin"]).connect() as db:
        db.execute(
            "INSERT INTO app.background_runs(task_id,provider,external_run_id,label,state,created_at,started_at) VALUES (%s,'fixture','job-1','Synthetic pipeline','running',%s,%s)",
            (work["id"], now - timedelta(hours=2), now - timedelta(hours=1)),
        )
    context = client.get(ROOT + "/tasks/" + work["id"]).json()
    assert 3600 <= float(context["background_runs"][0]["elapsed_seconds"]) < 3610
    snapshot = client.get(
        PLANNING, params={"start": now.date(), "end": now.date(), "timezone": "UTC"}
    ).json()
    assert snapshot["sessions"] == []
    assert snapshot["summaries"][0]["actual_minutes"] == 0
    with Database(settings.database_url).connect() as db:
        assert not db.execute("SELECT done FROM app.tasks WHERE id=%s", (work["id"],)).fetchone()[
            "done"
        ]
        edges = db.execute(
            "SELECT relation FROM app.operational_edges WHERE source=%s", ("task:" + work["id"],)
        ).fetchall()
        assert "runs_in_background" in [edge["relation"] for edge in edges]


def test_authenticated_bounded_reads_and_csrf(setup, signed_in):
    # Use the signed-in fixture's app; an independent client has no session.
    client, app, settings = signed_in
    anon = TestClient(app, base_url=settings.origin)
    assert anon.get(ROOT + "/notes/sample").status_code == 401
    assert client.get(ROOT + "/notes/sample?limit=101").status_code == 422
    assert client.get(ROOT + "/notes/sample").json()["tasks"] == []
    client.headers.pop("X-Yggdress-CSRF")
    assert (
        client.post(
            ROOT + "/commands",
            json={
                "key": str(uuid4()),
                "operation": "task.link_note",
                "entity_id": str(uuid4()),
                "version": 1,
                "note_slug": "sample",
            },
        ).status_code
        == 403
    )


def test_concurrent_retry_creates_only_one_link_and_source_reference(signed_in):
    client, app, settings = signed_in
    brain = wire(app)
    work = task(client)
    body = {
        "key": str(uuid4()),
        "operation": "task.link_note",
        "entity_id": work["id"],
        "version": work["version"],
        "note_slug": "sample",
    }
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: client.post(ROOT + "/commands", json=body), range(2)))
    assert all(response.status_code == 200 for response in responses)
    assert responses[0].json() == responses[1].json()
    assert all(method == "GET" for method, _, _ in brain.calls)
    with Database(settings.database_url).connect() as db:
        assert db.execute("SELECT count(*) AS n FROM app.task_note_links").fetchone()["n"] == 1
        assert db.execute("SELECT count(*) AS n FROM app.note_refs").fetchone()["n"] == 1
