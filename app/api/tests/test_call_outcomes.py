"""Voice calls v3: remove on a call, retries, outcomes, slot-end completion, the follow-up
on the next routine call, free slots and moving task blocks. Invented records, scripted
models; nothing paid, no speech."""

from datetime import date, datetime, timedelta
from uuid import uuid4

from test_call_briefs import BRIEF, Model, event, schedules
from test_call_service import calls  # noqa: F401 -- the shared signed-in call fixture

from yggdress_app import call_outcomes
from yggdress_app.agent_tools import Proposal
from yggdress_app.call_briefs import Answerer, Brief, act, item_for
from yggdress_app.free_slots import free_slots
from yggdress_app.voice_runtime import VoiceTools


def routine(client, title="Invented stretch", start="12:30", end="12:50", day="2030-04-10"):
    made = client.post("/v1/application/planning/commands", json={
        "key": str(uuid4()), "op": "routine.create",
        "data": {"title": title, "objective": "Take a pause", "starts_on": day,
                 "window_start": start, "window_end": end, "timezone": "Europe/Berlin"}})  # fmt: skip
    assert made.status_code == 200, made.text
    ensured = client.post("/v1/application/planning/commands", json={
        "key": str(uuid4()), "op": "ensure", "data": {"start": day, "end": day}})  # fmt: skip
    assert ensured.status_code == 200, ensured.text
    return made.json()


def outcomes(service):
    with service.database.connect() as db:
        return db.execute(
            "SELECT item_kind,outcome,decided_by FROM app.item_outcomes ORDER BY at, id"
        ).fetchall()


def ring_and_miss(service, clock):
    """The next due reminder rings, nobody answers for 46 s."""
    service.tick()
    clock[0] += timedelta(seconds=46)
    service.tick()


# ------------------------------------------------------------------ remove


def test_remove_on_a_call_is_read_back_and_applied_only_on_yes(calls):  # noqa: F811
    client, service, clock = calls
    made = event(client, clock, 5)
    service.tick()
    start = schedules(service, "event_start")[0]
    asked = Model(
        Model.__init__.__globals__["ModelReply"](
            [{"type": "tool_use", "id": "t1", "name": "remove_item", "input": {}}]
        )
    )
    brief = Brief(start["source_key"], "Invented pottery class", start["due_at"], "ready",
                  summary="Pottery starts soon.")  # fmt: skip
    answerer = Answerer(service.database, None, start, brief, asked, lookup=lambda q: {},
                        actions=lambda n, v: act(service.database, None, start, n, v,
                                                 now=service.now))  # fmt: skip
    assert answerer.reply([{"role": "user", "content": "Cancel it please"}]) == (
        "Remove Invented pottery class? Shall I?"
    )
    assert answerer.reply([{"role": "user", "content": "yes"}]) == (
        "Done. Invented pottery class is removed."
    )
    with service.database.connect() as db:
        row = db.execute(
            "SELECT cancelled FROM app.calendar_events WHERE id=%s", (made["id"],)
        ).fetchone()
    assert row["cancelled"] is True
    assert [(o["outcome"], o["decided_by"]) for o in outcomes(service)] == [("removed", "voice")]


def test_no_keeps_the_item(calls):  # noqa: F811
    client, service, clock = calls
    event(client, clock, 5)
    service.tick()
    start = schedules(service, "event_start")[0]
    brief = Brief(start["source_key"], "Invented pottery class", start["due_at"], "ready",
                  summary="Pottery starts soon.")  # fmt: skip
    answerer = Answerer(None, None, start, brief, Model(), lookup=lambda q: {},
                        actions=lambda n, v: {})  # fmt: skip
    answerer.asking = "remove"
    assert answerer.reply([{"role": "user", "content": "no"}]) == "Very well, I've kept it."


def test_a_routine_is_removed_for_that_day_only(calls):  # noqa: F811
    client, service, _clock = calls
    made = routine(client)
    service.tick()
    start = schedules(service, "routine")[0]
    assert act(service.database, None, start, "remove", {}, now=service.now) == {"removed": True}
    with service.database.connect() as db:
        template = db.execute(
            "SELECT active FROM app.routine_templates WHERE id=%s", (made["id"],)
        ).fetchone()
        task = db.execute(
            "SELECT state FROM app.tasks WHERE template_id=%s", (made["id"],)
        ).fetchone()
    assert template["active"] is True and task["state"] == "skipped"


# ------------------------------------------------------------------ retries


def test_a_missed_reminder_is_retried_at_5_and_10_minutes_then_an_event_counts_done(calls):  # noqa: F811
    client, service, clock = calls
    event(client, clock, 5)
    first_miss = clock[0] + timedelta(seconds=46)
    ring_and_miss(service, clock)
    retries = schedules(service, "retry")
    assert [r["due_at"] for r in retries] == [first_miss + timedelta(minutes=5)]
    clock[0] = retries[0]["due_at"]
    ring_and_miss(service, clock)
    retries = schedules(service, "retry")
    assert [r["due_at"] for r in retries][1] == first_miss + timedelta(minutes=10)
    clock[0] = retries[1]["due_at"]
    ring_and_miss(service, clock)
    assert len(schedules(service, "retry")) == 2  # no third retry
    assert [(o["item_kind"], o["outcome"], o["decided_by"]) for o in outcomes(service)] == [
        ("event", "completed", "after_retries")
    ]


def test_a_routine_left_unanswered_is_marked_not_answered(calls):  # noqa: F811
    client, service, clock = calls
    routine(client)
    service.tick()  # the routine's reminder is scheduled for 12:25
    for _ in range(3):  # the reminder and both retries go unanswered
        due = [r for r in schedules(service) if r["state"] == "pending"]
        clock[0] = max(clock[0], min(r["due_at"] for r in due))
        ring_and_miss(service, clock)
    assert [(o["item_kind"], o["outcome"]) for o in outcomes(service)] == [
        ("routine", "not_answered")
    ]


def test_answering_stops_the_retries(calls):  # noqa: F811
    client, service, clock = calls
    event(client, clock, 5)
    ring_and_miss(service, clock)
    retry = schedules(service, "retry")[0]
    act(service.database, None, retry, "snooze", {"minutes": 15}, now=service.now)
    assert schedules(service, "retry")[0]["state"] == "cancelled"


# ------------------------------------------------------------------ slot end


def test_an_event_counts_completed_when_its_slot_ends(calls):  # noqa: F811
    client, service, clock = calls
    event(client, clock, -50)  # 11:10-12:10 Berlin; now 12:00
    service.tick()
    assert outcomes(service) == []
    clock[0] += timedelta(minutes=11)
    service.tick()
    service.tick()  # recorded once
    assert [(o["outcome"], o["decided_by"]) for o in outcomes(service)] == [
        ("completed", "slot_end")
    ]


def test_a_started_routine_task_completes_when_its_planned_slot_ends(calls):  # noqa: F811
    client, service, clock = calls
    made = routine(client, start="12:30", end="12:50")
    service.tick()
    act(service.database, None, schedules(service, "routine")[0], "confirm_start", {},
        now=service.now)  # fmt: skip
    clock[0] = datetime(2030, 4, 10, 10, 59, tzinfo=clock[0].tzinfo)  # 12:59 Berlin
    service.tick()
    with service.database.connect() as db:  # its planned block runs to 13:00: not yet
        assert db.execute("SELECT state FROM app.tasks WHERE template_id=%s",
                          (made["id"],)).fetchone()["state"] == "in_progress"  # fmt: skip
    clock[0] = datetime(2030, 4, 10, 11, 1, tzinfo=clock[0].tzinfo)  # 13:01 Berlin
    service.tick()
    with service.database.connect() as db:
        task = db.execute(
            "SELECT state,done FROM app.tasks WHERE template_id=%s", (made["id"],)
        ).fetchone()
    assert task["state"] == "completed" and task["done"] is True
    assert ("routine", "completed", "slot_end") in [
        (o["item_kind"], o["outcome"], o["decided_by"]) for o in outcomes(service)
    ]


# ------------------------------------------------------------------ the next routine call


def test_the_next_routine_call_asks_about_last_time_and_advises_on_workload(calls):  # noqa: F811
    client, service, _clock = calls
    made = routine(client)
    service.tick()
    yesterday = date(2030, 4, 9)
    with service.database.connect() as db:
        call_outcomes.record(db, "routine", made["id"], yesterday, "not_answered", "after_retries")
        start = schedules(service, "routine")[0]
        missed = call_outcomes.follow_up(db, made["id"], date(2030, 4, 10))
    assert missed["day"] == yesterday and missed["title"] == "Invented stretch"
    brief = Brief(start["source_key"], "Invented stretch", start["due_at"], "ready",
                  summary="Stretch starts at 12:30.")  # fmt: skip
    answerer = Answerer(service.database, None, start, brief, Model(), lookup=lambda q: {},
                        actions=lambda n, v: act(service.database, None, start, n, v,
                                                 now=service.now),
                        follow_up=missed)  # fmt: skip
    assert "last time, on Tuesday, it went unanswered. Did you do it?" in answerer.opening()
    advice = answerer.reply([{"role": "user", "content": "no I didn't"}])
    assert advice.startswith("That leaves 30 minutes from Tuesday plus 30 today, 60 in all")
    assert advice.endswith("Shall I start today's now?")
    assert answerer.reply([{"role": "user", "content": "yes"}]) == (
        "Done. Invented stretch is marked as started."
    )
    assert ("routine", "not_done", "follow_up") in [
        (o["item_kind"], o["outcome"], o["decided_by"]) for o in outcomes(service)
    ]
    with service.database.connect() as db:
        assert call_outcomes.follow_up(db, made["id"], date(2030, 4, 10)) is None  # answered


def test_yes_about_last_time_marks_it_done_then_asks_about_today(calls):  # noqa: F811
    client, service, _clock = calls
    made = routine(client)
    service.tick()
    with service.database.connect() as db:
        call_outcomes.record(db, "routine", made["id"], date(2030, 4, 9), "not_answered",
                             "after_retries")  # fmt: skip
        missed = call_outcomes.follow_up(db, made["id"], date(2030, 4, 10))
    start = schedules(service, "routine")[0]
    brief = Brief(start["source_key"], "Invented stretch", start["due_at"], "ready",
                  summary="Stretch starts at 12:30.")  # fmt: skip
    answerer = Answerer(service.database, None, start, brief, Model(), lookup=lambda q: {},
                        actions=lambda n, v: act(service.database, None, start, n, v,
                                                 now=service.now),
                        follow_up=missed)  # fmt: skip
    assert answerer.reply([{"role": "user", "content": "yes"}]).startswith(
        "Great, I've marked it done. Stretch starts at 12:30. Shall I mark it as started"
    )


# ------------------------------------------------------------------ free slots and moving work


def test_free_slots_skip_events_task_blocks_and_buffers(calls):  # noqa: F811
    client, service, clock = calls
    event(client, clock, 60)  # 13:00-14:00 Berlin
    with service.database.connect() as db:
        slots = free_slots(db, date(2030, 4, 10), 1, 30, now=clock[0])
    assert slots[0]["start"].startswith("2030-04-10T12:00") and slots[0]["minutes"] == 50
    assert slots[1]["start"].startswith("2030-04-10T14:10")
    assert all(s["minutes"] >= 30 for s in slots)


def test_the_calendar_agent_reads_free_slots_and_task_blocks(calls):  # noqa: F811
    client, service, clock = calls
    event(client, clock, 60)
    read = VoiceTools(service.database).read(
        "calendar", {"start": "2030-04-10", "end": "2030-04-10", "free_minutes": 45}
    )
    assert read["free_slots"][0]["minutes"] >= 45 and "block" in read


def test_a_task_block_can_be_moved_by_a_spoken_yes(calls):  # noqa: F811
    client, service, _clock = calls
    task = client.post("/v1/application/planning/commands", json={
        "key": str(uuid4()), "op": "task.create",
        "data": {"title": "Invented report", "objective": "Finish it", "area": "work"}}).json()  # fmt: skip
    block = client.post("/v1/application/planning/commands", json={
        "key": str(uuid4()), "op": "block.create",
        "data": {"task_id": task["id"], "start": "2030-04-10T15:00:00+02:00",
                 "end": "2030-04-10T16:00:00+02:00", "timezone": "Europe/Berlin"}})  # fmt: skip
    assert block.status_code == 200, block.text
    moved = Proposal.model_validate({
        "operation": "block.update", "id": block.json()["id"], "version": block.json()["version"],
        "explanation": "Move the report to 17:00 for the emergency.",
        "data": {"start": "2030-04-10T17:00:00+02:00", "end": "2030-04-10T18:00:00+02:00",
                 "timezone": "Europe/Berlin"}})  # fmt: skip
    tools = VoiceTools(service.database)
    with service.database.connect() as db:
        tools.execute(moved, uuid4(), db)
        row = db.execute(
            "SELECT starts_at FROM app.execution_blocks WHERE id=%s", (block.json()["id"],)
        ).fetchone()
    assert row["starts_at"].isoformat().startswith("2030-04-10T15:00")  # stored in UTC


def test_an_end_check_in_and_a_retry_find_the_same_briefing(calls):  # noqa: F811
    client, service, clock = calls
    event(client, clock, 5)
    ring_and_miss(service, clock)
    retry = schedules(service, "retry")[0]
    with service.database.connect() as db:
        assert item_for(db, retry)["title"] == "Invented pottery class"
    assert BRIEF is not None
