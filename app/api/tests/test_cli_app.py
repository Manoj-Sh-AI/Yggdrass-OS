"""The app's agent commands (planning/cli-build-spec.md): notes, links, changes and planning
writes, in-process against a throwaway database (postgres_fixture.isolated_database, through
the session `postgres` fixture). Synthetic data only; one note_ref is restricted."""

import json
from uuid import uuid4

import pytest

from yggdress_app import commands
from yggdress_app.database import Database

SECRET = ("invented-zebra-secret", "Invented zebra diagnosis", "zebra", "rev-zebra")


def cli(*argv):
    return commands.run_captured([str(a) for a in argv])


def ok(*argv):
    code, out, err = cli(*argv)
    assert code == 0, (argv, err)
    fields = out.rstrip("\n").split("\t")
    assert fields[0] == "ok" and len(fields) == 4, out
    return fields[1], int(fields[2])


def fails(kind, *argv):
    code, out, err = cli(*argv)
    assert out == "" and err.startswith(f"error\t{kind}\t"), (argv, out, err)
    return code


def admin(postgres):
    return Database(postgres["admin"]).connect()


def row(postgres, table, identifier):
    with admin(postgres) as db:
        return db.execute(f"SELECT * FROM app.{table} WHERE id=%s", (identifier,)).fetchone()


@pytest.fixture
def world(setup, postgres, monkeypatch):
    """A normal and a restricted note_ref, each linked to one task and one event."""
    monkeypatch.setenv(commands.URL_VAR, postgres["runtime"])
    with admin(postgres) as db:
        refs = {}
        for slug, title, revision, sensitivity in (
            ("invented-public", "Invented public plan", "rev-public", "normal"),
            (SECRET[0], SECRET[1], SECRET[3], "restricted"),
        ):
            refs[sensitivity] = str(
                db.execute(
                    "INSERT INTO app.note_refs(external_id,observed_title,observed_revision,"
                    "sensitivity) VALUES (%s,%s,%s,%s) ON CONFLICT(source,external_id) DO UPDATE "
                    "SET observed_title=EXCLUDED.observed_title RETURNING id",
                    (slug, title, revision, sensitivity),
                ).fetchone()["id"]
            )
        task = str(
            db.execute(
                "INSERT INTO app.tasks(id,title,objective,area,due_date) VALUES "
                "(gen_random_uuid(),'Invented errand','Invented','work','2030-01-02') RETURNING id"
            ).fetchone()["id"]
        )
        event = str(
            db.execute(
                "INSERT INTO app.calendar_events(id,title,starts_at,ends_at,timezone) VALUES "
                "(gen_random_uuid(),'Invented meeting','2030-01-02T10:00Z','2030-01-02T11:00Z',"
                "'UTC') RETURNING id"
            ).fetchone()["id"]
        )
        for ref, kind in ((refs["normal"], "context"), (refs["restricted"], "source")):
            db.execute(
                "INSERT INTO app.task_note_links(task_id,note_ref_id,kind) VALUES (%s,%s,%s)",
                (task, ref, kind),
            )
            db.execute(
                "INSERT INTO app.event_note_links(event_id,note_ref_id,kind) VALUES (%s,%s,%s)",
                (event, ref, kind),
            )
    return {"public": refs["normal"], "secret": refs["restricted"], "task": task, "event": event}


# --- help -------------------------------------------------------------------------------


def verbs():
    parser = commands.build_parser()
    groups = next(a for a in parser._actions if a.dest == "group")
    for name, group in groups.choices.items():
        sub = next(a for a in group._actions if a.dest == "verb")
        for verb in sub.choices:
            yield name, verb


def test_every_verb_has_help():
    found = set(verbs())
    expected = {
        ("notes", "find"), ("notes", "refs"), ("notes", "linked"), ("links", "list"),
        ("changes", "read"),
        *(("task", v) for v in ("create", "update", "execute", "link-note", "unlink-note")),
        *((g, v) for g in ("goal", "project") for v in ("create", "update")),
        *(("block", v) for v in ("create", "update", "remove", "split")),
        *(("event", v) for v in ("create", "update", "remove", "link-note", "unlink-note",
                                 "link-task", "unlink-task")),
        *((g, v) for g in ("date-item", "availability") for v in ("create", "update", "remove")),
    }  # fmt: skip
    assert found == expected
    for group, verb in found:
        code, out, err = cli(group, verb, "--help")
        assert code == 0 and out.startswith("usage:") and err == "", (group, verb)


# --- reads ------------------------------------------------------------------------------


def test_notes_find(world):
    code, out, _ = cli("notes", "find", "public")
    assert code == 0 and out == f"{world['public']}\tinvented-public\tInvented public plan\n"
    assert json.loads(cli("notes", "find", "public", "--json")[1])[0]["slug"] == "invented-public"
    # nothing matches, and a restricted note cannot be found by any word: empty, exit 0
    for query in ("no-such-invented-note", "zebra", "diagnosis"):
        assert cli("notes", "find", query) == (0, "", "")


def test_notes_refs(world):
    code, out, _ = cli("notes", "refs")
    assert code == 0 and "invented-public" in out and "Sensitive note" in out
    code, out, _ = cli("notes", "refs", "--id", world["public"])
    assert code == 0 and out.split("\t")[:3] == [world["public"], "invented-public",
                                                 "Invented public plan"]  # fmt: skip
    assert fails("not_found", "notes", "refs", "--id", uuid4()) == 3
    assert fails("not_allowed", "notes", "refs", "--id", world["secret"]) == 4
    assert fails("invalid", "notes", "refs", "--id", "not-an-id") == 6


def test_notes_linked(world):
    code, out, _ = cli("notes", "linked", "--note", world["public"])
    assert code == 0 and {line.split("\t")[1] for line in out.splitlines()} == {
        world["task"],
        world["event"],
    }
    code, out, _ = cli("notes", "linked", "--thing", f"task:{world['task']}")
    lines = out.splitlines()
    assert code == 0 and len(lines) == 2
    assert any("invented-public" in line for line in lines)
    assert any("Sensitive note" in line and "restricted" in line for line in lines)
    assert fails("not_found", "notes", "linked", "--note", uuid4()) == 3
    assert commands.run_captured(["notes", "linked", "--thing", f"task:{uuid4()}"]) == (
        0,
        "",
        "",
    )  # empty list
    assert fails("not_allowed", "notes", "linked", "--note", world["secret"]) == 4
    assert fails("usage", "notes", "linked") == 2


def test_links_list(world):
    code, out, _ = cli("links", "list", "--kind", "task", "--id", world["task"])
    assert code == 0 and len(out.splitlines()) == 2 and "Sensitive note" in out
    code, out, _ = cli("links", "list", "--kind", "note", "--id", world["public"])
    assert code == 0 and len(out.splitlines()) == 2
    verb = out.split("\t")[4]
    code, out, _ = cli("links", "list", "--kind", "note", "--id", world["public"], "--verb", verb)
    assert code == 0 and out
    assert commands.run_captured(["links", "list", "--kind", "task", "--id", str(uuid4())]) == (
        0,
        "",
        "",
    )
    assert fails("not_found", "links", "list", "--kind", "note", "--id", uuid4()) == 3
    assert fails("not_allowed", "links", "list", "--kind", "note", "--id", world["secret"]) == 4


def test_changes_read(world):
    code, out, _ = cli("changes", "read", "invented-reader", "--json")
    events = json.loads(out)
    assert code == 0 and events
    assert set(events[0]) == {"seq", "at", "kind", "subject_kind", "subject_key", "actor",
                              "sensitivity"}  # fmt: skip
    assert any(e["subject_kind"] == "note_refs" for e in events)
    # the cursor moved: nothing new for this reader, and a plain line has seven fields
    assert cli("changes", "read", "invented-reader") == (0, "", "")
    code, out, _ = cli("changes", "read", "invented-other", "--limit", "1")
    assert code == 0 and len(out.splitlines()) == 1 and len(out.split("\t")) == 7
    assert fails("invalid", "changes", "read", "Not Allowed!") == 6
    assert fails("usage", "changes", "read", "invented-reader", "--limit", "0") == 2


def test_no_read_verb_leaks_the_restricted_note(world):
    reads = [
        ("notes", "find", "zebra"), ("notes", "find", "invented"), ("notes", "find", "diagnosis"),
        ("notes", "refs"), ("notes", "refs", "--id", world["secret"]),
        ("notes", "linked", "--note", world["secret"]),
        ("notes", "linked", "--thing", f"task:{world['task']}"),
        ("notes", "linked", "--thing", f"event:{world['event']}"),
        ("links", "list", "--kind", "task", "--id", world["task"]),
        ("links", "list", "--kind", "event", "--id", world["event"]),
        ("links", "list", "--kind", "note", "--id", world["secret"]),
        ("changes", "read", "invented-leak"),
    ]  # fmt: skip
    for argv in reads:
        for extra in ((), ("--json",)):
            code, out, err = cli(*argv, *extra)
            text = (out + err).lower()
            assert code in (0, 4), argv
            assert not any(word.lower() in text for word in SECRET), (argv, text)


# --- writes -----------------------------------------------------------------------------


def payloads(task):
    timed = {"start": "2030-01-02T10:00:00Z", "duration_minutes": 60, "timezone": "UTC"}
    return {
        "task": ("tasks", {"title": "Invented errand", "objective": "Invented", "timezone": "UTC"}),
        "goal": ("planning_goals", {"title": "Invented goal"}),
        "project": ("projects", {"title": "Invented project"}),
        "block": ("execution_blocks", {**timed, "task_id": task}),
        "event": ("calendar_events", {**timed, "title": "Invented meeting"}),
        "date-item": (
            "calendar_date_items",
            {"title": "Invented trip", "starts_on": "2030-01-02", "ends_before": "2030-01-05"},
        ),
        "availability": ("availability_windows", {**timed, "title": "Invented free time"}),
    }


@pytest.mark.parametrize(
    "group", ["task", "goal", "project", "block", "event", "date-item", "availability"]
)
def test_create_update_remove_with_stale_and_missing(world, postgres, group):
    table, data = payloads(world["task"])[group]
    identifier, version = ok(group, "create", "--data", json.dumps(data))
    assert row(postgres, table, identifier)["version"] == version

    changed = {**data, "description": "Invented change"}
    if group == "date-item":
        changed["ends_before"] = "2030-01-06"
    assert fails("not_found", group, "update", uuid4(), "--version", 1, "--data",
                 json.dumps(changed)) == 3  # fmt: skip
    _, newer = ok(group, "update", identifier, "--version", version, "--data", json.dumps(changed))
    assert newer == version + 1
    before = row(postgres, table, identifier)
    code = fails("stale", group, "update", identifier, "--version", version, "--data",
                 json.dumps(data))  # fmt: skip
    assert code == 5 and row(postgres, table, identifier) == before

    if group in ("block", "event", "date-item", "availability"):
        assert fails("stale", group, "remove", identifier, "--version", version) == 5
        assert row(postgres, table, identifier) == before
        assert fails("not_found", group, "remove", uuid4(), "--version", 1) == 3
        _, removed = ok(group, "remove", identifier, "--version", newer)
        assert removed == newer + 1 and row(postgres, table, identifier)["cancelled"]


def test_set_fields_and_a_retry_key_is_safe(world, postgres):
    key = str(uuid4())
    argv = ("goal", "create", "--set", "title=Invented retry", "--set", "description=Invented",
            "--key", key)  # fmt: skip
    first = cli(*argv)
    assert first[0] == 0 and first[1].rstrip("\n").split("\t")[3] == key
    assert cli(*argv) == first  # the same key replays the receipt, no second goal
    with admin(postgres) as db:
        count = db.execute(
            "SELECT count(*) AS n FROM app.planning_goals WHERE title='Invented retry'"
        ).fetchone()["n"]
    assert count == 1
    # a key without one is made and printed
    _, out, _ = cli("goal", "create", "--set", "title=Invented other")
    assert len(out.split("\t")[3].strip()) == 36
    assert fails("invalid", "goal", "create", "--set", "nope") == 6
    assert fails("invalid", "goal", "create", "--data", "[1]") == 6
    assert fails("invalid", "goal", "create", "--set", "title=") == 6


def test_task_execute(world, postgres):
    version = row(postgres, "tasks", world["task"])["version"]
    assert fails("not_found", "task", "execute", uuid4(), "--version", 1,
                 "--set", "action=start") == 3  # fmt: skip
    before = row(postgres, "tasks", world["task"])
    assert fails("stale", "task", "execute", world["task"], "--version", version + 7,
                 "--set", "action=start") == 5  # fmt: skip
    assert row(postgres, "tasks", world["task"]) == before
    _, newer = ok("task", "execute", world["task"], "--version", version, "--set", "action=start")
    assert newer == version + 1 and row(postgres, "tasks", world["task"])["state"] == "in_progress"


def test_block_split(world, postgres):
    _, data = payloads(world["task"])["block"]
    identifier, version = ok("block", "create", "--data", json.dumps(data))
    at = "2030-01-02T10:30:00Z"
    assert fails("not_found", "block", "split", uuid4(), "--version", 1, "--set", f"at={at}") == 3
    before = row(postgres, "execution_blocks", identifier)
    assert fails("stale", "block", "split", identifier, "--version", version + 1,
                 "--set", f"at={at}") == 5  # fmt: skip
    assert row(postgres, "execution_blocks", identifier) == before
    _, newer = ok("block", "split", identifier, "--version", version, "--set", f"at={at}")
    assert newer == version + 1
    assert fails("invalid", "block", "split", identifier, "--version", newer,
                 "--set", "at=2031-01-01T00:00:00Z") == 6  # fmt: skip


def note_links(postgres, table, field, identifier):
    with admin(postgres) as db:
        return db.execute(
            f"SELECT note_ref_id, kind FROM app.{table} WHERE {field}=%s ORDER BY 1, 2",
            (identifier,),
        ).fetchall()


@pytest.mark.parametrize(
    "group,table,link_table,field",
    [
        ("task", "tasks", "task_note_links", "task_id"),
        ("event", "calendar_events", "event_note_links", "event_id"),
    ],
)
def test_link_and_unlink_note(world, postgres, group, table, link_table, field):
    target = world[group]
    version = row(postgres, table, target)["version"]
    links = note_links(postgres, link_table, field, target)
    # a restricted note is refused before anything is written
    for verb in ("link-note", "unlink-note"):
        assert fails("not_allowed", group, verb, target, world["secret"], "--version",
                     version) == 4  # fmt: skip
        assert fails("not_found", group, verb, target, uuid4(), "--version", version) == 3
    assert fails("not_found", group, "link-note", uuid4(), world["public"], "--version", 1) == 3
    assert fails("stale", group, "link-note", target, world["public"], "--version", version + 3,
                 "--relation", "result") == 5  # fmt: skip
    assert note_links(postgres, link_table, field, target) == links
    assert row(postgres, table, target)["version"] == version

    _, linked = ok(group, "link-note", target, world["public"], "--version", version,
                   "--relation", "result")  # fmt: skip
    assert linked == version + 1
    assert len(note_links(postgres, link_table, field, target)) == len(links) + 1
    assert fails("stale", group, "unlink-note", target, world["public"], "--version", version,
                 "--relation", "result") == 5  # fmt: skip
    _, unlinked = ok(group, "unlink-note", target, world["public"], "--version", linked,
                     "--relation", "result")  # fmt: skip
    assert unlinked == linked + 1 and note_links(postgres, link_table, field, target) == links


def test_event_link_and_unlink_task(world, postgres):
    event, task = world["event"], world["task"]
    ev, tv = (
        row(postgres, "calendar_events", event)["version"],
        row(postgres, "tasks", task)["version"],
    )

    def task_links():
        with admin(postgres) as db:
            return db.execute(
                "SELECT task_id FROM app.event_task_links WHERE event_id=%s", (event,)
            ).fetchall()

    assert fails("not_found", "event", "link-task", event, uuid4(), "--version", ev,
                 "--task-version", 1) == 3  # fmt: skip
    assert fails("stale", "event", "link-task", event, task, "--version", ev,
                 "--task-version", tv + 1) == 5  # fmt: skip
    assert task_links() == []
    _, linked = ok("event", "link-task", event, task, "--version", ev, "--task-version", tv)
    assert linked == ev + 1 and len(task_links()) == 1
    assert fails("stale", "event", "unlink-task", event, task, "--version", ev,
                 "--task-version", tv + 1) == 5  # fmt: skip
    _, unlinked = ok("event", "unlink-task", event, task, "--version", linked,
                     "--task-version", tv + 1)  # fmt: skip
    assert unlinked == linked + 1 and task_links() == []
