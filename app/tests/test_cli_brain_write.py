"""`yggdras brain <write verb>` (planning/cli-build-spec.md) on a throwaway cluster holding the
invented brain of brain_pg.py (ada-lin is high, so restricted). Each writer: success,
not-found, not-allowed and a stale --version that exits 5 and writes nothing."""

import uuid

import pytest

from brain_pg import Cluster, make_brain, note, pg_bin

psycopg = pytest.importorskip("psycopg")

from yggdras.data.brain_db import loader, migrate  # noqa: E402
from yggdras.interface import commands  # noqa: E402

FACT = "The course runs on Saturdays (src: self, 2030-01-05)"
WRITERS = ("add-note", "add-fact", "replace-fact", "remove-fact", "link", "unlink", "undo")


@pytest.fixture(scope="session")
def pg_url(tmp_path_factory):
    bin_dir = pg_bin()
    if bin_dir is None:
        pytest.skip("no PostgreSQL binaries (initdb) on this machine")
    cluster = Cluster(bin_dir, tmp_path_factory.mktemp("pg") / "data")
    url = cluster.start()
    yield url
    cluster.stop()


@pytest.fixture
def brain(pg_url, tmp_path, monkeypatch):
    """The invented brain loaded fresh, the CLI pointed at it, the brain on rows."""
    monkeypatch.setenv("YGGDRAS_ENV_FILE", str(tmp_path / "no.env"))
    monkeypatch.setenv("BRAIN_DATABASE_URL", pg_url)
    monkeypatch.setenv("YGGDRAS_BRAIN_SOURCE", "rows")
    monkeypatch.setenv("YGGDRAS_LOCAL_DATA", str(tmp_path / "local-data"))
    monkeypatch.setenv("YGGDRAS_BRAIN", str(tmp_path / "the-real-one"))
    with psycopg.connect(pg_url) as conn:
        migrate.down(conn, 0)
        migrate.up(conn)
        loader.load(conn, make_brain(tmp_path / "copy"))
    return pg_url


def q(url, sql, args=()):
    with psycopg.connect(url) as conn:
        return conn.execute(sql, args).fetchall()


def version(url, slug):
    return q(url, "SELECT version FROM brain.notes WHERE slug = %s", (slug,))[0][0]


def state(url, slug):
    return q(url, "SELECT n.version, b.body FROM brain.notes n JOIN brain.note_bodies b "
                  "ON b.slug = n.slug WHERE n.slug = %s", (slug,))[0]  # fmt: skip


def body(url, slug):
    return state(url, slug)[1]


def run(*argv):
    return commands.run_captured(["brain", *argv])


def ok(argv, undo=True):
    code, out, err = run(*argv)
    assert code == 0 and err == "", (argv, err)
    cells = out.rstrip("\n").split("\t")
    assert out.count("\n") == 1 and cells[0] == "ok"
    assert len(cells) == (4 if undo else 3)
    return cells


def fails(argv, code, kind):
    got, out, err = run(*argv)
    assert got == code and out == "" and err.startswith(f"error\t{kind}\t"), (argv, got, err)
    assert err.count("\n") == 1
    return err


def stale(url, slug, argv):
    """An old --version exits 5 and leaves the note as it was."""
    before = state(url, slug)
    fails([*argv, "--version", str(before[0] - 1)], 5, "stale")
    assert state(url, slug) == before


# ---------------------------------------------------------------- --help


@pytest.mark.parametrize("verb", WRITERS)
def test_every_write_verb_has_help(verb):
    code, out, err = run(verb, "--help")
    assert code == 0 and f"usage: yggdras brain {verb}" in out and err == ""


@pytest.mark.parametrize("argv", [
    ["add-fact", "pottery-course", "x"], ["replace-fact", "pottery-course", "--old", "a",
     "--new", "b"], ["remove-fact", "pottery-course", "x"],
    ["link", "pottery-course", "uses", "odd-idea"], ["unlink", "pottery-course", "uses", "x"],
])  # fmt: skip
def test_version_is_required(argv):
    fails(argv, 2, "usage")


# ---------------------------------------------------------------- add-note


NEW = note(
    "kiln-log",
    "Kiln Log",
    "topic",
    "08-rest-joy",
    folder="08-rest-joy",
    facts=["The first firing went well"],
    links=["related_to [[kiln-decision]]"],
)[1]


def test_add_note(brain, tmp_path):
    path = tmp_path / "new.md"
    path.write_text(NEW, encoding="utf-8")
    cells = ok(["add-note", "--file", str(path)])
    assert cells[1] == "kiln-log" and cells[2] == str(version(brain, "kiln-log"))
    uuid.UUID(cells[3])
    assert "The first firing went well" in body(brain, "kiln-log")


def test_add_note_missing_file_and_restricted_slug(brain, tmp_path):
    fails(["add-note", "--file", str(tmp_path / "nope.md")], 3, "not_found")
    path = tmp_path / "ada.md"
    path.write_text(NEW.replace("kiln-log", "ada-lin"), encoding="utf-8")
    before = state(brain, "ada-lin")
    err = fails(["add-note", "--file", str(path)], 4, "not_allowed")
    assert "Ada" not in err and state(brain, "ada-lin") == before


def test_add_note_that_exists_is_invalid(brain, tmp_path):
    path = tmp_path / "dup.md"
    path.write_text(NEW.replace("kiln-log", "odd-idea"), encoding="utf-8")
    fails(["add-note", "--file", str(path)], 6, "invalid")


# ---------------------------------------------------------------- add-fact


def test_add_fact(brain):
    v = version(brain, "pottery-course")
    cells = ok(["add-fact", "pottery-course", "Clay costs money", "--version", str(v)])
    assert cells[1] == "pottery-course" and int(cells[2]) == version(brain, "pottery-course") > v
    assert "Clay costs money" in body(brain, "pottery-course")


def test_add_fact_not_found_not_allowed_stale(brain):
    fails(["add-fact", "no-such-note", "x", "--version", "1"], 3, "not_found")
    before = state(brain, "ada-lin")
    err = fails(["add-fact", "ada-lin", "x", "--version", str(before[0])], 4, "not_allowed")
    assert "ada-lin" not in err and state(brain, "ada-lin") == before
    stale(brain, "pottery-course", ["add-fact", "pottery-course", "x"])


def test_add_fact_json(brain):
    import json

    v = version(brain, "odd-idea")
    code, out, _ = run("add-fact", "odd-idea", "A json fact", "--version", str(v), "--json")
    assert code == 0 and json.loads(out)["line"].startswith("A json fact")


# ---------------------------------------------------------------- replace-fact


def replace(v, *extra):
    new = "The course runs on Sundays (src: self, 2030-03-01)"
    return ["replace-fact", "pottery-course", "--old", FACT, "--new", new,
            "--version", str(v), *extra]  # fmt: skip


def test_replace_fact_preview_then_write(brain):
    before = state(brain, "pottery-course")
    code, out, _ = run(*replace(before[0], "--preview"))
    assert code == 0 and out.startswith("preview\tpottery-course\t")
    assert state(brain, "pottery-course") == before
    cells = ok(replace(before[0]))
    assert int(cells[2]) == version(brain, "pottery-course") > before[0]
    assert "runs on Sundays" in body(brain, "pottery-course")


def test_replace_fact_not_found_not_allowed_stale(brain):
    fails(["replace-fact", "no-such-note", "--old", "a", "--new", "b", "--version", "1"],
          3, "not_found")  # fmt: skip
    fails(["replace-fact", "pottery-course", "--old", "not a fact here", "--new", "b",
           "--version", str(version(brain, "pottery-course"))], 3, "not_found")  # fmt: skip
    before = state(brain, "ada-lin")
    fails(["replace-fact", "ada-lin", "--old", "Ada teaches pottery", "--new", "x",
           "--version", str(before[0])], 4, "not_allowed")  # fmt: skip
    assert state(brain, "ada-lin") == before
    stale(brain, "pottery-course", replace(0)[:-2])


# ---------------------------------------------------------------- remove-fact


def test_remove_fact_preview_then_write(brain):
    before = state(brain, "pottery-course")
    argv = ["remove-fact", "pottery-course", FACT, "--version", str(before[0])]
    code, out, _ = run(*argv, "--preview")
    assert code == 0 and out == f"preview\tpottery-course\t{FACT}\n"
    assert state(brain, "pottery-course") == before
    cells = ok(argv, undo=False)
    assert int(cells[2]) == version(brain, "pottery-course") > before[0]
    assert f"- {FACT}" not in body(brain, "pottery-course")


def test_remove_fact_not_found_not_allowed_stale(brain):
    fails(["remove-fact", "no-such-note", "x", "--version", "1"], 3, "not_found")
    before = state(brain, "ada-lin")
    fails(["remove-fact", "ada-lin", "Ada teaches pottery", "--version", str(before[0])],
          4, "not_allowed")  # fmt: skip
    assert state(brain, "ada-lin") == before
    stale(brain, "pottery-course", ["remove-fact", "pottery-course", FACT])


# ---------------------------------------------------------------- link and unlink


def test_link_preview_then_write(brain):
    before = state(brain, "odd-idea")
    argv = ["link", "odd-idea", "uses", "wheel-throwing", "--version", str(before[0])]
    code, out, _ = run(*argv, "--preview")
    assert code == 0 and out.startswith("preview\todd-idea\todd-idea uses wheel-throwing\t")
    assert state(brain, "odd-idea") == before
    cells = ok(argv)
    assert int(cells[2]) == version(brain, "odd-idea") > before[0]
    assert "uses [[wheel-throwing]]" in body(brain, "odd-idea")


def test_link_not_found_not_allowed_stale(brain):
    v = str(version(brain, "odd-idea"))
    fails(["link", "no-such-note", "uses", "odd-idea", "--version", "1"], 3, "not_found")
    fails(["link", "odd-idea", "uses", "no-such-note", "--version", v], 3, "not_found")
    before = state(brain, "odd-idea")
    err = fails(["link", "odd-idea", "knows", "ada-lin", "--version", v], 4, "not_allowed")
    assert "ada-lin" not in err and state(brain, "odd-idea") == before
    fails(["link", "ada-lin", "uses", "odd-idea", "--version", "1"], 4, "not_allowed")
    stale(brain, "odd-idea", ["link", "odd-idea", "uses", "wheel-throwing"])


def test_unlink_preview_then_write(brain):
    before = state(brain, "odd-idea")
    argv = ["unlink", "odd-idea", "related_to", "glaze-chemistry", "--version", str(before[0])]
    code, out, _ = run(*argv, "--preview")
    assert code == 0 and out == "preview\todd-idea\todd-idea related_to glaze-chemistry\n"
    assert state(brain, "odd-idea") == before
    cells = ok(argv, undo=False)
    assert int(cells[2]) == version(brain, "odd-idea") > before[0]
    assert "related_to [[glaze-chemistry]]" not in body(brain, "odd-idea")


def test_unlink_not_found_not_allowed_stale(brain):
    v = str(version(brain, "odd-idea"))
    fails(["unlink", "no-such-note", "uses", "odd-idea", "--version", "1"], 3, "not_found")
    fails(["unlink", "odd-idea", "uses", "wheel-throwing", "--version", v], 3, "not_found")
    before = state(brain, "pottery-course")
    fails(["unlink", "pottery-course", "created_by", "ada-lin", "--version", str(before[0])],
          4, "not_allowed")  # fmt: skip
    assert state(brain, "pottery-course") == before
    fails(["unlink", "ada-lin", "knows", "pottery-course", "--version", "1"], 4, "not_allowed")
    stale(brain, "odd-idea", ["unlink", "odd-idea", "related_to", "glaze-chemistry"])


# ---------------------------------------------------------------- undo


def test_undo_once(brain):
    v = version(brain, "odd-idea")
    undo_id = ok(["add-fact", "odd-idea", "Undo me", "--version", str(v)])[3]
    assert "Undo me" in body(brain, "odd-idea")
    code, out, err = run("undo", undo_id)
    assert code == 0 and out == f"ok\t{undo_id}\t-\n" and err == ""
    assert "Undo me" not in body(brain, "odd-idea")
    fails(["undo", undo_id], 6, "invalid")  # used already


def test_undo_not_found_and_permanent(brain):
    fails(["undo", str(uuid.uuid4())], 3, "not_found")
    fails(["undo", "not-a-uuid"], 3, "not_found")
    v = version(brain, "pottery-course")
    code, out, _ = run("remove-fact", "pottery-course", FACT, "--version", str(v), "--json")
    assert code == 0
    import json

    change_id = json.loads(out)["change_id"]
    fails(["undo", change_id], 6, "invalid")  # remove-fact is permanent


def test_writes_are_refused_while_the_brain_is_on_markdown(brain, monkeypatch):
    monkeypatch.setenv("YGGDRAS_BRAIN_SOURCE", "markdown")
    before = state(brain, "odd-idea")
    fails(["add-fact", "odd-idea", "x", "--version", str(before[0])], 6, "invalid")
    assert state(brain, "odd-idea") == before
