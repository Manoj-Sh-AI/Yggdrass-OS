"""Ported from the single-session run (#63), adapted to this run's output format.

`yggdras brain tree|note|version|search` (planning/cli-build-spec.md) on a throwaway
cluster and the invented brain, where `ada-lin` is the restricted (sensitivity: high) note."""

import json

import pytest

from brain_pg import Cluster, make_brain, pg_bin

psycopg = pytest.importorskip("psycopg")

from yggdras.data.brain_db import loader, migrate  # noqa: E402
from yggdras.interface.commands import run_captured  # noqa: E402

SECRET_MARKS = ("ada-lin", "Ada Lin", "Ada teaches", "Ada runs")
READS = (
    ["brain", "tree"],
    ["brain", "note", "pottery-course"],
    ["brain", "version", "pottery-course"],
    ["brain", "search", "pottery"],
    ["brain", "search", "ada"],
    ["brain", "search", "ada-lin"],
    ["brain", "search", "teaches"],
    ["brain", "note", "ada-lin"],
    ["brain", "version", "ada-lin"],
)


@pytest.fixture(scope="module")
def pg_url(tmp_path_factory):
    bin_dir = pg_bin()
    if bin_dir is None:
        pytest.skip("no PostgreSQL binaries (initdb) on this machine")
    cluster = Cluster(bin_dir, tmp_path_factory.mktemp("pg") / "data")
    url = cluster.start()
    with psycopg.connect(url) as conn:
        migrate.up(conn)
        loader.load(conn, make_brain(tmp_path_factory.mktemp("brain")))
    yield url
    cluster.stop()


@pytest.fixture(autouse=True)
def brain_url(pg_url, monkeypatch):
    monkeypatch.setenv("BRAIN_DATABASE_URL", pg_url)


def version_of(pg_url, slug):
    with psycopg.connect(pg_url) as conn:
        return conn.execute(
            "SELECT version FROM api.brain_notes WHERE slug=%s", (slug,)
        ).fetchone()[0]


# ---------------------------------------------------------------- success


def test_tree_lists_every_note_with_a_masked_restricted_row():
    code, out, err = run_captured(["brain", "tree"])
    assert (code, err) == (0, "")
    lines = out.splitlines()
    assert any("\tpottery-course\t" in line for line in lines)
    assert sum("Sensitive note" in line for line in lines) == 1
    assert all(
        len(line.split("\t")) == 7 for line in lines
    )  # area slug title type shelf parent version


def test_tree_json_is_one_document():
    code, out, _ = run_captured(["brain", "tree", "--json"])
    assert code == 0
    rows = json.loads(out)
    assert {"area", "slug", "title", "type", "version"} <= set(rows[0])
    masked = [r for r in rows if r["title"] == "Sensitive note"]
    assert len(masked) == 1 and masked[0]["slug"] is None and masked[0]["version"] is None


def test_note_prints_its_text_and_links(pg_url):
    code, out, err = run_captured(["brain", "note", "glaze-chemistry"])
    assert (code, err) == (0, "")
    first = out.splitlines()[0].split("\t")
    assert first[0:2] == ["note", "glaze-chemistry"]
    assert first[5] == str(version_of(pg_url, "glaze-chemistry"))
    assert "Glazes melt into glass" in out
    links = [line.split("\t") for line in out.splitlines() if line.startswith("link\t")]
    assert ["glaze-chemistry", "broader", "wheel-throwing"] in [[f[1], f[2], f[4]] for f in links]


def test_version_prints_the_token(pg_url):
    code, out, _ = run_captured(["brain", "version", "pottery-course"])
    assert code == 0
    assert out == f"pottery-course\t{version_of(pg_url, 'pottery-course')}\n"


def test_search_finds_a_note():
    code, out, _ = run_captured(["brain", "search", "glazes"])
    assert code == 0
    assert out.splitlines()[0].split("\t")[0] == "glaze-chemistry"


# ---------------------------------------------------------------- not found (3)


@pytest.mark.parametrize("verb", ["note", "version"])
def test_a_missing_slug_exits_3(verb):
    code, out, err = run_captured(["brain", verb, "no-such-note"])
    assert (code, out) == (3, "")
    assert err.startswith("error\tnot_found\t")


def test_tree_and_search_find_nothing_as_empty_output():
    code, out, err = run_captured(["brain", "search", "zzzznothing"])
    assert (code, out, err) == (0, "", "")


# ---------------------------------------------------------------- not allowed (4)


@pytest.mark.parametrize("verb", ["note", "version"])
def test_a_restricted_slug_exits_4(verb):
    code, out, err = run_captured(["brain", verb, "ada-lin"])
    assert (code, out) == (4, "")
    assert err.startswith("error\tnot_allowed\t")


def test_a_restricted_slug_with_json_is_a_json_error():
    code, _, err = run_captured(["brain", "note", "ada-lin", "--json"])
    assert code == 4
    assert json.loads(err)["error"] == "not_allowed"


@pytest.mark.parametrize("q", ["ada", "ada-lin", "Ada Lin", "teaches"])
def test_search_never_finds_the_restricted_note(q):
    code, out, _ = run_captured(["brain", "search", q])
    assert code == 0
    assert "ada-lin" not in out


# ---------------------------------------------------------------- leak and help


def test_no_read_verb_ever_shows_the_restricted_note():
    for argv in READS:
        for extra in ([], ["--json"]):
            _, out, err = run_captured([*argv, *extra])
            for mark in SECRET_MARKS:
                if argv[-1] == "ada-lin" and mark == "ada-lin":
                    continue  # the caller's own argument is not a leak; checked below
                assert mark not in out + err, (argv, mark)
            if argv[1] in ("note", "version") and argv[-1] == "ada-lin":
                assert out == "" and "ada-lin" not in err
            elif argv[-1] == "ada-lin":
                assert "ada-lin" not in out.lower() + err


@pytest.mark.parametrize("verb", ["tree", "note", "version", "search"])
def test_help_exits_0(verb):
    code, out, _ = run_captured(["brain", verb, "--help"])
    assert code == 0
    assert "usage:" in out
