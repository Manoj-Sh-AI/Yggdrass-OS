from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient

from yggdress_app.application import create_app
from yggdress_app.database import Database

ROOT = "/v1/application/planning"


def send(client, op, data=None, identifier=None, version=None, key=None, status=200):
    response = client.post(
        ROOT + "/commands",
        json={
            "key": key or str(uuid4()),
            "op": op,
            "data": data or {},
            "id": identifier,
            "version": version,
        },
    )
    assert response.status_code == status, response.text
    return response.json()


def read(client, start="2026-03-01", end="2026-04-01", timezone="Europe/Berlin"):
    response = client.get(ROOT, params={"start": start, "end": end, "timezone": timezone})
    assert response.status_code == 200, response.text
    return response.json()


def task(client, **values):
    body = {
        "title": "Synthetic research",
        "objective": "Write three original observations",
        "due_date": "2026-03-30",
        **values,
    }
    return send(client, "task.create", body), body


def block(client, task_id, **values):
    return send(
        client,
        "block.create",
        {"task_id": task_id, "start": "2026-03-28T09:00", "end": "2026-03-28T10:00", **values},
    )


def routine(client, **values):
    body = {
        "title": "Synthetic daily care",
        "objective": "Keep the original essential commitment",
        "starts_on": "2026-03-27",
        "window_start": "02:30",
        "window_end": "04:00",
        "expected_minutes": 20,
        "essential": True,
        **values,
    }
    return send(client, "routine.create", body), body


def test_schedule_reschedule_split_remove_preserve_commitments_and_restart(signed_in):
    client, _, settings = signed_in
    created, body = task(client)
    scheduled = block(client, created["id"])
    send(
        client,
        "block.update",
        {"start": "2026-03-29T10:00", "end": "2026-03-29T11:00", "reason": "Manual reschedule"},
        scheduled["id"],
        1,
    )
    send(client, "block.split", {"at": "2026-03-29T08:30:00Z"}, scheduled["id"], 2)
    state = read(client)
    assert len(state["blocks"]) == 2
    assert state["tasks"][0]["objective"] == body["objective"]
    assert state["tasks"][0]["due_date"] == body["due_date"]
    first = state["blocks"][0]
    send(client, "block.remove", {}, first["id"], first["version"])
    restarted = TestClient(create_app(settings), base_url=settings.origin)
    restarted.cookies.update(client.cookies)
    after = read(restarted)
    assert len(after["tasks"]) == 1 and len(after["blocks"]) == 1
    assert after["tasks"][0]["objective"] == body["objective"]


def test_retry_receipts_and_optimistic_versions(signed_in):
    client = signed_in[0]
    key = str(uuid4())
    first = send(
        client, "task.create", {"title": "Synthetic retry", "objective": "Exactly once"}, key=key
    )
    assert (
        send(
            client,
            "task.create",
            {"title": "Synthetic retry", "objective": "Exactly once"},
            key=key,
        )
        == first
    )
    send(
        client,
        "task.create",
        {"title": "Changed payload", "objective": "Exactly once"},
        key=key,
        status=409,
    )
    send(client, "task.execute", {"action": "progress", "percent": 20}, first["id"], 1)
    send(client, "task.execute", {"action": "progress", "percent": 50}, first["id"], 1, status=409)
    assert len(read(client)["tasks"]) == 1
    assert read(client)["tasks"][0]["progress"] == 20


def test_concurrent_updates_only_one_wins(signed_in):
    client = signed_in[0]
    created, _ = task(client)

    def mutate(percent):
        return client.post(
            ROOT + "/commands",
            json={
                "key": str(uuid4()),
                "op": "task.execute",
                "id": created["id"],
                "version": 1,
                "data": {"action": "progress", "percent": percent},
            },
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(mutate, [25, 50])) == [200, 409]


def test_execution_pause_resume_reload_and_completion(signed_in):
    client, app, settings = signed_in
    created, body = task(client)
    identifier = created["id"]
    send(client, "task.execute", {"action": "start"}, identifier, 1)
    with app.state.database.connect() as db:
        db.execute(
            "UPDATE app.execution_sessions SET started_at=clock_timestamp()-interval '10 minutes' WHERE task_id=%s",
            (identifier,),
        )
    restarted = TestClient(create_app(settings), base_url=settings.origin)
    restarted.cookies.update(client.cookies)
    restarted.headers.update(client.headers)
    client = restarted
    assert read(client)["tasks"][0]["actual_seconds"] >= 599
    send(client, "task.execute", {"action": "pause"}, identifier, 2)
    today = str(date.today())
    paused = read(client, today, today)
    assert paused["tasks"][0]["state"] == "paused" and paused["sessions"][0]["ended_at"]
    send(client, "task.execute", {"action": "resume"}, identifier, 3)
    assert len(read(client, today, today)["sessions"]) == 2
    send(client, "task.execute", {"action": "progress", "percent": 100}, identifier, 4)
    assert not read(client)["tasks"][0]["done"]
    send(client, "task.execute", {"action": "complete"}, identifier, 5)
    final = read(client)
    assert final["tasks"][0]["done"] and final["tasks"][0]["objective"] == body["objective"]
    assert client.get("/v1/application/tasks").json()["tasks"][0]["done"]


def test_only_one_focus_session_and_legacy_completion_closes_it(signed_in):
    client = signed_in[0]
    a, _ = task(client)
    b, _ = task(client)
    send(client, "task.execute", {"action": "start"}, a["id"], 1)
    send(client, "task.execute", {"action": "start"}, b["id"], 1, status=409)
    assert client.patch(f"/v1/application/tasks/{a['id']}", json={"done": True}).status_code == 200
    assert all(
        s["ended_at"] for s in read(client, str(date.today()), str(date.today()))["sessions"]
    )


def test_daily_recurrence_dst_gap_idempotency_and_occurrence_edit(signed_in):
    client = signed_in[0]
    template, original = routine(client)
    scope = {"start": "2026-03-27", "end": "2026-03-30"}
    assert send(client, "ensure", scope)["generated"] == 4
    assert send(client, "ensure", scope)["generated"] == 0
    state = read(client)
    occurrence = next(t for t in state["tasks"] if t["occurrence_date"] == "2026-03-29")
    scheduled = next(b for b in state["blocks"] if b["task_id"] == occurrence["id"])
    assert scheduled["starts_at"].startswith("2026-03-29T01:00")  # 03:00 after missing 02:30
    send(
        client,
        "task.update",
        {
            "title": "Only this occurrence",
            "objective": original["objective"],
            "due_date": "2026-03-29",
        },
        occurrence["id"],
        occurrence["version"],
    )
    after = read(client)
    assert after["routines"][0]["title"] == original["title"]
    assert sum(t["title"] == "Only this occurrence" for t in after["tasks"]) == 1
    send(client, "routine.skip", {"day": "2026-03-30"}, template["id"], 1)
    send(client, "ensure", scope)
    assert len(read(client)["tasks"]) == 4
    assert (
        next(t for t in read(client)["tasks"] if t["occurrence_date"] == "2026-03-30")["state"]
        == "skipped"
    )


def test_weekly_routine_intervals_and_exception(signed_in):
    client = signed_in[0]
    routine(client, starts_on="2026-03-02", frequency="weekly", weekdays=[0, 2], interval_count=2)
    send(client, "ensure", {"start": "2026-03-01", "end": "2026-03-31"})
    assert sorted(t["occurrence_date"] for t in read(client)["tasks"]) == [
        "2026-03-02",
        "2026-03-04",
        "2026-03-16",
        "2026-03-18",
        "2026-03-30",
    ]


def test_explicit_future_series_update_preserves_started_and_edited(signed_in):
    client = signed_in[0]
    start = date.today() + timedelta(days=1)
    end = start + timedelta(days=2)
    template, body = routine(client, starts_on=str(start))
    send(client, "ensure", {"start": str(start), "end": str(end)})
    tasks = read(client, str(start), str(end))["tasks"]
    edited = tasks[0]
    send(
        client,
        "task.update",
        {"title": "Explicit occurrence", "objective": body["objective"]},
        edited["id"],
        1,
    )
    send(client, "routine.update", {**body, "title": "Future series"}, template["id"], 1)
    updated = read(client, str(start), str(end))
    assert (
        next(t for t in updated["tasks"] if t["id"] == edited["id"])["title"]
        == "Explicit occurrence"
    )
    assert sum(t["title"] == "Future series" for t in updated["tasks"]) == 2
    assert len(updated["blocks"]) == 3


def test_timezone_gap_fold_midnight_and_conflicts_are_retained(signed_in):
    client = signed_in[0]
    created, _ = task(client)
    send(
        client,
        "block.create",
        {"task_id": created["id"], "start": "2026-03-29T02:30", "end": "2026-03-29T04:00"},
        status=422,
    )
    first = block(
        client, created["id"], start="2026-10-25T02:15", end="2026-10-25T02:45", fold=0, end_fold=0
    )
    second = block(
        client, created["id"], start="2026-10-25T02:15", end="2026-10-25T02:45", fold=1, end_fold=1
    )
    autumn = read(client, "2026-10-24", "2026-10-26")
    assert {b["starts_at"] for b in autumn["blocks"]} == {
        "2026-10-25T00:15:00+00:00",
        "2026-10-25T01:15:00+00:00",
    }
    assert first["id"] != second["id"]
    block(client, created["id"], start="2026-03-28T23:30", end="2026-03-29T03:30")
    send(
        client,
        "event.create",
        {"title": "Synthetic fixed event", "start": "2026-03-29T03:00", "end": "2026-03-29T04:00"},
    )
    state = read(client, "2026-03-29", "2026-03-29")
    assert len(state["blocks"]) == 1 and len(state["events"]) == 1
    b = state["blocks"][0]
    assert (
        datetime.fromisoformat(b["ends_at"]) - datetime.fromisoformat(b["starts_at"])
    ).total_seconds() == 3 * 3600


def test_goal_project_subtasks_dependencies_and_cycles(signed_in):
    client = signed_in[0]
    goal = send(client, "goal.create", {"title": "Synthetic milestone"})
    project = send(client, "project.create", {"title": "Synthetic project", "goal_id": goal["id"]})
    parent, _ = task(client, goal_id=goal["id"], project_id=project["id"])
    child, body = task(client, parent_id=parent["id"])
    dependent, _ = task(client, dependencies=[child["id"]])
    send(client, "task.execute", {"action": "complete"}, parent["id"], 1, status=409)
    send(client, "task.execute", {"action": "start"}, dependent["id"], 1, status=409)
    send(
        client,
        "task.update",
        {**body, "dependencies": [dependent["id"]]},
        child["id"],
        1,
        status=422,
    )
    send(client, "task.execute", {"action": "complete"}, child["id"], 1)
    send(client, "task.execute", {"action": "complete"}, parent["id"], 1)
    assert read(client)["goals"][0]["title"] == "Synthetic milestone"


def test_daily_plan_context_concurrency_reminder_readiness(signed_in):
    client = signed_in[0]
    created, _ = task(client)
    block(client, created["id"])
    body = {
        "day": "2026-03-28",
        "available_minutes": 45,
        "energy": "User says low",
        "sleep": "Optional voluntary context",
        "confirm": True,
    }
    send(client, "daily.save", body)
    send(
        client, "daily.save", {**body, "review": True, "reflection": "Continue tomorrow"}, version=1
    )
    send(client, "daily.save", body, version=1, status=409)
    snapshot = read(client)
    assert snapshot["plans"][0]["confirmed_at"] and snapshot["plans"][0]["reviewed_at"]
    assert len(snapshot["reminders"]) == 2
    send(client, "reminder.ack", {"reminder_id": snapshot["reminders"][0]["id"]})
    assert len(read(client)["reminders"]) == 1


def test_auth_input_boundaries_and_brain_untouched(setup, signed_in):
    client, app, _ = signed_in
    anonymous = TestClient(app)
    assert (
        anonymous.get(ROOT, params={"start": "2026-03-01", "end": "2026-03-02"}).status_code == 401
    )
    assert (
        anonymous.post(ROOT + "/commands", json={"key": str(uuid4()), "op": "ensure"}).status_code
        == 401
    )
    assert client.get(ROOT, params={"start": "2026-01-01", "end": "2026-12-31"}).status_code == 422
    assert (
        client.get(
            ROOT, params={"start": "2026-01-01", "end": "2026-01-02", "timezone": "fake/zone"}
        ).status_code
        == 422
    )
    send(client, "task.create", {"title": " ", "objective": "Anything"}, status=422)
    before = client.get("/v1/brain/notes").json()
    task(client)
    assert client.get("/v1/brain/notes").json() == before


def test_runtime_cannot_delete_history_or_receipts(postgres):
    import psycopg
    import pytest

    for table in ("task_history", "execution_sessions", "planning_commands"):
        with (
            pytest.raises(psycopg.errors.InsufficientPrivilege),
            Database(postgres["runtime"]).connect() as db,
        ):
            db.execute(f"DELETE FROM app.{table}")


def test_elapsed_drag_duration_across_dst_and_day_capacity_clipping(signed_in):
    client = signed_in[0]
    created, _ = task(client)
    scheduled = send(
        client,
        "block.create",
        {"task_id": created["id"], "start": "2026-03-29T01:30", "duration_minutes": 60},
    )
    state = read(client, "2026-03-29", "2026-03-29")
    block_row = next(b for b in state["blocks"] if b["id"] == scheduled["id"])
    assert block_row["ends_at"].startswith("2026-03-29T01:30")
    assert state["summaries"][0]["scheduled_minutes"] == 60
    send(
        client,
        "block.create",
        {"task_id": created["id"], "start": "2026-03-28T23:30", "end": "2026-03-29T00:30"},
    )
    state = read(client, "2026-03-28", "2026-03-29")
    assert state["summaries"][0]["scheduled_minutes"] == 30
    assert state["summaries"][1]["scheduled_minutes"] == 90


def test_execution_snapshots_selected_window_and_expected_duration(signed_in):
    client = signed_in[0]
    created, _ = task(client)
    scheduled = block(client, created["id"])
    send(client, "task.execute", {"action": "start", "block_id": scheduled["id"]}, created["id"], 1)
    state = read(client)
    session = next(s for s in state["sessions"] if s["task_id"] == created["id"])
    before = session["scheduled_start"]
    assert before == state["blocks"][0]["starts_at"]
    send(
        client,
        "block.update",
        {"start": "2026-03-29T11:00", "end": "2026-03-29T12:00"},
        scheduled["id"],
        1,
    )
    after = next(s for s in read(client)["sessions"] if s["id"] == session["id"])
    assert after["scheduled_start"] == before and after["expected_minutes"] == 30


def test_subtasks_and_dependencies_cannot_create_a_combined_deadlock(signed_in):
    client = signed_in[0]
    parent, _ = task(client)
    child, body = task(client, parent_id=parent["id"])
    send(
        client, "task.update", {**body, "dependencies": [parent["id"]]}, child["id"], 1, status=422
    )
    row = client.get("/v1/application/tasks").json()["tasks"][0]
    assert (
        client.patch(
            f"/v1/application/tasks/{row['id']}", json={"done": False, "version": 99}
        ).status_code
        == 409
    )


def test_ten_thousand_synthetic_tasks_and_explicit_limit(signed_in):
    client, app, _ = signed_in
    with app.state.database.connect() as db:
        # Seed the load fixture separately; the actual API still has its 10s bound.
        db.execute("SET LOCAL statement_timeout='60s'")
        db.execute(
            "INSERT INTO app.tasks(id,title,objective,area) SELECT gen_random_uuid(),'Synthetic load '||n,'Preserve outcome '||n,'work' FROM generate_series(1,10000) n"
        )
    state = read(client)
    assert len(state["tasks"]) == 10000 and state["source"] == "postgresql"
    task(client)
    assert client.get(ROOT, params={"start": "2026-03-01", "end": "2026-03-02"}).status_code == 422


def test_task_schedule_summary_includes_blocks_outside_calendar_range(signed_in):
    client = signed_in[0]
    created, _ = task(client, due_date=None)
    far_future = (date.today() + timedelta(days=200)).isoformat()
    scheduled = block(client, created["id"], start=far_future + "T09:00", end=far_future + "T10:00")
    state = read(client, "2026-03-01", "2026-03-02")
    assert not state["blocks"]
    assert state["tasks"][0]["scheduled_block_count"] == 1
    assert state["tasks"][0]["next_scheduled_at"] is not None
    send(client, "block.remove", {}, scheduled["id"], 1)
    assert read(client)["tasks"][0]["scheduled_block_count"] == 0
