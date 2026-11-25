"""`yggdras brain tree|note|version|search` on a throwaway cluster and the invented brain
(brain_pg). `ada-lin` is the invented `sensitivity: high` note; `pottery-course` links to it."""

import json

import pytest

from brain_pg import Cluster, make_brain, pg_bin

psycopg = pytest.importorskip("psycopg")

from yggdras.data.brain_db import loader, migrate  # noqa: E402
from yggdras.interface import commands  # noqa: E402

SECRET_MARKS = ("ada-lin", "Ada Lin", "Ada teaches", "Ada runs")
VERBS = ("tree", "note", "version", "search")


@pytest.fixture(scope="module")
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
    with psycopg.connect(pg_url) as c:
        migrate.down(c, 0)
        migrate.up(c)
        loader.load(c, make_brain(tmp_path / "brain"))
    monkeypatch.setenv("BRAIN_DATABASE_URL", pg_url)
    return pg_url


def run(*argv):
    return commands.run_captured(["brain", *argv])


def version_of(url, slug):
    with psycopg.connect(url) as c:
        return c.execute("SELECT version FROM brain.notes WHERE slug=%s", (slug,)).fetchone()[0]


# ---------------------------------------------------------------- --help


@pytest.mark.parametrize("verb", VERBS)
def test_help_exits_0_for_every_verb(verb):
    code, out, err = run(verb, "--help")
    assert code == 0 and f"usage: yggdras brain {verb}" in out and err == ""


# ---------------------------------------------------------------- tree


def test_tree_lists_every_live_note_one_line_each(brain):
    code, out, err = run("tree")
    assert code == 0 and err == ""
    lines = [line.split("\t") for line in out.splitlines()]
    assert len(lines) == 12  # every live note, the restricted one masked
    assert ["04", "pottery-course", "Pottery Course", "project"] == lines[
        [r[1] for r in lines].index("pottery-course")
    ][:4]
    code, out, _ = run("tree", "--json")
    rows = json.loads(out)
    assert code == 0 and len(rows) == 12
    assert {"area": "04", "slug": "pottery-course", "type": "project"}.items() <= next(
        r for r in rows if r["slug"] == "pottery-course"
    ).items()


def test_tree_masks_the_restricted_note(brain):
    code, out, _ = run("tree")
    assert code == 0
    assert "-\tSensitive note\t-" in out
    assert "ada-lin" not in out and "Ada Lin" not in out


def test_tree_not_found_is_an_empty_brain(pg_url, monkeypatch):
    with psycopg.connect(pg_url) as c:
        migrate.down(c, 0)
        migrate.up(c)
    monkeypatch.setenv("BRAIN_DATABASE_URL", pg_url)
    assert run("tree") == (0, "", "")


# ---------------------------------------------------------------- note


def test_note_shows_the_note_links_and_masked_body(brain):
    code, out, err = run("note", "pottery-course")
    assert code == 0 and err == ""
    lines = out.splitlines()
    head = lines[0].split("\t")
    assert head[:5] == ["note", "pottery-course", "Pottery Course", "project", "04"]
    assert head[5] == str(version_of(brain, "pottery-course"))
    links = [line.split("\t") for line in lines if line.startswith("link\t")]
    assert ["pottery-course", "related_to", "glaze-chemistry"] in [
        [r[1], r[2], r[4]] for r in links
    ]
    assert lines[-1].startswith("body\t") and "[[sensitive-note]]" in lines[-1]
    data = json.loads(run("note", "pottery-course", "--json")[1])
    assert data["slug"] == "pottery-course" and "Saturdays" in data["body"]


def test_note_missing_exits_3(brain):
    code, out, err = run("note", "no-such-note")
    assert (code, out) == (3, "") and err.startswith("error\tnot_found\t")


def test_note_restricted_exits_4(brain):
    code, out, err = run("note", "ada-lin")
    assert (code, out) == (4, "") and err.startswith("error\tnot_allowed\t")
    assert "Ada Lin" not in err and "Ada teaches" not in err


def test_note_archived_is_not_found(brain):
    with psycopg.connect(brain) as c:
        c.execute("UPDATE brain.notes SET archived_at = now() WHERE slug='kiln-decision'")
    assert run("note", "kiln-decision")[0] == 3


# ---------------------------------------------------------------- version


def test_version_prints_the_token(brain):
    expected = version_of(brain, "glaze-chemistry")
    assert run("version", "glaze-chemistry") == (0, f"glaze-chemistry\t{expected}\n", "")
    code, out, _ = run("version", "glaze-chemistry", "--json")
    assert code == 0 and json.loads(out) == {"slug": "glaze-chemistry", "version": expected}


def test_version_missing_exits_3(brain):
    code, out, err = run("version", "no-such-note")
    assert (code, out) == (3, "") and err.startswith("error\tnot_found\t")


def test_version_restricted_exits_4(brain):
    code, out, err = run("version", "ada-lin", "--json")
    assert (code, out) == (4, "") and json.loads(err)["error"] == "not_allowed"


# ---------------------------------------------------------------- search


def test_search_finds_a_note(brain):
    code, out, err = run("search", "Saturdays")
    assert code == 0 and err == ""
    assert [line.split("\t")[0] for line in out.splitlines()] == ["pottery-course"]
    code, out, _ = run("search", "Saturdays", "--json")
    assert [r["slug"] for r in json.loads(out)] == ["pottery-course"]


def test_search_with_no_hit_prints_nothing(brain):
    assert run("search", "zebra") == (0, "", "")


def test_search_never_finds_the_restricted_note(brain):
    for q in ("teaches", "ada-lin", "Ada", "studio"):
        code, out, err = run("search", q)
        assert code == 0 and "ada-lin" not in out and "Ada" not in out, q


def test_search_empty_text_lists_every_visible_note_like_the_existing_search(brain):
    code, out, err = run("search", "  ")
    slugs = [line.split("\t")[0] for line in out.splitlines()]
    assert code == 0 and err == "" and slugs == sorted(slugs) and "pottery-course" in slugs
    assert "ada-lin" not in out


def test_search_keeps_web_search_syntax(brain):
    """The existing search is websearch_to_tsquery: phrases and -not work (a Phase C run had
    silently changed this; now a test holds it)."""
    assert run("search", '"runs on Saturdays"')[1].startswith("pottery-course\t")
    assert run("search", '"Saturdays runs on"')[1] == ""
    hits = run("search", "clay -handbook")[1]
    assert "clay-handbook" not in hits


# ---------------------------------------------------------------- leak test


def test_no_read_verb_leaks_the_restricted_note(brain):
    argvs = [["tree"], ["search", "pottery"], ["search", "Ada"], ["search", "teaches"]]
    for slug in ("ada-lin", "pottery-course", "wheel-throwing", "no-such-note"):
        argvs += [["note", slug], ["version", slug]]
    argvs += [argv + ["--json"] for argv in argvs]
    for argv in argvs:
        code, out, err = run(*argv)
        assert code in (0, 3, 4), argv
        text = out + err
        marks = SECRET_MARKS[1:] if argv[1:2] == ["ada-lin"] else SECRET_MARKS
        for mark in marks:  # the error may only echo the slug the caller typed
            assert mark not in text, (argv, mark)
        if argv[1:2] == ["ada-lin"]:
            assert out == "" and code == 4, argv
