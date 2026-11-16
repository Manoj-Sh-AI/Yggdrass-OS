"""Source-note bridge: real application PostgreSQL; synthetic, read-only Brain."""

from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from notes_fixture import SyntheticBrain

from yggdress_app.application import create_app
from yggdress_app.database import Database
from yggdress_app.notes_proxy import NotesError

ROOT = "/v1/application/connections"


def payload(kind="task", **changes):
    return {
        "key": str(uuid4()),
        "operation": kind + ".create",
        "note_slug": "sample",
        "note_revision": "1",
        kind: (
            {
                "title": "Synthetic proposal",
                "objective": "Submit the agreed proposal.",
                "due_date": "2030-01-02",
            }
            if kind == "task"
            else {
                "title": "Synthetic review",
                "start": "2030-01-02T10:00",
                "end": "2030-01-02T11:00",
                "timezone": "Europe/Berlin",
            }
        ),
        **changes,
    }


def brain(app):
    fixture = SyntheticBrain()
    app.state.notes_proxy.http = fixture
    return fixture


@pytest.mark.parametrize("kind", ["task", "event"])
def test_atomic_creation_shared_records_provenance_and_restart(signed_in, kind):
    client, app, settings = signed_in
    fixture = brain(app)
    assert client.get(ROOT + "/capabilities").json() == {
        "linked_work": True,
        "automatic_interpretation": False,
    }
    body = payload(kind)
    created = client.post(ROOT + "/from-note", json=body)
    assert created.status_code == 200, created.text
    result = created.json()
    context = client.get(ROOT + "/notes/sample").json()
    item = context[kind + "s"][0]
    assert (
        item["id"] == result["id"] and item["source_revision"] == "1" and item["kind"] == "source"
    )
    snapshot = client.get(
        "/v1/application/planning?start=2030-01-02&end=2030-01-02&timezone=Europe%2FBerlin"
    ).json()
    assert any(item["id"] == result["id"] for item in snapshot[kind + "s"])
    if kind == "task":
        assert snapshot["blocks"] == []  # A deadline creates no invented work interval.
        assert context["tasks"][0]["objective"] == "Submit the agreed proposal."
    restarted = TestClient(create_app(settings), base_url=settings.origin)
    restarted.cookies.update(client.cookies)
    assert (
        restarted.get(ROOT + "/" + kind + "s/" + result["id"]).json()["notes"][0]["source_revision"]
        == "1"
    )
    assert all(method == "GET" for method, _, _ in fixture.calls)
    with Database(settings.database_url).connect() as db:
        changes = db.execute(
            "SELECT entity_type FROM app.workspace_changes WHERE command_id=%s", (body["key"],)
        ).fetchall()
        assert {row["entity_type"] for row in changes} >= {
            "note_refs",
            "task_note_links" if kind == "task" else "event_note_links",
            "tasks" if kind == "task" else "calendar_events",
        }


@pytest.mark.parametrize("kind", ["task", "event"])
def test_stale_missing_offline_and_mismatched_notes_do_not_create_work(signed_in, kind):
    client, app, settings = signed_in
    fixture = brain(app)
    assert (
        client.post(ROOT + "/from-note", json=payload(kind, note_revision="older")).status_code
        == 409
    )
    assert (
        client.post(ROOT + "/from-note", json=payload(kind, note_slug="missing")).status_code == 404
    )
    fixture.notes["sample"]["slug"] = "wrong"
    assert client.post(ROOT + "/from-note", json=payload(kind)).status_code == 502

    class Offline:
        def call(self, *args):
            raise NotesError(503, "Synthetic offline Brain")

    app.state.notes_proxy.http = Offline()
    assert client.post(ROOT + "/from-note", json=payload(kind)).status_code == 503
    with Database(settings.database_url).connect() as db:
        for table in (
            "tasks",
            "calendar_events",
            "note_refs",
            "workspace_changes",
            "planning_commands",
        ):
            assert db.execute(f"SELECT count(*) AS n FROM app.{table}").fetchone()["n"] == 0


def test_related_task_failure_rolls_back_source_history_journal_and_receipt(signed_in):
    client, app, settings = signed_in
    brain(app)
    body = payload()
    body["task"]["goal_id"] = str(uuid4())
    assert client.post(ROOT + "/from-note", json=body).status_code == 409
    with Database(settings.database_url).connect() as db:
        for table in (
            "tasks",
            "note_refs",
            "task_note_links",
            "task_history",
            "workspace_changes",
            "planning_commands",
        ):
            assert db.execute(f"SELECT count(*) AS n FROM app.{table}").fetchone()["n"] == 0


def test_concurrent_retries_and_offline_replay_return_one_original_commit(signed_in):
    client, app, settings = signed_in
    fixture = brain(app)
    body = payload()
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: client.post(ROOT + "/from-note", json=body), range(2)))
    assert all(response.status_code == 200 for response in responses)
    original = responses[0].json()
    assert original == responses[1].json()

    class Offline:
        def call(self, *args):
            raise AssertionError("Committed replay must not call Brain")

    app.state.notes_proxy.http = Offline()
    assert client.post(ROOT + "/from-note", json=body).json() == original
    assert client.post(ROOT + "/from-note", json={**body, "note_revision": "2"}).status_code == 409
    with Database(settings.database_url).connect() as db:
        for table in ("tasks", "note_refs", "task_note_links", "task_history", "planning_commands"):
            assert db.execute(f"SELECT count(*) AS n FROM app.{table}").fetchone()["n"] == 1
    assert all(method == "GET" for method, _, _ in fixture.calls)


def test_source_revision_survives_note_changes_completion_and_unlink(signed_in):
    client, app, settings = signed_in
    fixture = brain(app)
    first = client.post(ROOT + "/from-note", json=payload()).json()
    fixture.notes["sample"]["version"] = 2
    assert (
        client.post(ROOT + "/from-note", json=payload("event", note_revision="2")).status_code
        == 200
    )
    completed = client.post(
        "/v1/application/planning/commands",
        json={
            "key": str(uuid4()),
            "op": "task.execute",
            "id": first["id"],
            "version": first["version"],
            "data": {"action": "complete"},
        },
    )
    assert completed.status_code == 200
    context = client.get(ROOT + "/notes/sample").json()
    assert context["note_ref"]["observed_revision"] == "2"
    assert context["tasks"][0]["source_revision"] == "1" and context["tasks"][0]["done"]
    fixture.notes.clear()  # Archive/unavailability cannot delete application work.
    assert client.get(ROOT + "/notes/sample").json()["tasks"][0]["done"]
    assert (
        client.post(
            ROOT + "/commands",
            json={
                "key": str(uuid4()),
                "operation": "task.unlink_note",
                "entity_id": first["id"],
                "version": completed.json()["version"],
                "note_slug": "sample",
                "relation": "source",
            },
        ).status_code
        == 200
    )
    with Database(settings.database_url).connect() as db:
        assert db.execute("SELECT done FROM app.tasks WHERE id=%s", (first["id"],)).fetchone()[
            "done"
        ]


def test_strict_creation_contract_authentication_and_csrf(signed_in):
    client, app, settings = signed_in
    brain(app)
    anon = TestClient(app, base_url=settings.origin)
    assert anon.get(ROOT + "/capabilities").status_code == 401
    assert anon.post(ROOT + "/from-note", json=payload()).status_code == 401
    for bad in (
        payload(note_revision=""),
        payload(event={}),
        payload("event", event={"title": "Missing time", "start": "2030-01-02T10:00"}),
    ):
        assert client.post(ROOT + "/from-note", json=bad).status_code == 422
    client.headers.pop("X-Yggdress-CSRF")
    assert client.post(ROOT + "/from-note", json=payload()).status_code == 403
