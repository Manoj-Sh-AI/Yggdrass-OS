from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

from yggdress_app.database import Database

ROOT = "/v1/application/planning/commands"


def command(client, op, data, item=None, *, key=None, status=200):
    response = client.post(
        ROOT,
        json={
            "key": key or str(uuid4()),
            "op": op,
            "data": data,
            "id": item["id"] if item else None,
            "version": item["version"] if item else None,
        },
    )
    assert response.status_code == status, response.text
    return response.json()


def create(client, title):
    return command(
        client,
        "task.create",
        {"title": title, "objective": "Keep this exact outcome.", "due_date": "2030-01-02"},
    )


def test_focus_selection_without_a_clock_starts_none(signed_in):
    client, _, settings = signed_in
    task = create(client, "Synthetic chosen focus")
    result = command(client, "focus.switch", {}, task)
    assert not result["timer_running"] and result["version"] == task["version"]
    with Database(settings.database_url).connect() as db:
        assert db.execute("SELECT count(*) AS n FROM app.execution_sessions").fetchone()["n"] == 0
        assert (
            db.execute("SELECT state FROM app.tasks WHERE id=%s", (task["id"],)).fetchone()["state"]
            == "todo"
        )


def test_handoff_has_one_instant_one_clock_preserved_goals_and_replay(signed_in):
    client, _, settings = signed_in
    first, second = create(client, "Synthetic first focus"), create(client, "Synthetic next focus")
    first = command(client, "task.execute", {"action": "start"}, first)
    key = str(uuid4())
    body = {"from_task_id": first["id"], "from_version": first["version"]}
    moved = command(client, "focus.switch", body, second, key=key)
    assert moved["timer_running"]
    assert command(client, "focus.switch", body, second, key=key) == moved
    with Database(settings.database_url).connect() as db:
        sessions = db.execute(
            "SELECT * FROM app.execution_sessions ORDER BY started_at,id"
        ).fetchall()
        assert len(sessions) == 2 and sessions[0]["ended_at"] == sessions[1]["started_at"]
        assert sessions[0]["outcome"] == "paused" and sessions[1]["ended_at"] is None
        tasks = db.execute(
            "SELECT objective,due_date,state FROM app.tasks ORDER BY title"
        ).fetchall()
        assert {row["objective"] for row in tasks} == {"Keep this exact outcome."}
        assert {str(row["due_date"]) for row in tasks} == {"2030-01-02"}
        assert {row["state"] for row in tasks} == {"paused", "in_progress"}


def test_stale_or_blocked_handoff_never_stops_current_clock(signed_in):
    client, _, settings = signed_in
    first, second = create(client, "Synthetic active"), create(client, "Synthetic dependent")
    first = command(client, "task.execute", {"action": "start"}, first)
    command(
        client,
        "focus.switch",
        {"from_task_id": first["id"], "from_version": first["version"] - 1},
        second,
        status=409,
    )
    second = command(
        client,
        "task.update",
        {
            "title": "Synthetic dependent",
            "objective": "Keep this exact outcome.",
            "dependencies": [first["id"]],
        },
        second,
    )
    command(
        client,
        "focus.switch",
        {"from_task_id": first["id"], "from_version": first["version"]},
        second,
        status=409,
    )
    with Database(settings.database_url).connect() as db:
        sessions = db.execute("SELECT * FROM app.execution_sessions").fetchall()
        assert (
            len(sessions) == 1
            and sessions[0]["task_id"] == UUID(first["id"])
            and sessions[0]["ended_at"] is None
        )


def test_two_competing_handoffs_preserve_a_single_clock(signed_in):
    client, _, settings = signed_in
    first, second, third = (
        create(client, title) for title in ("Synthetic one", "Synthetic two", "Synthetic three")
    )
    first = command(client, "task.execute", {"action": "start"}, first)

    def switch(task):
        return client.post(
            ROOT,
            json={
                "key": str(uuid4()),
                "op": "focus.switch",
                "id": task["id"],
                "version": task["version"],
                "data": {"from_task_id": first["id"], "from_version": first["version"]},
            },
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(switch, (second, third))) == [200, 409]
    with Database(settings.database_url).connect() as db:
        assert (
            db.execute(
                "SELECT count(*) AS n FROM app.execution_sessions WHERE ended_at IS NULL"
            ).fetchone()["n"]
            == 1
        )
