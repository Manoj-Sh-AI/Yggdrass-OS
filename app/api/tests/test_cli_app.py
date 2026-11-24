"""The app's agent commands (planning/cli-build-spec.md) on a throwaway database: notes,
links, changes and the planning writers. One note_ref is 'restricted' (secret-diary)."""

import copy
import json
from uuid import uuid4

import psycopg
import pytest
from notes_fixture import BODY, SyntheticBrain
from postgres_fixture import isolated_database

from yggdress_app.commands import planning as cli_planning
from yggdress_app.commands import run_captured

SECRET = ("secret-diary", "Secret Diary", "diary body")
EVENT = {"title": "Synthetic meeting", "start": "2030-01-02T10:00", "end": "2030-01-02T11:00"}
DATE_ITEM = {"title": "Synthetic trip", "starts_on": "2030-02-01", "ends_before": "2030-02-03"}
AVAILABLE = {"title": "Free morning", "start": "2030-01-03T08:00", "end": "2030-01-03T10:00"}


@pytest.fixture(scope="module")
def database():
    with isolated_database() as urls:
        with psycopg.connect(urls["admin"]) as db:
            for slug, title, sensitivity in (("sample", "Sample", "normal"),
                                             ("secret-diary", "Secret Diary", "restricted")):  # fmt: skip
                db.execute(
                    "INSERT INTO app.note_refs(external_id,observed_title,observed_revision,"
                    "sensitivity) VALUES (%s,%s,1,%s)",
                    (slug, title, sensitivity),
                )
        yield urls


@pytest.fixture(autouse=True)
def env(database, monkeypatch):
    monkeypatch.setenv("YGGDRESS_DATABASE_URL", database["runtime"])
    brain = SyntheticBrain()
    secret = copy.deepcopy(brain.notes["sample"])
    secret |= {"slug": "secret-diary", "title": "Secret Diary",
               "body": BODY.replace("slug: sample\nname: Sample",
                                    "slug: secret-diary\nname: Secret Diary\nsensitivity: high")
               + "- diary body (src: self, 2030-01-01)\n"}  # fmt: skip
    brain.notes["secret-diary"] = secret

    from yggdress_app.notes_proxy import NotesProxy

    monkeypatch.setattr(cli_planning, "notes_client", lambda: NotesProxy(http=brain))
    return database


def q(database, sql, args=()):
    with psycopg.connect(database["admin"]) as db:
        return db.execute(sql, args).fetchall()


def ref_id(database, slug):
    return str(q(database, "SELECT id FROM app.note_refs WHERE external_id=%s", (slug,))[0][0])


def ok(argv):
    code, out, err = run_captured(argv)
    assert (code, err) == (0, ""), (argv, err)
    return out


def create(group, data):
    cells = ok([group, "create", "--data", json.dumps(data)]).rstrip("\n").split("\t")
    assert cells[0] == "ok"
    return cells[1], cells[2]  # id, version


def task():
    return create("task", {"title": "Synthetic plan", "objective": "Keep it unchanged."})


def block(task_id):
    return create("block", {"task_id": task_id, "start": "2030-01-02T12:00",
                            "end": "2030-01-02T13:00"})  # fmt: skip


def snapshot(database):
    tables = ("tasks", "planning_goals", "projects", "execution_blocks", "calendar_events",
              "calendar_date_items", "availability_windows", "task_note_links",
              "event_note_links", "event_task_links")  # fmt: skip
    return {t: q(database, f"SELECT * FROM app.{t} ORDER BY id") for t in tables}


# ---------------------------------------------------------------- writers


def fresh(kind):
    """(argv prefix for the update-like verbs, id, version) of a new item of *kind*."""
    if kind in ("task", "goal", "project"):
        data = {"title": "A goal"} if kind != "task" else None
        return task() if kind == "task" else create(kind, data)
    if kind == "block":
        return block(task()[0])
    if kind == "event":
        return create("event", EVENT)
    if kind == "date-item":
        return create("date-item", DATE_ITEM)
    return create("availability", AVAILABLE)


# (group, verb, extra argv) for every writer of an existing item.
UPDATES = [
    ("task", "update", ["--set", "title=Renamed", "--set", "objective=Still there."]),
    ("task", "execute", ["--set", "action=start"]),
    ("goal", "update", ["--set", "title=Renamed goal"]),
    ("project", "update", ["--set", "title=Renamed project"]),
    ("block", "update", ["--set", "start=2030-01-02T14:00", "--set", "end=2030-01-02T15:00"]),
    ("block", "remove", []),
    ("block", "split", ["--set", "at=2030-01-02T12:30:00+01:00"]),
    ("event", "update", ["--data", json.dumps({**EVENT, "title": "Moved"})]),
    ("event", "remove", []),
    ("date-item", "update", ["--data", json.dumps({**DATE_ITEM, "title": "Moved"})]),
    ("date-item", "remove", []),
    ("availability", "update", ["--data", json.dumps({**AVAILABLE, "title": "Moved"})]),
    ("availability", "remove", []),
]
CREATES = {"task": {"title": "T", "objective": "O"}, "goal": {"title": "G"},
           "project": {"title": "P"}, "event": EVENT, "date-item": DATE_ITEM,
           "availability": AVAILABLE}  # fmt: skip
UPDATE_IDS = [f"{g}-{v}" for g, v, _ in UPDATES]


@pytest.mark.parametrize("group", sorted(CREATES))
def test_create_prints_ok_id_version_and_key(group):
    cells = ok([group, "create", "--data", json.dumps(CREATES[group])]).rstrip("\n").split("\t")
    assert cells[0] == "ok" and cells[2] == "1" and len(cells) == 4


def test_block_create():
    assert block(task()[0])[1] == "1"


def test_set_and_a_given_key_replay_safely(database):
    key = str(uuid4())
    argv = ["goal", "create", "--set", "title=Once", "--key", key]
    assert ok(argv) == ok(argv)
    assert q(database, "SELECT count(*) FROM app.planning_goals WHERE title='Once'")[0][0] == 1


@pytest.mark.parametrize(("group", "verb", "extra"), UPDATES, ids=UPDATE_IDS)
def test_each_update_writes(group, verb, extra):
    identifier, version = fresh(group)
    cells = ok([group, verb, identifier, "--version", version, *extra]).split("\t")
    assert cells[0] == "ok" and int(cells[2]) > int(version)


@pytest.mark.parametrize(("group", "verb", "extra"), UPDATES, ids=UPDATE_IDS)
def test_each_update_of_a_missing_item_exits_3(group, verb, extra):
    code, out, err = run_captured([group, verb, str(uuid4()), "--version", "1", *extra])
    assert (code, out) == (3, "") and err.startswith("error\tnot_found\t")


@pytest.mark.parametrize(("group", "verb", "extra"), UPDATES, ids=UPDATE_IDS)
def test_each_stale_update_exits_5_and_writes_nothing(database, group, verb, extra):
    identifier, version = fresh(group)
    title = "Fresh" if group != "task" else None
    bump = ["--set", f"title={title}"] if title else ["--set", "title=X", "--set", "objective=Y"]
    if group in ("event", "date-item", "availability"):
        data = {"event": EVENT, "date-item": DATE_ITEM, "availability": AVAILABLE}[group]
        bump = ["--data", json.dumps({**data, "title": "Bumped"})]
    if group == "block":
        bump = ["--set", "start=2030-01-02T16:00", "--set", "end=2030-01-02T17:00"]
    ok([group, "update", identifier, "--version", version, *bump])
    before = snapshot(database)
    code, out, err = run_captured([group, verb, identifier, "--version", version, *extra])
    assert (code, out) == (5, "") and err.startswith("error\tstale\t"), err
    assert snapshot(database) == before


def test_invalid_fields_exit_6():
    assert run_captured(["task", "create", "--set", "title=only"])[0] == 6
    assert run_captured(["goal", "create", "--data", "[1]"])[0] == 6


# ---------------------------------------------------------------- connections


@pytest.mark.parametrize("group", ["task", "event"])
def test_link_and_unlink_a_note(database, group):
    identifier, version = fresh(group)
    cells = ok([group, "link-note", identifier, "sample", "--version", version]).split("\t")
    assert cells[0] == "ok" and int(cells[2]) == int(version) + 1
    kind = group
    linked = ok(["notes", "linked", "--thing", f"{kind}:{identifier}"])
    assert "sample" in linked
    by_id = ref_id(database, "sample")
    cells = ok([group, "unlink-note", identifier, by_id, "--version", cells[2]]).split("\t")
    assert int(cells[2]) == int(version) + 2
    assert ok(["notes", "linked", "--thing", f"{kind}:{identifier}"]) == ""


@pytest.mark.parametrize("group", ["task", "event"])
@pytest.mark.parametrize("verb", ["link-note", "unlink-note"])
def test_a_missing_item_or_note_exits_3(group, verb):
    identifier, version = fresh(group)
    assert run_captured([group, verb, str(uuid4()), "sample", "--version", "1"])[0] == 3
    missing = "no-such-note" if verb == "unlink-note" else str(uuid4())
    assert run_captured([group, verb, identifier, missing, "--version", version])[0] == 3


@pytest.mark.parametrize("group", ["task", "event"])
@pytest.mark.parametrize("verb", ["link-note", "unlink-note"])
@pytest.mark.parametrize("by", ["slug", "id"])
def test_a_restricted_note_exits_4_and_writes_nothing(database, group, verb, by):
    identifier, version = fresh(group)
    before = snapshot(database)
    note = "secret-diary" if by == "slug" else ref_id(database, "secret-diary")
    code, out, err = run_captured([group, verb, identifier, note, "--version", version])
    if verb == "unlink-note" and by == "slug":
        assert code == 3  # a slug not shown in api.note_search is not found
    else:
        assert code == 4 and err.startswith("error\tnot_allowed\t")
    assert out == "" and "Secret" not in err and "diary body" not in err
    assert snapshot(database) == before


@pytest.mark.parametrize("verb", ["link-note", "unlink-note"])
def test_a_stale_note_link_exits_5(database, verb):
    identifier, version = task()
    current = ok(["task", "link-note", identifier, "sample", "--version", version]).split("\t")[2]
    if verb == "link-note":
        ok(["task", "unlink-note", identifier, "sample", "--version", current])
    before = snapshot(database)
    assert run_captured(["task", verb, identifier, "sample", "--version", version])[0] == 5
    assert snapshot(database) == before


def test_event_link_and_unlink_a_task(database):
    event_id, event_version = fresh("event")
    task_id, task_version = task()
    argv = ["event", "link-task", event_id, task_id, "--version", event_version,
            "--task-version", task_version]  # fmt: skip
    cells = ok(argv).split("\t")
    assert int(cells[2]) == int(event_version) + 1
    pair = "SELECT count(*) FROM app.event_task_links WHERE event_id=%s AND task_id=%s"
    assert q(database, pair, (event_id, task_id))[0][0] == 1
    task_now = str(int(task_version) + 1)
    # stale: the old event version
    before = snapshot(database)
    stale = ["event", "unlink-task", event_id, task_id, "--version", event_version,
             "--task-version", task_now]  # fmt: skip
    assert run_captured(stale)[0] == 5
    assert snapshot(database) == before
    ok(["event", "unlink-task", event_id, task_id, "--version", cells[2], "--task-version",
        task_now])  # fmt: skip
    missing = ["event", "link-task", event_id, str(uuid4()), "--version", "9",
               "--task-version", "1"]  # fmt: skip
    assert run_captured(missing)[0] in (3, 5)
    assert run_captured(["event", "link-task", str(uuid4()), task_id, "--version", "1",
                         "--task-version", "1"])[0] == 3  # fmt: skip


# ---------------------------------------------------------------- reads


def test_notes_find_and_refs(database):
    out = ok(["notes", "find", "sam"])
    assert out.split("\t")[1] == "sample"
    assert ok(["notes", "find", "zzz-nothing"]) == ""
    assert "sample" in ok(["notes", "refs"])
    assert ok(["notes", "refs", "--id", ref_id(database, "sample")]).split("\t")[1] == "sample"
    assert run_captured(["notes", "refs", "--id", str(uuid4())])[0] == 3
    assert run_captured(["notes", "refs", "--id", ref_id(database, "secret-diary")])[0] == 4
    assert run_captured(["notes", "find", "--json", "sample"])[1].startswith("[")


def test_notes_linked_by_note(database):
    identifier, version = task()
    ok(["task", "link-note", identifier, "sample", "--version", version])
    assert identifier in ok(["notes", "linked", "--note", ref_id(database, "sample")])
    assert run_captured(["notes", "linked", "--note", str(uuid4())])[0] == 3
    assert run_captured(["notes", "linked", "--note", ref_id(database, "secret-diary")])[0] == 4
    assert run_captured(["notes", "linked", "--thing", f"task:{uuid4()}"]) == (0, "", "")


def test_links_list(database):
    identifier, version = task()
    ok(["task", "link-note", identifier, "sample", "--version", version])
    assert "Sample" in ok(["links", "list", "--kind", "task", "--id", identifier])
    assert ok(["links", "list", "--kind", "task", "--id", str(uuid4())]) == ""
    assert run_captured(["links", "list", "--kind", "note", "--id", str(uuid4())])[0] == 3
    secret = ref_id(database, "secret-diary")
    assert run_captured(["links", "list", "--kind", "note", "--id", secret])[0] == 4


def test_changes_read_returns_only_the_view_columns():
    create("goal", {"title": "Watched"})
    rows = json.loads(ok(["changes", "read", "cli-test", "--limit", "1000", "--json"]))
    assert rows and set(rows[0]) == {"seq", "at", "kind", "subject_kind", "subject_key",
                                     "actor", "sensitivity"}  # fmt: skip
    assert ok(["changes", "read", "cli-test"]) == ""  # the cursor moved
    assert run_captured(["changes", "read", "BAD NAME"])[0] == 6


def test_no_read_verb_ever_shows_the_restricted_note(database):
    """The restricted note linked to a task and an event (written directly, as the
    connections router would), then every read verb run with and without --json."""
    task_id, _ = task()
    event_id, _ = fresh("event")
    secret = ref_id(database, "secret-diary")
    with psycopg.connect(database["admin"]) as db:
        db.execute("INSERT INTO app.task_note_links(task_id,note_ref_id,kind) VALUES (%s,%s,"
                   "'context')", (task_id, secret))  # fmt: skip
        db.execute("INSERT INTO app.event_note_links(event_id,note_ref_id,kind) VALUES (%s,%s,"
                   "'context')", (event_id, secret))  # fmt: skip
    reads = [
        ["notes", "find", "secret"], ["notes", "find", "diary"], ["notes", "find", "s"],
        ["notes", "refs"], ["notes", "refs", "--id", secret],
        ["notes", "linked", "--note", secret],
        ["notes", "linked", "--thing", f"task:{task_id}"],
        ["notes", "linked", "--thing", f"event:{event_id}"],
        ["links", "list", "--kind", "task", "--id", task_id],
        ["links", "list", "--kind", "event", "--id", event_id],
        ["links", "list", "--kind", "note", "--id", secret],
        ["changes", "read", "leak-test", "--limit", "1000"],
    ]  # fmt: skip
    for argv in reads:
        for extra in ([], ["--json"]):
            _, out, err = run_captured([*argv, *extra])
            for mark in SECRET:
                assert mark not in out + err, (argv, mark)
    assert "Sensitive note" in ok(["notes", "linked", "--thing", f"task:{task_id}"])


# ---------------------------------------------------------------- help

HELP = [
    ["notes", "find"], ["notes", "refs"], ["notes", "linked"], ["links", "list"],
    ["changes", "read"],
    *[[g, v] for g in ("task", "goal", "project", "block", "event", "date-item",
                       "availability") for v in ("create", "update")],
    ["task", "execute"], ["task", "link-note"], ["task", "unlink-note"],
    ["block", "remove"], ["block", "split"],
    ["event", "remove"], ["event", "link-note"], ["event", "unlink-note"],
    ["event", "link-task"], ["event", "unlink-task"],
    ["date-item", "remove"], ["availability", "remove"],
]  # fmt: skip


@pytest.mark.parametrize("argv", HELP, ids=[" ".join(a) for a in HELP])
def test_help_exits_0(argv):
    code, out, _ = run_captured([*argv, "--help"])
    assert code == 0 and "usage:" in out
