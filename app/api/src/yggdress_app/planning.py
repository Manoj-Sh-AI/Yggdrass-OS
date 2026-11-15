"""Deterministic application planning service. No Brain or agent dependency."""

import hashlib
from collections import defaultdict, deque
from datetime import UTC, date, datetime, time, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from psycopg import sql
from psycopg.types.json import Jsonb
from pydantic import ValidationError

from .planning_models import (
    AcknowledgeInput,
    Command,
    DailyInput,
    DateRange,
    ExceptionInput,
    ExecutionInput,
    FocusSwitchInput,
    GroupInput,
    RoutineInput,
    SplitInput,
    TaskInput,
    TimeInput,
)

LOCK = 719218402


def wall_instant(value: datetime, timezone: str, fold: int = 0) -> datetime:
    """Reject nonexistent local times; explicit fold disambiguates autumn clocks."""
    if value.tzinfo is not None:
        return value.astimezone(UTC)
    zone = ZoneInfo(timezone)
    candidate = value.replace(tzinfo=zone, fold=fold).astimezone(UTC)
    if candidate.astimezone(zone).replace(tzinfo=None) != value:
        raise HTTPException(
            422, "This local time does not exist during the clock change. Choose another time."
        )
    return candidate


def day_bounds(start: date, end: date, timezone: str):
    zone = ZoneInfo(timezone)
    return (
        datetime.combine(start, time(), zone).astimezone(UTC),
        datetime.combine(end + timedelta(days=1), time(), zone).astimezone(UTC),
    )


def matches(template, day: date):
    if day < template["starts_on"] or (template["ends_on"] and day > template["ends_on"]):
        return False
    delta = (day - template["starts_on"]).days
    if template["frequency"] == "daily":
        return delta % template["interval_count"] == 0
    monday = template["starts_on"] - timedelta(days=template["starts_on"].weekday())
    return (
        day.weekday() in template["weekdays"]
        and ((day - monday).days // 7) % template["interval_count"] == 0
    )


def history(db, identifier, kind, detail=None):
    db.execute(
        "INSERT INTO app.task_history(task_id,kind,detail) VALUES (%s,%s,%s)",
        (identifier, kind, Jsonb(jsonable_encoder(detail or {}))),
    )


def insert(db, table, values):
    fields = list(values)
    return db.execute(
        sql.SQL("INSERT INTO app.{} ({}) VALUES ({}) RETURNING *").format(
            sql.Identifier(table),
            sql.SQL(",").join(map(sql.Identifier, fields)),
            sql.SQL(",").join(sql.Placeholder() for _ in fields),
        ),
        list(values.values()),
    ).fetchone()


def update(db, table, identifier, values):
    return db.execute(
        sql.SQL("UPDATE app.{} SET {},version=version+1 WHERE id=%s RETURNING *").format(
            sql.Identifier(table),
            sql.SQL(",").join(sql.SQL("{}=%s").format(sql.Identifier(field)) for field in values),
        ),
        [*values.values(), identifier],
    ).fetchone()


def locked(db, table, command):
    row = db.execute(
        sql.SQL("SELECT * FROM app.{} WHERE id=%s FOR UPDATE").format(sql.Identifier(table)),
        (command.id,),
    ).fetchone()
    if not row:
        raise HTTPException(404, "Planning item not found.")
    if command.version != row["version"]:
        raise HTTPException(
            409, "This item changed in another view. Refresh before applying your draft."
        )
    return row


def task_values(body):
    values = body.model_dump(exclude={"dependencies"})
    if body.deadline_at:
        values["due_date"] = body.deadline_at.astimezone(ZoneInfo(body.timezone)).date()
    return values


def relationships(db, identifier, body):
    # Parent completion requires its children, so both relationship kinds belong
    # in cycle detection. Iterative traversal avoids recursion limits on deep plans.
    edges = defaultdict(set)
    for task in db.execute("SELECT id,parent_id FROM app.tasks").fetchall():
        edges[task["id"]]
        parent = body.parent_id if task["id"] == identifier else task["parent_id"]
        if parent:
            edges[parent].add(task["id"])
    for edge in db.execute(
        "SELECT * FROM app.task_dependencies WHERE task_id<>%s", (identifier,)
    ).fetchall():
        edges[edge["task_id"]].add(edge["depends_on"])
    edges[identifier].update(body.dependencies)
    indegree = defaultdict(int, {node: 0 for node in edges})
    for targets in edges.values():
        for target in targets:
            indegree[target] += 1
    ready = deque(node for node, degree in indegree.items() if degree == 0)
    visited = 0
    while ready:
        node = ready.popleft()
        visited += 1
        for target in edges.get(node, ()):
            indegree[target] -= 1
            if indegree[target] == 0:
                ready.append(target)
    if visited != len(indegree):
        raise HTTPException(422, "Subtasks and dependencies cannot form a cycle.")
    db.execute("DELETE FROM app.task_dependencies WHERE task_id=%s", (identifier,))
    for dependency in set(body.dependencies):
        db.execute(
            "INSERT INTO app.task_dependencies(task_id,depends_on) VALUES (%s,%s)",
            (identifier, dependency),
        )


def materialize(db, body: DateRange):
    templates = db.execute(
        "SELECT * FROM app.routine_templates WHERE active ORDER BY id"
    ).fetchall()
    count = 0
    for template in templates:
        for offset in range((body.end - body.start).days + 1):
            day = body.start + timedelta(days=offset)
            if not matches(template, day):
                continue
            exception = db.execute(
                "SELECT 1 FROM app.routine_exceptions WHERE template_id=%s AND occurrence_date=%s",
                (template["id"], day),
            ).fetchone()
            if exception:
                continue
            identifier = uuid4()
            row = db.execute(
                "INSERT INTO app.tasks(id,title,description,objective,area,due_date,timezone,estimated_minutes,priority,goal_id,template_id,occurrence_date,routine_window_start,routine_window_end) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(template_id,occurrence_date) DO NOTHING RETURNING id",
                (
                    identifier,
                    template["title"],
                    template["description"],
                    template["objective"],
                    template["area"],
                    day,
                    template["timezone"],
                    template["expected_minutes"],
                    template["priority"],
                    template["goal_id"],
                    template["id"],
                    day,
                    template["window_start"],
                    template["window_end"],
                ),
            ).fetchone()
            if not row:
                continue
            naive = datetime.combine(day, template["window_start"])
            for gap in range(181):
                try:
                    start = wall_instant(naive + timedelta(minutes=gap), template["timezone"])
                    break
                except HTTPException:
                    if gap == 180:
                        raise
            insert(
                db,
                "execution_blocks",
                {
                    "id": uuid4(),
                    "task_id": identifier,
                    "starts_at": start,
                    "ends_at": start + timedelta(minutes=template["expected_minutes"]),
                    "timezone": template["timezone"],
                    "reason": "Routine preferred start; duration from your definition"
                    + ("; moved forward across the DST gap" if gap else ""),
                    "automatic": True,
                },
            )
            history(
                db,
                identifier,
                "routine.generated",
                {"template_id": template["id"], "date": day, "dst_adjusted_minutes": gap},
            )
            count += 1
    return {"generated": count}


def close_session(db, identifier, outcome):
    db.execute(
        "UPDATE app.execution_sessions SET ended_at=clock_timestamp(),outcome=%s WHERE task_id=%s AND ended_at IS NULL",
        (outcome, identifier),
    )


def execute_task(db, row, body: ExecutionInput):
    identifier, action = row["id"], body.action
    if action in ("start", "resume", "push"):
        if row["done"] or row["state"] == "skipped":
            raise HTTPException(409, "Reopen this task before starting it.")
        blocked = db.execute(
            "SELECT 1 FROM app.task_dependencies d JOIN app.tasks t ON t.id=d.depends_on WHERE d.task_id=%s AND NOT t.done LIMIT 1",
            (identifier,),
        ).fetchone()
        if blocked:
            raise HTTPException(409, "Complete this task’s dependencies before starting.")
        running = db.execute(
            "SELECT * FROM app.execution_sessions WHERE ended_at IS NULL"
        ).fetchone()
        if running and running["task_id"] != identifier:
            raise HTTPException(409, "Pause the other active task before starting this one.")
        selected_block = (
            db.execute(
                "SELECT * FROM app.execution_blocks WHERE id=%s AND task_id=%s AND NOT cancelled",
                (body.block_id, identifier),
            ).fetchone()
            if body.block_id
            else None
        )
        if body.block_id and not selected_block:
            raise HTTPException(422, "Choose an active block belonging to this task.")
        if not running:
            insert(
                db,
                "execution_sessions",
                {
                    "id": uuid4(),
                    "task_id": identifier,
                    "block_id": body.block_id,
                    "started_at": datetime.now(UTC),
                    "expected_minutes": row["estimated_minutes"],
                    "scheduled_start": selected_block["starts_at"] if selected_block else None,
                },
            )
        values = {"state": "in_progress"}
    elif action == "pause":
        if row["state"] != "in_progress":
            raise HTTPException(409, "Start the task before pausing it.")
        close_session(db, identifier, "paused")
        values = {"state": "paused"}
    elif action == "complete":
        if db.execute(
            "SELECT 1 FROM app.tasks WHERE parent_id=%s AND NOT done AND state<>'skipped' LIMIT 1",
            (identifier,),
        ).fetchone():
            raise HTTPException(409, "Complete the subtasks before finishing their parent.")
        if db.execute(
            "SELECT 1 FROM app.task_dependencies d JOIN app.tasks t ON t.id=d.depends_on WHERE d.task_id=%s AND NOT t.done LIMIT 1",
            (identifier,),
        ).fetchone():
            raise HTTPException(409, "Complete dependencies first.")
        close_session(db, identifier, "completed")
        values = {
            "state": "completed",
            "done": True,
            "progress": 100,
            "completed_at": datetime.now(UTC),
        }
    elif action == "reopen":
        close_session(db, identifier, "paused")
        values = {"state": "todo", "done": False, "progress": 0, "completed_at": None}
    else:
        if body.percent is None or row["done"]:
            raise HTTPException(422, "Enter progress from 0–100 for an unfinished task.")
        values = {"progress": body.percent}
    result = update(db, "tasks", identifier, {**values, "updated_at": datetime.now(UTC)})
    history(
        db, identifier, "execution." + action, {"percent": body.percent, "block_id": body.block_id}
    )
    return result


def time_values(body: TimeInput):
    start = wall_instant(body.start, body.timezone, body.fold)
    if (body.end is None) == (body.duration_minutes is None):
        raise HTTPException(422, "Provide either an end time or an elapsed duration.")
    end = (
        wall_instant(body.end, body.timezone, body.end_fold)
        if body.end
        else start + timedelta(minutes=body.duration_minutes)
    )
    if not timedelta(0) < end - start <= timedelta(days=7):
        raise HTTPException(422, "The end must follow the start, within seven days.")
    return {"starts_at": start, "ends_at": end, "timezone": body.timezone}


def command_result(db, command: Command):
    op, data = command.op, command.data
    if op == "focus.switch":
        body = FocusSwitchInput.model_validate(data)
        chosen = locked(db, "tasks", command)
        if chosen["done"] or chosen["state"] == "skipped":
            raise HTTPException(409, "Choose an unfinished task as your focus.")
        running = db.execute(
            "SELECT * FROM app.execution_sessions WHERE ended_at IS NULL FOR UPDATE"
        ).fetchone()
        if not running:
            if body.from_task_id is not None:
                raise HTTPException(409, "The focus timer changed. Refresh before switching.")
            return {"id": chosen["id"], "version": chosen["version"], "timer_running": False}
        if running["task_id"] == chosen["id"]:
            return {"id": chosen["id"], "version": chosen["version"], "timer_running": True}
        previous = db.execute(
            "SELECT * FROM app.tasks WHERE id=%s FOR UPDATE", (running["task_id"],)
        ).fetchone()
        if previous["done"] or previous["state"] != "in_progress":
            raise HTTPException(409, "The running task changed. Refresh before switching focus.")
        if body.from_task_id != previous["id"] or body.from_version != previous["version"]:
            raise HTTPException(409, "The focus timer changed. Refresh before switching.")
        if db.execute(
            "SELECT 1 FROM app.task_dependencies d JOIN app.tasks t ON t.id=d.depends_on WHERE d.task_id=%s AND NOT t.done LIMIT 1",
            (chosen["id"],),
        ).fetchone():
            raise HTTPException(409, "Complete this task’s dependencies before switching focus.")
        instant = db.execute("SELECT clock_timestamp() AS value").fetchone()["value"]
        db.execute(
            "UPDATE app.execution_sessions SET ended_at=%s,outcome='paused' WHERE id=%s",
            (instant, running["id"]),
        )
        paused = update(db, "tasks", previous["id"], {"state": "paused", "updated_at": instant})
        started = update(db, "tasks", chosen["id"], {"state": "in_progress", "updated_at": instant})
        insert(
            db,
            "execution_sessions",
            {
                "id": uuid4(),
                "task_id": chosen["id"],
                "started_at": instant,
                "expected_minutes": chosen["estimated_minutes"],
            },
        )
        history(db, previous["id"], "execution.focus_handoff", {"to_task_id": chosen["id"]})
        history(db, chosen["id"], "execution.focus_received", {"from_task_id": previous["id"]})
        return {
            "id": started["id"],
            "version": started["version"],
            "previous_id": paused["id"],
            "previous_version": paused["version"],
            "timer_running": True,
        }
    if op == "ensure":
        return materialize(db, DateRange.model_validate(data))
    if op.startswith("task."):
        if op == "task.create":
            body = TaskInput.model_validate(data)
            identifier = uuid4()
            row = insert(db, "tasks", {"id": identifier, **task_values(body)})
            relationships(db, identifier, body)
            history(
                db, identifier, op, {"objective": row["objective"], "due_date": row["due_date"]}
            )
        else:
            row = locked(db, "tasks", command)
            if op == "task.execute":
                row = execute_task(db, row, ExecutionInput.model_validate(data))
            else:
                body = TaskInput.model_validate(data)
                relationships(db, row["id"], body)
                previous = {
                    "objective": row["objective"],
                    "deadline_at": row["deadline_at"],
                    "due_date": row["due_date"],
                }
                row = update(
                    db,
                    "tasks",
                    row["id"],
                    {
                        **task_values(body),
                        "occurrence_edited": bool(row["template_id"]),
                        "updated_at": datetime.now(UTC),
                    },
                )
                history(db, row["id"], op, {"before": previous, "after": data})
        return {"id": row["id"], "version": row["version"]}
    if op.startswith(("goal.", "project.")):
        table = "planning_goals" if op.startswith("goal.") else "projects"
        body = GroupInput.model_validate(data)
        values = body.model_dump(exclude={"goal_id"} if table == "planning_goals" else set())
        if op.endswith("create"):
            row = insert(db, table, {"id": uuid4(), **values})
        else:
            row = update(db, table, locked(db, table, command)["id"], values)
        return {"id": row["id"], "version": row["version"]}
    if op.startswith("routine."):
        if op == "routine.skip":
            body = ExceptionInput.model_validate(data)
            template = locked(db, "routine_templates", command)
            row = db.execute(
                "SELECT * FROM app.tasks WHERE template_id=%s AND occurrence_date=%s",
                (template["id"], body.day),
            ).fetchone()
            if row and (
                row["done"]
                or db.execute(
                    "SELECT 1 FROM app.execution_sessions WHERE task_id=%s", (row["id"],)
                ).fetchone()
            ):
                raise HTTPException(
                    409, "An executed occurrence cannot be skipped. Its history is preserved."
                )
            db.execute(
                "INSERT INTO app.routine_exceptions VALUES (%s,%s) ON CONFLICT DO NOTHING",
                (template["id"], body.day),
            )
            if row:
                update(db, "tasks", row["id"], {"state": "skipped", "occurrence_edited": True})
                db.execute(
                    "UPDATE app.execution_blocks SET cancelled=true,version=version+1 WHERE task_id=%s",
                    (row["id"],),
                )
                history(db, row["id"], op, {"date": body.day})
            return {"id": template["id"]}
        body = RoutineInput.model_validate(data)
        if op == "routine.create":
            row = insert(db, "routine_templates", {"id": uuid4(), **body.model_dump()})
        else:
            current = locked(db, "routine_templates", command)
            row = update(db, "routine_templates", current["id"], body.model_dump())
            # Explicit future-series policy: history and edited/started occurrences survive.
            today = datetime.now(ZoneInfo(current["timezone"])).date()
            future = db.execute(
                "SELECT t.* FROM app.tasks t WHERE template_id=%s AND occurrence_date>%s AND NOT done AND NOT occurrence_edited AND NOT EXISTS(SELECT 1 FROM app.execution_sessions s WHERE s.task_id=t.id)",
                (row["id"], today),
            ).fetchall()
            for task in future:
                day = task["occurrence_date"]
                if db.execute(
                    "SELECT 1 FROM app.execution_blocks WHERE task_id=%s AND NOT automatic AND NOT cancelled",
                    (task["id"],),
                ).fetchone():
                    continue
                db.execute(
                    "UPDATE app.execution_blocks SET cancelled=true,version=version+1 WHERE task_id=%s AND automatic",
                    (task["id"],),
                )
                valid = row["active"] and matches(row, day)
                update(
                    db,
                    "tasks",
                    task["id"],
                    {
                        "title": row["title"],
                        "area": row["area"],
                        "timezone": row["timezone"],
                        "routine_window_start": row["window_start"],
                        "routine_window_end": row["window_end"],
                        "description": row["description"],
                        "objective": row["objective"],
                        "estimated_minutes": row["expected_minutes"],
                        "priority": row["priority"],
                        "goal_id": row["goal_id"],
                        "state": "todo" if valid else "skipped",
                    },
                )
                if valid:
                    start = datetime.combine(day, row["window_start"])
                    for gap in range(181):
                        try:
                            instant = wall_instant(start + timedelta(minutes=gap), row["timezone"])
                            break
                        except HTTPException:
                            if gap == 180:
                                raise
                    insert(
                        db,
                        "execution_blocks",
                        {
                            "id": uuid4(),
                            "task_id": task["id"],
                            "starts_at": instant,
                            "ends_at": instant + timedelta(minutes=row["expected_minutes"]),
                            "timezone": row["timezone"],
                            "reason": "Explicit future-series update",
                            "automatic": True,
                        },
                    )
                history(
                    db,
                    task["id"],
                    op,
                    {
                        "policy": "future untouched occurrences only",
                        "template_version": row["version"],
                    },
                )
        return {"id": row["id"], "version": row["version"]}
    if op.startswith(("block.", "event.")):
        block = op.startswith("block.")
        table = "execution_blocks" if block else "calendar_events"
        if op.endswith("create"):
            row = None
        else:
            row = locked(db, table, command)
            if row["cancelled"]:
                raise HTTPException(409, "This calendar item was removed. Refresh the view.")
        if op.endswith("remove"):
            result = update(db, table, row["id"], {"cancelled": True})
        elif op == "block.split":
            body = SplitInput.model_validate(data)
            if body.at.tzinfo is None or not row["starts_at"] < body.at < row["ends_at"]:
                raise HTTPException(
                    422, "Split point must be an offset-aware instant inside this block."
                )
            result = update(db, table, row["id"], {"ends_at": body.at, "automatic": False})
            insert(
                db,
                table,
                {
                    "id": uuid4(),
                    "task_id": row["task_id"],
                    "starts_at": body.at,
                    "ends_at": row["ends_at"],
                    "timezone": row["timezone"],
                    "reason": "Manually split from another execution block",
                },
            )
        else:
            body = TimeInput.model_validate(data)
            values = time_values(body)
            if block:
                identifier = row["task_id"] if row else body.task_id
                task = db.execute("SELECT * FROM app.tasks WHERE id=%s", (identifier,)).fetchone()
                if not task or task["done"] or task["state"] == "skipped":
                    raise HTTPException(422, "Choose an unfinished task to schedule.")
                values.update({"task_id": identifier, "reason": body.reason, "automatic": False})
            else:
                if not body.title:
                    raise HTTPException(422, "An event title is required.")
                values.update({"title": body.title, "description": body.description})
            result = (
                update(db, table, row["id"], values)
                if row
                else insert(db, table, {"id": uuid4(), **values})
            )
        if block:
            history(
                db,
                result["task_id"],
                op,
                {"block_id": result["id"], "before": row, "after": result},
            )
            db.execute(
                "UPDATE app.tasks SET occurrence_edited=true WHERE id=%s AND template_id IS NOT NULL",
                (result["task_id"],),
            )
        return {"id": result["id"], "version": result["version"]}
    if op == "daily.save":
        body = DailyInput.model_validate(data)
        previous = db.execute(
            "SELECT * FROM app.daily_plans WHERE day=%s AND timezone=%s", (body.day, body.timezone)
        ).fetchone()
        if (previous and command.version != previous["version"]) or (
            not previous and command.version is not None
        ):
            raise HTTPException(409, "This daily plan changed. Refresh before saving your draft.")
        db.execute(
            "INSERT INTO app.daily_plans(day,timezone,available_minutes,energy,focus,sleep,intention,reflection,confirmed_at,reviewed_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(day,timezone) DO UPDATE SET available_minutes=excluded.available_minutes,energy=excluded.energy,focus=excluded.focus,sleep=excluded.sleep,intention=excluded.intention,reflection=excluded.reflection,confirmed_at=COALESCE(excluded.confirmed_at,app.daily_plans.confirmed_at),reviewed_at=COALESCE(excluded.reviewed_at,app.daily_plans.reviewed_at),version=app.daily_plans.version+1",
            (
                body.day,
                body.timezone,
                body.available_minutes,
                body.energy,
                body.focus,
                body.sleep,
                body.intention,
                body.reflection,
                datetime.now(UTC) if body.confirm else None,
                datetime.now(UTC) if body.review else None,
            ),
        )
        return {"saved": True}
    body = AcknowledgeInput.model_validate(data)
    row = db.execute(
        "UPDATE app.reminder_requests SET acknowledged_at=COALESCE(acknowledged_at,now()) WHERE id=%s RETURNING id",
        (body.reminder_id,),
    ).fetchone()
    if not row:
        raise HTTPException(404, "Reminder not found.")
    return row


def refresh_reminders(db):
    # Queued readiness records, not outbound notification delivery.
    db.execute(
        "INSERT INTO app.reminder_requests(id,task_id,kind,eligible_at) SELECT 'due:'||id||':'||COALESCE(deadline_at::text,due_date::text),id,'deadline',COALESCE(deadline_at,(due_date+1)::timestamp AT TIME ZONE timezone) FROM app.tasks WHERE NOT done AND state<>'skipped' AND due_date IS NOT NULL ON CONFLICT DO NOTHING"
    )
    db.execute(
        "INSERT INTO app.reminder_requests(id,task_id,block_id,kind,eligible_at) SELECT 'start:'||b.id||':'||b.version,b.task_id,b.id,'start',b.starts_at FROM app.execution_blocks b JOIN app.tasks t ON t.id=b.task_id WHERE NOT b.cancelled AND NOT t.done AND t.state<>'skipped' ON CONFLICT DO NOTHING"
    )


def snapshot(db, body: DateRange):
    start, end = day_bounds(body.start, body.end, body.timezone)
    # Repeatable read at the route keeps this multi-table snapshot consistent.
    tasks = db.execute(
        "SELECT t.*, COALESCE((SELECT sum(EXTRACT(epoch FROM (COALESCE(s.ended_at,statement_timestamp())-s.started_at))) FROM app.execution_sessions s WHERE s.task_id=t.id),0)::float8 AS actual_seconds FROM app.tasks t ORDER BY created_at,id LIMIT 10001"
    ).fetchall()
    if len(tasks) > 10000:
        raise HTTPException(
            422,
            "This workspace exceeds the initial 10,000-task read limit. A paged API is required.",
        )
    schedule = {
        row["task_id"]: row
        for row in db.execute(
            "SELECT task_id,count(*)::integer AS scheduled_block_count,min(starts_at) FILTER (WHERE ends_at>statement_timestamp()) AS next_scheduled_at,max(ends_at) AS last_scheduled_end FROM app.execution_blocks WHERE NOT cancelled GROUP BY task_id"
        ).fetchall()
    }
    for task in tasks:
        task.update(
            {
                key: value
                for key, value in schedule.get(
                    task["id"],
                    {
                        "scheduled_block_count": 0,
                        "next_scheduled_at": None,
                        "last_scheduled_end": None,
                    },
                ).items()
                if key != "task_id"
            }
        )
    queries = {
        "goals": "SELECT * FROM app.planning_goals ORDER BY title,id",
        "projects": "SELECT * FROM app.projects ORDER BY title,id",
        "routines": "SELECT * FROM app.routine_templates ORDER BY title,id",
        "dependencies": "SELECT * FROM app.task_dependencies",
        "exceptions": "SELECT * FROM app.routine_exceptions",
    }
    result = {key: db.execute(query).fetchall() for key, query in queries.items()}
    result.update(
        {
            "tasks": tasks,
            "blocks": db.execute(
                "SELECT b.* FROM app.execution_blocks b WHERE NOT cancelled AND starts_at<%s AND ends_at>%s ORDER BY starts_at,id",
                (end, start),
            ).fetchall(),
            "events": db.execute(
                "SELECT * FROM app.calendar_events WHERE NOT cancelled AND starts_at<%s AND ends_at>%s ORDER BY starts_at,id",
                (end, start),
            ).fetchall(),
            "date_items": db.execute(
                "SELECT * FROM app.calendar_date_items WHERE NOT cancelled AND starts_on<=%s AND ends_before>%s ORDER BY starts_on,id LIMIT 1001",
                (body.end, body.start),
            ).fetchall(),
            "availability": db.execute(
                "SELECT * FROM app.availability_windows WHERE NOT cancelled AND starts_at<%s AND ends_at>%s ORDER BY starts_at,id LIMIT 1001",
                (end, start),
            ).fetchall(),
            "sessions": db.execute(
                "SELECT * FROM app.execution_sessions WHERE (started_at<%s AND ended_at>%s) OR ended_at IS NULL ORDER BY started_at,id",
                (end, start),
            ).fetchall(),
            "history": db.execute(
                "SELECT * FROM app.task_history ORDER BY id DESC LIMIT 1000"
            ).fetchall(),
            "plans": db.execute(
                "SELECT * FROM app.daily_plans WHERE day BETWEEN %s AND %s AND timezone=%s",
                (body.start, body.end, body.timezone),
            ).fetchall(),
            "reminders": db.execute(
                "SELECT r.* FROM app.reminder_requests r JOIN app.tasks t ON t.id=r.task_id LEFT JOIN app.execution_blocks b ON b.id=r.block_id WHERE NOT t.done AND t.state<>'skipped' AND r.acknowledged_at IS NULL AND r.eligible_at<=%s AND ((r.kind='start' AND NOT b.cancelled AND r.id='start:'||b.id||':'||b.version) OR (r.kind='deadline' AND r.id='due:'||t.id||':'||COALESCE(t.deadline_at::text,t.due_date::text))) ORDER BY r.eligible_at LIMIT 200",
                (end,),
            ).fetchall(),
            "server_now": datetime.now(UTC),
            "source": "postgresql",
            "range": body.model_dump(),
        }
    )
    if len(result["date_items"]) > 1000 or len(result["availability"]) > 1000:
        raise HTTPException(
            413,
            "This calendar range exceeds 1,000 date items or availability windows. Choose a narrower range.",
        )
    summaries = []
    now = datetime.now(UTC)
    for offset in range((body.end - body.start).days + 1):
        day = body.start + timedelta(days=offset)
        left, right = day_bounds(day, day, body.timezone)
        minutes = lambda a, b, left=left, right=right: max(
            0, (min(b, right) - max(a, left)).total_seconds() / 60
        )
        blocks = [b for b in result["blocks"] if b["starts_at"] < right and b["ends_at"] > left]
        events = [e for e in result["events"] if e["starts_at"] < right and e["ends_at"] > left]
        ids = {b["task_id"] for b in blocks}
        due = [t for t in tasks if t["due_date"] == day or t["id"] in ids]
        summaries.append(
            {
                "day": day,
                "scheduled_minutes": sum(minutes(b["starts_at"], b["ends_at"]) for b in blocks),
                "event_minutes": sum(minutes(e["starts_at"], e["ends_at"]) for e in events),
                "estimated_minutes": sum(
                    t["estimated_minutes"] for t in due if t["state"] != "skipped"
                ),
                "actual_minutes": sum(
                    minutes(s["started_at"], s["ended_at"] or now) for s in result["sessions"]
                ),
                "completed": sum(
                    1 for t in tasks if t["completed_at"] and left <= t["completed_at"] < right
                ),
                "unfinished": sum(1 for t in due if not t["done"] and t["state"] != "skipped"),
            }
        )
    result["summaries"] = summaries
    return result


def planning_router(database, session):
    router = APIRouter(prefix="/v1/application/planning", dependencies=[Depends(session)])

    @router.get("")
    def read(start: date, end: date, timezone: str = "Europe/Berlin"):
        try:
            body = DateRange(start=start, end=end, timezone=timezone)
        except ValidationError:
            raise HTTPException(
                422, "Choose a valid date range (at most 63 days) and named timezone."
            ) from None
        with database.connect() as db:
            db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            return snapshot(db, body)

    @router.post("/commands")
    def mutate(command: Command):
        fingerprint = hashlib.sha256(command.model_dump_json(exclude={"key"}).encode()).hexdigest()
        with database.connect() as db:
            db.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK,))
            receipt = db.execute(
                "SELECT * FROM app.planning_commands WHERE id=%s", (command.key,)
            ).fetchone()
            if receipt:
                if receipt["fingerprint"] != fingerprint:
                    raise HTTPException(
                        409, "This request key was already used for a different change."
                    )
                return receipt["result"]
            try:
                db.execute("SELECT set_config('yggdress.command_id',%s,true)", (str(command.key),))
                result = jsonable_encoder(command_result(db, command))
            except ValidationError as error:
                messages = "; ".join(e["msg"] for e in error.errors())
                raise HTTPException(422, messages) from None
            refresh_reminders(db)
            db.execute(
                "INSERT INTO app.planning_commands(id,fingerprint,result) VALUES (%s,%s,%s)",
                (command.key, fingerprint, Jsonb(result)),
            )
            return result

    return router
