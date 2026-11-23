"""Voice reminders: the 5-minute lead, background briefings, fast answers, confirm and
snooze. Invented records, a scripted model, a fake Lia and fake notes; nothing paid,
no speech. Lia is the only way into the notes; the notes fake only answers "is it sensitive"."""

import json
from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from test_call_service import calls  # noqa: F401 -- the shared signed-in call fixture

from yggdress_app.agent_models import ModelReply
from yggdress_app.call_briefs import (
    CHECKING,
    GOODBYE,
    HANDING_OVER,
    LEAD,
    Answerer,
    Brief,
    BriefPreparer,
    BriefStore,
    act,
    ask_lia,
    brief_key,
    end_summary,
    item_for,
    plain_end,
    plain_yes,
    ring_now,
)


class Notes:
    """Invented notes, read only to check whether a note Lia cites is sensitive."""

    def __init__(self):
        self.reads = []

    def get(self, owner, slug):
        self.reads.append(slug)
        return {"note": {"title": slug, "sensitive": slug == "private-health"}}

    def search(self, owner, query):
        raise AssertionError("reminders never search the notes; Lia is the only door")


POTTERY = "The studio moved to Hafenstrasse.[1]\n[1] [[pottery-course]] «moved»"


class Lia:
    """Invented Lia: records each question and returns a scripted answer (or error)."""

    def __init__(self, answer=POTTERY):
        self.answer, self.asked = answer, []

    def ask(self, question, context="", model="default"):
        self.asked.append({"question": question, "context": context})
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


class Model:
    def __init__(self, *replies):
        self.replies, self.seen = list(replies), []

    def complete(self, system, messages, tools):
        self.seen.append({"system": system, "messages": messages, "tools": tools})
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def text(value):
    return ModelReply([{"type": "text", "text": value}])


BRIEF = text(json.dumps({"summary": "Pottery starts at 10:30. Bring your apron.",
                         "context": "pottery-course: the studio moved to Hafenstrasse."}))  # fmt: skip


def event(client, clock, minutes, title="Invented pottery class"):
    made = client.post("/v1/application/planning/commands", json={
        "key": str(uuid4()), "op": "event.create",
        "data": {"title": title, "start": (clock[0] + timedelta(minutes=minutes)).isoformat(),
                 "end": (clock[0] + timedelta(minutes=minutes + 60)).isoformat(),
                 "timezone": "Europe/Berlin"}})  # fmt: skip
    assert made.status_code == 200, made.text
    return made.json()


def test_a_start_reminder_rings_five_minutes_early_and_ends_ring_on_time(calls):  # noqa: F811
    client, service, clock = calls
    event(client, clock, 30)
    service.tick()
    with service.database.connect() as db:
        rows = {r["kind"]: r["due_at"] for r in db.execute(
            "SELECT kind,due_at FROM app.call_schedules WHERE state='pending'").fetchall()}  # fmt: skip
    assert rows["event_start"] == clock[0] + timedelta(minutes=30) - LEAD
    assert rows["event_end"] == clock[0] + timedelta(minutes=90)


def test_lia_is_asked_ten_minutes_before_the_start_and_the_briefing_is_built_from_her(
    calls,  # noqa: F811
):
    client, service, clock = calls
    with service.database.connect() as db:
        db.execute("DELETE FROM app.call_briefs")
    event(client, clock, 40)  # starts at +40: Lia is asked from +30
    service.tick()
    model, lia = Model(BRIEF), Lia()
    preparer = BriefPreparer(
        service.database, lia, lambda name: model, notes=Notes(), now=service.now
    )
    clock[0] += timedelta(minutes=29)  # 11 minutes before the start: not yet
    service.tick()
    assert preparer.run_due() == 0 and lia.asked == []
    clock[0] += timedelta(minutes=1)  # 10 minutes before the start
    service.tick()
    assert preparer.run_due() == 1 and preparer.run_due() == 0  # once per reminder
    assert len(lia.asked) == 1 and "Invented pottery class" in lia.asked[0]["question"]
    assert "read-only" in lia.asked[0]["context"]
    with service.database.connect() as db:
        row = db.execute("SELECT * FROM app.call_briefs").fetchone()
    assert row["status"] == "ready" and row["summary"].startswith("Pottery starts")
    assert row["sources"] == ["pottery-course"] and row["failure"] == ""
    assert "Hafenstrasse" in json.dumps(model.seen[0]["messages"])


def test_a_sensitive_note_lia_cites_is_used_on_calls_by_manojs_decision(calls):  # noqa: F811
    client, service, clock = calls
    with service.database.connect() as db:
        db.execute("DELETE FROM app.call_briefs")
    event(client, clock, 10)
    service.tick()
    model = Model(BRIEF)
    lia = Lia("SECRET_FIXTURE diagnosis.[1]\n[1] [[private-health]] «x»")
    BriefPreparer(
        service.database, lia, lambda name: model, notes=Notes(), now=service.now
    ).run_due()
    with service.database.connect() as db:
        row = db.execute("SELECT * FROM app.call_briefs").fetchone()
    assert row["failure"] == "" and row["sources"] == ["private-health"]
    assert "SECRET_FIXTURE" in json.dumps(model.seen, default=str, ensure_ascii=False)


def test_when_lia_is_down_the_briefing_comes_from_the_item_alone(calls):  # noqa: F811
    client, service, clock = calls
    with service.database.connect() as db:
        db.execute("DELETE FROM app.call_briefs")
    event(client, clock, 10)
    service.tick()
    BriefPreparer(
        service.database,
        Lia(RuntimeError("down")),
        lambda name: Model(BRIEF),
        notes=Notes(),
        now=service.now,
    ).run_due()
    with service.database.connect() as db:
        row = db.execute("SELECT * FROM app.call_briefs").fetchone()
    assert row["status"] == "ready" and row["failure"] == "lia:RuntimeError"


def test_a_failed_briefing_still_gives_a_spoken_reminder(calls):  # noqa: F811
    client, service, clock = calls
    with service.database.connect() as db:
        db.execute("DELETE FROM app.call_briefs")
    event(client, clock, 10)
    service.tick()
    preparer = BriefPreparer(service.database, Lia(), lambda name: Model(ValueError("down")),
                             notes=Notes(), now=service.now)  # fmt: skip
    assert preparer.run_due() == 1
    with service.database.connect() as db:
        row = db.execute("SELECT * FROM app.call_briefs").fetchone()
    assert row["status"] == "failed" and row["failure"] == "ValueError"
    assert row["summary"].startswith("Reminder: Invented pottery class starts at")


def test_answers_come_from_the_briefing_and_asking_lia_says_one_moment_first(calls):  # noqa: F811
    client, service, clock = calls
    with service.database.connect() as db:
        db.execute("DELETE FROM app.call_briefs")
    event(client, clock, 10)
    service.tick()
    BriefPreparer(
        service.database, Lia(), lambda name: Model(BRIEF), notes=Notes(), now=service.now
    ).run_due()
    with service.database.connect() as db:
        schedule = db.execute(
            "SELECT * FROM app.call_schedules WHERE kind='event_start'").fetchone()  # fmt: skip
        brief = BriefStore().get(db, schedule["source_key"])
    lookup = ModelReply([{"type": "tool_use", "id": "t1", "name": "ask_lia",
                          "input": {"question": "teacher name"}}])  # fmt: skip
    model = Model(lookup, text("Your teacher is Ada."))
    spoken, asked = [], []
    answerer = Answerer(service.database, None, schedule, brief, model,
                        lookup=lambda q: asked.append(q) or {"answer": "Ada."},
                        actions=lambda name, values: {})  # fmt: skip
    assert "sir. Pottery starts at 10:30." in answerer.opening()
    assert answerer.reply([{"role": "user", "content": "Who teaches it?"}], spoken.append) == (
        "Your teacher is Ada."
    )
    assert spoken == [CHECKING] and asked == ["teacher name"]
    cached = model.seen[0]["system"][1]
    assert cached["cache_control"] == {"type": "ephemeral"} and "Hafenstrasse" in cached["text"]


def test_snooze_rings_again_with_the_same_briefing(calls):  # noqa: F811
    client, service, clock = calls
    event(client, clock, 10)
    service.tick()
    with service.database.connect() as db:
        schedule = db.execute(
            "SELECT * FROM app.call_schedules WHERE kind='event_start'").fetchone()  # fmt: skip
    out = act(service.database, None, schedule, "snooze", {"minutes": 10}, now=service.now)
    assert out == {"snoozed_minutes": 10}
    with service.database.connect() as db:
        snoozed = db.execute("SELECT * FROM app.call_schedules WHERE kind='snooze'").fetchone()
    assert snoozed["due_at"] == clock[0] + timedelta(minutes=10)
    assert brief_key(snoozed["source_key"]) == schedule["source_key"]
    with service.database.connect() as db:
        assert item_for(db, snoozed)["title"] == "Invented pottery class"


def test_yes_starts_the_routine_task_and_an_event_is_only_acknowledged(calls):  # noqa: F811
    client, service, clock = calls
    event(client, clock, 10)
    service.tick()
    with service.database.connect() as db:
        schedule = db.execute(
            "SELECT * FROM app.call_schedules WHERE kind='event_start'").fetchone()  # fmt: skip
    assert act(service.database, None, schedule, "confirm_start", {})["started"] is False
    routine = client.post("/v1/application/planning/commands", json={
        "key": str(uuid4()), "op": "routine.create",
        "data": {"title": "Invented stretch", "objective": "Take a pause",
                 "starts_on": "2030-04-10", "window_start": "12:30", "window_end": "12:50",
                 "timezone": "Europe/Berlin"}}).json()  # fmt: skip
    materialized = client.post("/v1/application/planning/commands", json={
        "key": str(uuid4()), "op": "ensure",
        "data": {"start": "2030-04-10", "end": "2030-04-10"}})  # fmt: skip
    assert materialized.status_code == 200, materialized.text
    service.tick()
    with service.database.connect() as db:
        rschedule = db.execute(
            "SELECT * FROM app.call_schedules WHERE kind='routine' AND state='pending'"
        ).fetchone()
    assert rschedule and str(rschedule["source_id"]) == routine["id"]
    assert act(service.database, None, rschedule, "confirm_start", {}) == {
        "confirmed": True,
        "started": True,
    }
    with service.database.connect() as db:
        task = db.execute("SELECT state FROM app.tasks WHERE template_id=%s",
                          (routine["id"],)).fetchone()  # fmt: skip
    assert task["state"] == "in_progress"


def test_the_manual_test_prepares_now_and_rings_on_the_next_sweep(calls):  # noqa: F811
    client, service, clock = calls
    event(client, clock, 120)
    brief = ring_now(
        service.database, Lia(), lambda name: Model(BRIEF), notes=Notes(), now=service.now
    )
    assert brief.status == "ready" and brief.title == "Invented pottery class"
    service.tick()
    with service.database.connect() as db:
        rung = db.execute(
            "SELECT s.source_key,c.state FROM app.call_schedules s JOIN app.calls c ON c.id=s.call_id "
            "WHERE s.reason='Test reminder'").fetchone()  # fmt: skip
        assert rung["state"] == "ringing"
        assert BriefStore().get(db, rung["source_key"]).summary.startswith("Pottery starts")


@pytest.mark.parametrize("key", ["auto:event_start:x:1", "snooze:ab12cd34:auto:event_start:x:1"])
def test_a_snooze_key_points_back_to_its_original_briefing(key):
    assert brief_key(key) == "auto:event_start:x:1"


def test_only_a_manual_test_rings_in_quiet_hours(calls):  # noqa: F811
    client, service, clock = calls
    clock[0] = clock[0].replace(hour=22, minute=30)  # 23:30 Berlin: quiet hours
    event(client, clock, 120)
    ring_now(service.database, Lia(), lambda name: Model(BRIEF), notes=Notes(), now=service.now)
    with service.database.connect() as db:
        db.execute(
            "INSERT INTO app.call_schedules(id,kind,due_at,reason) VALUES (%s,'one_off',%s,'Requested check-in')",
            (uuid4(), clock[0]),
        )
    service.tick()
    with service.database.connect() as db:
        states = {r["reason"]: r["state"] for r in db.execute(
            "SELECT reason,state FROM app.call_schedules WHERE kind='one_off'").fetchall()}  # fmt: skip
    assert states == {"Test reminder": "rung", "Requested check-in": "cancelled"}


@pytest.mark.parametrize("said", ["Yes", "yes.", "Yeah, sure!", "OK", "yes please", "Confirm"])
def test_a_plain_yes_confirms(said):
    assert plain_yes(said)


@pytest.mark.parametrize("said", ["No", "yes, but snooze it", "not yet", "yes?", "in a minute",
                                  "what is it about"])  # fmt: skip
def test_anything_else_is_not_a_yes(said):
    assert not plain_yes(said)


def test_yes_confirms_without_the_model_and_the_call_records_it(calls):  # noqa: F811
    from yggdress_app.call_briefs import Brief

    client, service, clock = calls
    event(client, clock, 10, title="Invented test reminder")
    service.tick()
    with service.database.connect() as db:
        schedule = db.execute(
            "SELECT * FROM app.call_schedules WHERE kind='event_start'").fetchone()  # fmt: skip
        call = service.create(db, direction="outbound")
    brief = Brief(schedule["source_key"], "Invented test reminder", schedule["due_at"], "ready",
                  summary="A test.")  # fmt: skip
    model = Model()  # any model call would fail: there are no scripted replies
    answerer = Answerer(service.database, call["id"], schedule, brief, model, lookup=lambda q: {},
                        actions=lambda name, values: act(service.database, call["id"], schedule,
                                                         name, values, now=service.now))  # fmt: skip
    said = answerer.reply([{"role": "user", "content": "Yes."}])
    assert said == "Confirmed. Invented test reminder is noted." and model.seen == []
    with service.database.connect() as db:
        summary = db.execute("SELECT summary FROM app.calls WHERE id=%s", (call["id"],)).fetchone()
    assert summary["summary"] == "Confirmed Invented test reminder at 12:00."


@pytest.mark.parametrize("said", ["Bye", "Goodbye!", "End the call", "Okay, thanks, bye.",
                                  "Please hang up now", "That will be all"])  # fmt: skip
def test_saying_goodbye_ends_the_call(said):
    assert plain_end(said)


@pytest.mark.parametrize("said", ["Yes", "Snooze it", "Who is the teacher?"])
def test_other_replies_do_not_end_the_call(said):
    assert not plain_end(said)


def test_goodbye_hangs_up_without_the_model_and_end_call_tool_works():
    from yggdress_app.call_briefs import Brief

    brief = Brief("k", "Invented", None, "ready", summary="A test.")
    model = Model()
    answerer = Answerer(None, None, None, brief, model, lambda q: {}, lambda n, v: {})
    assert answerer.reply([{"role": "user", "content": "Bye."}]) == GOODBYE
    assert answerer.wants_end and model.seen == []
    ending = ModelReply([{"type": "text", "text": "Of course, sir."},
                         {"type": "tool_use", "id": "t", "name": "end_call", "input": {}}])  # fmt: skip
    answerer = Answerer(None, None, None, brief, Model(ending), lambda q: {}, lambda n, v: {})
    assert answerer.reply([{"role": "user", "content": "I think we are done here"}]) == (
        "Of course, sir."
    )
    assert answerer.wants_end


def test_the_backup_lookup_asks_lia_read_only_and_speaks_without_footnotes():
    lia = Lia("Your teacher is Ada.[1]\n[1] [[pottery-course]] «Ada teaches»")
    result = ask_lia(lia, Notes(), "Invented pottery class", "Who teaches it?")
    assert result == {"answer": "Your teacher is Ada.[1]"}
    assert lia.asked[0]["question"] == "Who teaches it?"
    context = lia.asked[0]["context"]
    assert "Read-only" in context and "Invented pottery class" in context


def test_the_backup_lookup_speaks_sensitive_notes_and_survives_lia_failing():
    secret = Lia("SECRET_FIXTURE.[1]\n[1] [[private-health]] «x»")
    assert ask_lia(secret, Notes(), "t", "q") == {"answer": "SECRET_FIXTURE.[1]"}
    assert ask_lia(Lia(RuntimeError("down")), Notes(), "t", "q")["answer"] is None
    assert ask_lia(None, Notes(), "t", "q")["answer"] is None


class Yggdras:
    """Invented full Yggdras role: records requests, can hold one waiting change."""

    def __init__(self, waiting=False):
        self.requests, self.waiting = [], waiting

    def pending(self):
        return self.waiting

    def turn(self, text):
        self.requests.append(text)
        if self.waiting:
            self.waiting = False
            return "Done."
        self.waiting = True
        return "Move it to 15:00 today. Shall I?"


def test_calendar_and_reminder_requests_are_handed_to_yggdras_with_one_moment_first():
    handoff = ModelReply([{"type": "tool_use", "id": "t1", "name": "hand_to_yggdras",
                           "input": {"request": "move it to 3pm"}}])  # fmt: skip
    model, yggdras, spoken, actions = Model(handoff), Yggdras(), [], []
    answerer = Answerer(None, None, None, BriefStore_brief(), model, lookup=lambda q: {},
                        actions=lambda name, values: actions.append(name) or {},
                        yggdras=yggdras)  # fmt: skip
    reply = answerer.reply([{"role": "user", "content": "Can you move it to 3pm?"}], spoken.append)
    assert reply == "Move it to 15:00 today. Shall I?" and spoken == [HANDING_OVER]
    assert yggdras.requests == ["move it to 3pm"]
    # The next "yes" answers the waiting change, not the reminder's own confirm_start.
    assert answerer.reply([{"role": "user", "content": "yes"}]) == "Done."
    assert yggdras.requests[-1] == "yes" and actions == [] and len(model.seen) == 1


def BriefStore_brief():
    from datetime import UTC, datetime

    from yggdress_app.call_briefs import Brief

    return Brief("auto:x", "Invented pottery class", datetime(2030, 4, 10, tzinfo=UTC), "ready",
                 summary="Pottery starts at 10:30.")  # fmt: skip


# ------------------------------------------------------------------ edge cases (2026-11-20)


def schedules(service, kind=None):
    with service.database.connect() as db:
        return db.execute(
            "SELECT * FROM app.call_schedules"
            + (" WHERE kind=%s" if kind else "")
            + " ORDER BY due_at",
            (kind,) if kind else (),
        ).fetchall()


def test_a_reminder_due_during_a_call_is_announced_in_that_call_not_rung(calls):  # noqa: F811
    client, service, clock = calls
    talking = client.post("/v1/calls", json={"key": str(uuid4()), "device": "desktop"}).json()
    assert talking["state"] == "answered"
    event(client, clock, 5)  # its reminder is due now
    service.tick()
    start = schedules(service, "event_start")[0]
    assert start["state"] == "rung" and start["call_id"] == UUID(talking["id"])
    with service.database.connect() as db:
        assert db.execute("SELECT count(*) AS n FROM app.calls").fetchone()["n"] == 1
        schedule, _ = BriefStore().for_call(db, talking["id"])
    assert schedule["id"] == start["id"]  # the call's newest reminder is now in focus


def test_a_reminder_waits_while_another_call_is_still_ringing(calls):  # noqa: F811
    client, service, clock = calls
    with service.database.connect() as db:
        service.create(db, direction="outbound")
    event(client, clock, 5)
    service.tick()
    assert schedules(service, "event_start")[0]["state"] == "pending"


def test_a_reminder_that_could_not_ring_in_time_shows_as_a_missed_call(calls):  # noqa: F811
    client, service, clock = calls
    event(client, clock, 5, title="Invented dentist")
    event(client, clock, 5, title="Invented removed class")
    service.tick()  # rings the first; the second waits behind it
    with service.database.connect() as db:
        db.execute("UPDATE app.calls SET state='ended' WHERE state='ringing'")
        db.execute(
            "UPDATE app.calendar_events SET cancelled=true WHERE title='Invented removed class'"
        )
        # The laptop slept: the waiting reminder is now 10 minutes overdue.
        db.execute("UPDATE app.call_schedules SET state='pending',call_id=NULL WHERE state='rung'")
    clock[0] += timedelta(minutes=10)
    service.tick()
    with service.database.connect() as db:
        missed = db.execute("SELECT reason,state FROM app.calls WHERE state='missed'").fetchall()
        left = db.execute("SELECT count(*) AS n FROM app.call_schedules WHERE state='pending' "
                          "AND kind='event_start'").fetchone()["n"]  # fmt: skip
    assert [m["reason"] for m in missed] == ["Missed Reminder · Invented dentist"]
    assert left == 0  # nothing rings late, and a removed event is not reported


def test_the_latest_snooze_replaces_an_earlier_one(calls):  # noqa: F811
    client, service, clock = calls
    event(client, clock, 10)
    service.tick()
    start = schedules(service, "event_start")[0]
    act(service.database, None, start, "snooze", {"minutes": 10}, now=service.now)
    act(service.database, None, start, "snooze", {"minutes": 5}, now=service.now)
    pending = [r for r in schedules(service, "snooze") if r["state"] == "pending"]
    assert [r["due_at"] for r in pending] == [clock[0] + timedelta(minutes=5)]


def test_an_end_of_event_check_in_is_not_a_start_reminder_and_needs_no_lia(calls):  # noqa: F811
    client, service, clock = calls
    with service.database.connect() as db:
        db.execute("DELETE FROM app.call_briefs")
    event(client, clock, -55)  # started 55 min ago, ends in 5
    service.tick()
    lia = Lia()
    BriefPreparer(service.database, lia, lambda name: Model(BRIEF), now=service.now).run_due()
    assert lia.asked == []
    end = schedules(service, "event_end")[0]
    with service.database.connect() as db:
        item = item_for(db, end)
    assert end_summary(item) == "Invented pottery class is due to end at 12:05."
    answerer = Answerer(None, None, end, Brief("k", "t", end["due_at"], "failed",
                        summary=end_summary(item)), Model(), lookup=lambda q: {},
                        actions=lambda n, v: {})  # fmt: skip
    assert "mark it as started" not in answerer.opening()
    assert answerer.opening().endswith("Is there anything to note, change or plan next?")
    assert answerer.announcement().startswith("Pardon the interruption, sir. Invented pottery")


def test_a_failing_turn_is_spoken_as_an_apology_and_the_call_goes_on():
    pytest.importorskip("livekit.agents")
    from yggdress_app.livekit_adapter import TROUBLE, answer_turn

    class Broken:
        wants_end = False

        def reply(self, messages, say):
            raise RuntimeError("model down")

    class Owner:
        answerer, history, identifier = Broken(), [], None

        class runtime:
            @staticmethod
            def turn(*_):
                raise RuntimeError("Lia down")

    assert answer_turn(Owner(), "what's next?") == TROUBLE
    Owner.answerer = None

    class Database:
        def connect(self):
            raise RuntimeError("database down")

    Owner.runtime.database = Database()
    assert answer_turn(Owner(), "what's next?") == TROUBLE


def test_bye_on_a_call_you_started_is_flagged_for_the_event_loop_not_run_in_the_thread():
    pytest.importorskip("livekit.agents")
    from yggdress_app.livekit_adapter import answer_turn

    class Owner:
        answerer, history, identifier, wants_end = None, [], None, False

        @staticmethod
        def hang_up():
            raise AssertionError("hang_up must run on the event loop, not in the turn thread")

    owner = Owner()
    assert answer_turn(owner, "Okay, bye") == GOODBYE and owner.wants_end
