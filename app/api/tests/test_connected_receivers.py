from uuid import uuid4

import psycopg
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from notes_fixture import SyntheticBrain

from yggdress_app.application import create_app
from yggdress_app.database import Database


def configured(signed_in):
    original, app, settings = signed_in
    brain = SyntheticBrain()
    app.state.notes_proxy.http = brain
    tokens = {
        name: name + "-synthetic-only-" + "x" * 40
        for name in ("note_signals", "workflow_dispatch", "workflow", "background")
    }
    test_app = create_app(settings, notes=app.state.notes_proxy, receiver_tokens=tokens)

    @test_app.exception_handler(psycopg.Error)
    async def synthetic_database_diagnostic(_request, error):
        return JSONResponse(
            {"detail": error.diag.message_primary or type(error).__name__}, status_code=503
        )

    client = TestClient(
        test_app,
        base_url=settings.origin,
    )
    client.cookies.update(original.cookies)
    client.headers.update(original.headers)
    return client, brain, tokens, settings


def post(client, path, payload, token=None, status=200):
    response = client.post(
        path, json=payload, headers={"Authorization": "Bearer " + token} if token else {}
    )
    assert response.status_code == status, response.text
    return response.json()


def signal(
    client,
    brain,
    tokens,
    sequence=0,
    previous=None,
    lifecycle="active",
    slug="sample",
    identity="immutable-synthetic-source",
):
    revision = str(brain.notes.get(slug, {}).get("version", sequence + 1))
    payload = {
        "id": str(uuid4()),
        "producer": "lia",
        "namespace": "synthetic-brain",
        "external_identity": identity,
        "sequence": sequence,
        "previous_revision": previous,
        "revision": revision,
        "slug": slug,
        "lifecycle": lifecycle,
        "context": "Synthetic source context",
        "dates": [
            {
                "meaning": "deadline",
                "precision": "date",
                "value": {"date": "2030-01-02"},
                "original_phrase": "Finish on 2 January",
            }
        ]
        if lifecycle == "active"
        else [],
    }
    post(client, "/v1/receivers/note-signals", payload, tokens["note_signals"])
    return payload


def interpretation(**changes):
    return {
        "commitment_identity": "finish-project",
        "meaning": "deadline",
        "precision": "date",
        "disposition": "clear",
        "entity_type": "task",
        "data": {
            "title": "Synthetic deadline",
            "objective": "Preserve this exact goal.",
            "due_date": "2030-01-02",
        },
        **changes,
    }


def apply(
    client, tokens, handoff, items, sequence=0, previous=None, producer="calendar-agent", status=200
):
    payload = {
        "change_id": str(uuid4()),
        "handoff_id": handoff["id"],
        "producer": producer,
        "producer_version": "synthetic-v1",
        "namespace": handoff["namespace"],
        "external_identity": handoff["external_identity"],
        "sequence": sequence,
        "previous_revision": previous,
        "revision": handoff["revision"],
        "slug": handoff["slug"],
        "lifecycle": handoff["lifecycle"],
        "interpretations": items,
    }
    return post(
        client, "/v1/receivers/workflow/changes", payload, tokens["workflow"], status
    ), payload


def test_lia_handoff_is_durable_read_only_context_until_agent_command(signed_in):
    client, brain, tokens, settings = configured(signed_in)
    event = signal(client, brain, tokens)
    assert (
        post(client, "/v1/receivers/note-signals", event, tokens["note_signals"])["work_changed"]
        is False
    )
    with Database(settings.database_url).connect() as db:
        assert db.execute("SELECT count(*) AS n FROM app.tasks").fetchone()["n"] == 0
    assert client.get("/v1/receivers/handoffs").status_code == 401
    pending = client.get(
        "/v1/receivers/handoffs", headers={"Authorization": "Bearer " + tokens["workflow_dispatch"]}
    ).json()
    assert (
        len(pending["handoffs"]) == 1
        and pending["handoffs"][0]["payload"]["context"] == "Synthetic source context"
    )
    assert post(
        client,
        "/v1/receivers/handoffs/acknowledge",
        {"id": event["id"]},
        tokens["workflow_dispatch"],
    )["acknowledged"]
    assert post(
        client,
        "/v1/receivers/handoffs/acknowledge",
        {"id": event["id"]},
        tokens["workflow_dispatch"],
    )["acknowledged"]


def test_agent_creates_once_with_real_fk_source_graph_and_retry_without_brain(signed_in):
    client, brain, tokens, settings = configured(signed_in)
    handoff = signal(client, brain, tokens)
    result, payload = apply(client, tokens, handoff, [interpretation()])
    item = result["results"][0]
    assert item["state"] == "applied"
    brain.notes.clear()
    with Database(settings.database_url).connect() as db:
        payload = db.execute("SELECT payload FROM app.workflow_changes").fetchone()["payload"]
    assert post(client, "/v1/receivers/workflow/changes", payload, tokens["workflow"]) == result
    with Database(settings.database_url).connect() as db:
        assert db.execute("SELECT count(*) AS n FROM app.tasks").fetchone()["n"] == 1
        assert (
            db.execute("SELECT task_id FROM app.workflow_bindings").fetchone()["task_id"]
            is not None
        )
    graph = client.get("/v1/application/work-graph", params={"root": "task:" + item["id"]}).json()
    assert {node["kind"] for node in graph["nodes"]} == {"task", "note"}
    assert graph["edges"][0]["relation"] == "source"
    assert all(method == "GET" for method, _, _ in brain.calls)


def test_source_and_handoff_versions_are_enforced_without_fabricated_updates(signed_in):
    client, brain, tokens, _ = configured(signed_in)
    h = signal(client, brain, tokens)
    brain.notes["sample"]["version"] = 2
    apply(client, tokens, h, [interpretation()], status=409)
    current = signal(client, brain, tokens, 1, "1")
    result, _ = apply(client, tokens, current, [interpretation()])
    assert result["results"][0]["state"] == "applied"
    altered = {**current, "id": str(uuid4()), "sequence": 3, "previous_revision": "2"}
    post(client, "/v1/receivers/note-signals", altered, tokens["note_signals"], 409)


def test_uncertain_relative_recurrence_and_historical_context_remain_truthful(signed_in):
    client, brain, tokens, settings = configured(signed_in)
    h = signal(client, brain, tokens)
    items = [
        interpretation(
            commitment_identity="vague",
            precision="relative",
            disposition="uncertain",
            original_phrase="sometime next month",
        ),
        interpretation(commitment_identity="repeat", meaning="recurrence"),
        interpretation(
            commitment_identity="past",
            meaning="historical",
            precision="year",
            action="context",
            data={"year": 1999},
        ),
    ]
    result, _ = apply(client, tokens, h, items)
    assert [r["state"] for r in result["results"]] == ["review", "review", "context"]
    reviews = client.get("/v1/application/workflow/reviews").json()["reviews"]
    assert len(reviews) == 2 and any(
        r["proposal"]["original_phrase"] == "sometime next month" for r in reviews
    )
    with Database(settings.database_url).connect() as db:
        assert db.execute("SELECT count(*) AS n FROM app.calendar_events").fetchone()["n"] == 0
        assert db.execute("SELECT count(*) AS n FROM app.tasks").fetchone()["n"] == 0


def test_manual_target_change_is_reviewed_and_goal_change_cannot_overwrite(signed_in):
    client, brain, tokens, settings = configured(signed_in)
    h = signal(client, brain, tokens)
    result, _ = apply(client, tokens, h, [interpretation()])
    task = result["results"][0]
    with Database(settings.database_url).connect() as db:
        db.execute(
            "UPDATE app.tasks SET title='Owner edited title',version=version+1 WHERE id=%s",
            (task["id"],),
        )
    brain.notes["sample"]["version"] = 2
    h2 = signal(client, brain, tokens, 1, "1")
    apply(
        client,
        tokens,
        h2,
        [
            interpretation(
                data={
                    "title": "New source title",
                    "objective": "Preserve this exact goal.",
                    "due_date": "2030-01-03",
                }
            )
        ],
        1,
        "1",
    )
    review = client.get("/v1/application/workflow/reviews").json()["reviews"][0]
    assert review["current"]["title"] == "Owner edited title"
    accepted = post(
        client,
        "/v1/application/workflow/reviews/resolve",
        {
            "key": str(uuid4()),
            "id": str(review["id"]),
            "version": review["version"],
            "decision": "accept",
            "target_version": review["current"]["version"],
        },
    )
    assert accepted["state"] == "applied"
    brain.notes["sample"]["version"] = 3
    h3 = signal(client, brain, tokens, 2, "2")
    apply(
        client,
        tokens,
        h3,
        [
            interpretation(
                data={"title": "Changed", "objective": "Different goal", "due_date": "2030-01-04"}
            )
        ],
        2,
        "2",
    )
    review = client.get("/v1/application/workflow/reviews").json()["reviews"][0]
    post(
        client,
        "/v1/application/workflow/reviews/resolve",
        {
            "key": str(uuid4()),
            "id": str(review["id"]),
            "version": review["version"],
            "decision": "accept",
            "target_version": review["current"]["version"],
        },
        status=409,
    )
    with Database(settings.database_url).connect() as db:
        assert (
            db.execute("SELECT objective FROM app.tasks WHERE id=%s", (task["id"],)).fetchone()[
                "objective"
            ]
            == "Preserve this exact goal."
        )


def test_archive_restore_rename_preserve_completed_work_and_stable_ref(signed_in):
    client, brain, tokens, settings = configured(signed_in)
    h = signal(client, brain, tokens)
    result, _ = apply(client, tokens, h, [interpretation()])
    task = result["results"][0]
    with Database(settings.database_url).connect() as db:
        ref = db.execute("SELECT note_ref_id FROM app.task_note_links").fetchone()["note_ref_id"]
        db.execute(
            "UPDATE app.tasks SET state='completed',done=true,version=version+1 WHERE id=%s",
            (task["id"],),
        )
    archived = signal(client, brain, tokens, 1, "1", "archived")
    apply(client, tokens, archived, [], 1, "1")
    assert (
        client.get("/v1/application/workflow/reviews").json()["reviews"][0]["lifecycle"]
        == "archived"
    )
    brain.notes["renamed"] = brain.notes.pop("sample")
    brain.notes["renamed"]["slug"] = "renamed"
    brain.notes["renamed"]["version"] = 3
    restored = signal(client, brain, tokens, 2, archived["revision"], slug="renamed")
    apply(client, tokens, restored, [interpretation()], 2, archived["revision"])
    with Database(settings.database_url).connect() as db:
        assert (
            db.execute("SELECT external_id FROM app.note_refs WHERE id=%s", (ref,)).fetchone()[
                "external_id"
            ]
            == "renamed"
        )
        assert db.execute("SELECT done FROM app.tasks WHERE id=%s", (task["id"],)).fetchone()[
            "done"
        ]
        assert db.execute("SELECT count(*) AS n FROM app.tasks").fetchone()["n"] == 1


def test_background_clocks_and_cancellation_are_separate_from_human_focus(signed_in):
    client, _, tokens, settings = configured(signed_in)
    event = {
        "event_key": str(uuid4()),
        "provider": "synthetic-pipeline",
        "external_run_id": "job-1",
        "sequence": 0,
        "label": "Synthetic pipeline",
        "state": "running",
    }
    run = post(client, "/v1/receivers/background/events", event, tokens["background"])["run"]
    assert (
        post(client, "/v1/receivers/background/events", event, tokens["background"])["run"]["id"]
        == run["id"]
    )
    cancelled = post(
        client,
        "/v1/application/background/cancel",
        {"key": str(uuid4()), "id": run["id"], "version": run["version"]},
    )["run"]
    assert cancelled["state"] == "running" and cancelled["cancellation_requested_at"]
    terminal = {**event, "event_key": str(uuid4()), "sequence": 1, "state": "cancelled"}
    finished = post(client, "/v1/receivers/background/events", terminal, tokens["background"])[
        "run"
    ]
    assert finished["ended_at"]
    post(
        client,
        "/v1/receivers/background/events",
        {**terminal, "event_key": str(uuid4()), "sequence": 2, "state": "running"},
        tokens["background"],
        409,
    )
    with Database(settings.database_url).connect() as db:
        assert db.execute("SELECT count(*) AS n FROM app.execution_sessions").fetchone()["n"] == 0


def test_receivers_disabled_or_auth_scoped_and_browser_cannot_impersonate_agents(signed_in):
    original, _, _ = signed_in
    assert original.get("/v1/receivers/handoffs").status_code == 503
    client, brain, tokens, _ = configured(signed_in)
    h = signal(client, brain, tokens)
    result, payload = apply(client, tokens, h, [interpretation()])
    assert result["results"][0]["state"] == "applied"
    post(
        client,
        "/v1/receivers/workflow/changes",
        {**payload, "change_id": str(uuid4())},
        tokens["note_signals"],
        401,
    )
    assert (
        TestClient(client.app, base_url="http://127.0.0.1")
        .get("/v1/application/work-graph/roots")
        .status_code
        == 401
    )


def test_graph_remains_bounded_with_ten_thousand_tasks(signed_in):
    client, brain, tokens, settings = configured(signed_in)
    h = signal(client, brain, tokens)
    result, _ = apply(client, tokens, h, [interpretation()])
    root = result["results"][0]["id"]
    with Database(settings.database_url).connect() as db:
        db.execute("SET LOCAL statement_timeout='60s'")
        goal = db.execute(
            "INSERT INTO app.planning_goals(id,title,description) VALUES (gen_random_uuid(),'Synthetic goal','') RETURNING id"
        ).fetchone()["id"]
        db.execute("UPDATE app.tasks SET goal_id=%s WHERE id=%s", (goal, root))
        db.execute(
            "INSERT INTO app.tasks(id,title,objective,area,due_date,goal_id) SELECT gen_random_uuid(),'Synthetic task '||n,'Keep goal','work','2030-01-02',%s FROM generate_series(1,10000)n",
            (goal,),
        )
    graph = client.get(
        "/v1/application/work-graph", params={"root": "task:" + root, "depth": 2, "limit": 40}
    ).json()
    assert len(graph["nodes"]) <= 40 and len(graph["edges"]) <= 160 and graph["truncated"]
    assert len(client.get("/v1/application/work-graph/roots?limit=30").json()["roots"]) == 30


def test_receiving_exact_and_all_day_times_do_not_guess_offsets_or_create_focus(signed_in):
    client, brain, tokens, settings = configured(signed_in)
    h = signal(client, brain, tokens)
    items = [
        interpretation(
            commitment_identity="appointment",
            meaning="appointment",
            precision="interval",
            entity_type="event",
            data={
                "title": "Synthetic appointment",
                "start": "2030-01-02T10:00:00+01:00",
                "end": "2030-01-02T11:00:00+01:00",
                "timezone": "Europe/Berlin",
            },
        ),
        interpretation(
            commitment_identity="all-day",
            meaning="review",
            entity_type="date_item",
            data={
                "title": "Synthetic review date",
                "kind": "review",
                "starts_on": "2030-01-02",
                "ends_before": "2030-01-03",
            },
        ),
        interpretation(
            commitment_identity="ambiguous",
            meaning="appointment",
            precision="datetime",
            entity_type="event",
            data={"title": "Needs timezone", "start": "2030-01-02T10:00", "duration_minutes": 30},
        ),
    ]
    result, _ = apply(client, tokens, h, items)
    assert [r["state"] for r in result["results"]] == ["applied", "applied", "review"]
    with Database(settings.database_url).connect() as db:
        assert db.execute("SELECT count(*) AS n FROM app.calendar_events").fetchone()["n"] == 1
        assert db.execute("SELECT count(*) AS n FROM app.calendar_date_items").fetchone()["n"] == 1
        assert db.execute("SELECT count(*) AS n FROM app.execution_sessions").fetchone()["n"] == 0


def test_explicit_cancellation_requires_confirmation_and_preserves_goal_history(signed_in):
    client, brain, tokens, settings = configured(signed_in)
    h = signal(client, brain, tokens)
    created, _ = apply(client, tokens, h, [interpretation()])
    identifier = created["results"][0]["id"]
    apply(client, tokens, h, [interpretation(action="retract", meaning="cancellation")], 1, "1")
    review = client.get("/v1/application/workflow/reviews").json()["reviews"][0]
    with Database(settings.database_url).connect() as db:
        assert (
            db.execute("SELECT state FROM app.tasks WHERE id=%s", (identifier,)).fetchone()["state"]
            == "todo"
        )
    post(
        client,
        "/v1/application/workflow/reviews/resolve",
        {
            "key": str(uuid4()),
            "id": str(review["id"]),
            "version": review["version"],
            "decision": "accept",
            "target_version": review["current"]["version"],
        },
    )
    with Database(settings.database_url).connect() as db:
        row = db.execute("SELECT * FROM app.tasks WHERE id=%s", (identifier,)).fetchone()
        assert row["state"] == "skipped" and row["objective"] == "Preserve this exact goal."
        assert (
            db.execute(
                "SELECT count(*) AS n FROM app.task_history WHERE task_id=%s AND kind='source.cancel'",
                (identifier,),
            ).fetchone()["n"]
            == 1
        )


def test_concurrent_agent_redelivery_commits_once_and_receipts_survive_api_restart(signed_in):
    from concurrent.futures import ThreadPoolExecutor

    client, brain, tokens, settings = configured(signed_in)
    h = signal(client, brain, tokens)
    payload = {
        "change_id": str(uuid4()),
        "handoff_id": h["id"],
        "producer": "task-agent",
        "producer_version": "synthetic-v1",
        "namespace": h["namespace"],
        "external_identity": h["external_identity"],
        "sequence": 0,
        "revision": "1",
        "slug": "sample",
        "interpretations": [interpretation()],
    }

    def send(_):
        return client.post(
            "/v1/receivers/workflow/changes",
            headers={"Authorization": "Bearer " + tokens["workflow"]},
            json=payload,
        )

    with ThreadPoolExecutor(max_workers=4) as workers:
        responses = list(workers.map(send, range(4)))
    assert all(response.status_code == 200 for response in responses)
    assert all(response.json() == responses[0].json() for response in responses)
    brain.notes.clear()
    restarted = TestClient(
        create_app(settings, notes=client.app.state.notes_proxy, receiver_tokens=tokens),
        base_url=settings.origin,
    )
    assert (
        restarted.post(
            "/v1/receivers/workflow/changes",
            headers={"Authorization": "Bearer " + tokens["workflow"]},
            json=payload,
        ).json()
        == responses[0].json()
    )
    with Database(settings.database_url).connect() as db:
        assert db.execute("SELECT count(*) AS n FROM app.tasks").fetchone()["n"] == 1
        assert db.execute("SELECT count(*) AS n FROM app.workflow_changes").fetchone()["n"] == 1


def test_binding_existing_manual_work_requires_review_and_never_duplicates(signed_in):
    client, brain, tokens, settings = configured(signed_in)
    created = post(
        client,
        "/v1/application/planning/commands",
        {
            "key": str(uuid4()),
            "op": "task.create",
            "data": {
                "title": "Existing owner task",
                "objective": "Keep this exact goal.",
                "due_date": "2030-01-02",
            },
        },
    )
    linked = post(
        client,
        "/v1/application/connections/commands",
        {
            "key": str(uuid4()),
            "operation": "task.link_note",
            "entity_id": created["id"],
            "version": created["version"],
            "note_slug": "sample",
        },
    )
    created["version"] = linked["version"]
    h = signal(client, brain, tokens)
    cursor = client.get(
        "/v1/receivers/workflow/source",
        params={"handoff_id": h["id"]},
        headers={"Authorization": "Bearer " + tokens["workflow"]},
    ).json()
    assert cursor["linked_targets"][0]["id"] == created["id"] and cursor["next_sequence"] == 0
    proposal = interpretation(
        target_id=created["id"],
        target_version=created["version"],
        data={
            "title": "Existing owner task",
            "objective": "Keep this exact goal.",
            "due_date": "2030-01-03",
        },
    )
    result, _ = apply(client, tokens, h, [proposal])
    assert result["results"][0]["state"] == "review"
    review = client.get("/v1/application/workflow/reviews").json()["reviews"][0]
    assert str(review["current"]["id"]) == created["id"]
    post(
        client,
        "/v1/application/workflow/reviews/resolve",
        {
            "key": str(uuid4()),
            "id": str(review["id"]),
            "version": review["version"],
            "decision": "accept",
            "target_version": created["version"],
        },
    )
    with Database(settings.database_url).connect() as db:
        assert db.execute("SELECT count(*) AS n FROM app.tasks").fetchone()["n"] == 1
        assert (
            str(db.execute("SELECT entity_id FROM app.workflow_bindings").fetchone()["entity_id"])
            == created["id"]
        )
