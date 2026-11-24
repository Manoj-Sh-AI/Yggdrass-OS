"""`yggdras brain add-note|add-fact|replace-fact|remove-fact|link|unlink|undo`
(planning/cli-build-spec.md) on a throwaway cluster and the invented brain. `ada-lin` is the
restricted note. Writes go through BrainWrites and a RowStore, as start_api builds them."""

import pytest

from brain_pg import Cluster, make_brain, note, pg_bin

psycopg = pytest.importorskip("psycopg")

from yggdras.data.brain_db import loader, migrate  # noqa: E402
from yggdras.interface.commands import run_captured  # noqa: E402

FACT = "The course runs on Saturdays"
NEW = "The course runs on Sundays (src: self, 2030-03-01)"
TABLES = ("notes", "note_bodies", "relationships", "undo")


@pytest.fixture(scope="module")
def pg_url(tmp_path_factory):
    bin_dir = pg_bin()
    if bin_dir is None:
        pytest.skip("no PostgreSQL binaries (initdb) on this machine")
    cluster = Cluster(bin_dir, tmp_path_factory.mktemp("pg") / "data")
    url = cluster.start()
    yield url
    cluster.stop()


@pytest.fixture(autouse=True)
def url(pg_url, tmp_path, monkeypatch):
    """A fresh invented brain on rows; nothing outside tmp_path is touched."""
    monkeypatch.setenv("BRAIN_DATABASE_URL", pg_url)
    monkeypatch.setenv("YGGDRAS_BRAIN_SOURCE", "rows")
    monkeypatch.setenv("YGGDRAS_BRAIN", str(tmp_path / "the-real-one"))
    monkeypatch.setenv("YGGDRAS_LOCAL_DATA", str(tmp_path / "local-data"))
    with psycopg.connect(pg_url) as conn:
        migrate.down(conn, 0)
        migrate.up(conn)
        loader.load(conn, make_brain(tmp_path / "copy"))
    return pg_url


def q(url, sql, args=()):
    with psycopg.connect(url) as conn:
        return conn.execute(sql, args).fetchall()


def dump(url):
    return {t: q(url, f"SELECT * FROM brain.{t} ORDER BY 1") for t in TABLES}


def version(url, slug):
    return q(url, "SELECT version FROM brain.notes WHERE slug = %s", (slug,))[0][0]


def body(url, slug):
    return q(url, "SELECT body FROM brain.note_bodies WHERE slug = %s", (slug,))[0][0]


def v(url, slug):
    return ["--version", str(version(url, slug))]


# Every writer that takes a slug: argv after the slug (the version is added per test).
WRITERS = {
    "add-fact": lambda s: ["brain", "add-fact", s, "A new invented fact"],
    "replace-fact": lambda s: ["brain", "replace-fact", s, "--old", FACT, "--new", NEW],
    "remove-fact": lambda s: ["brain", "remove-fact", s, FACT],
    "link": lambda s: ["brain", "link", s, "related_to", "odd-idea"],
    "unlink": lambda s: ["brain", "unlink", s, "uses", "wheel-throwing"],
}


def new_note(tmp_path, slug="tea-ritual"):
    path = tmp_path / f"{slug}.md"
    _, text = note(slug, "Tea Ritual", "topic", "08-rest-joy", folder="08-rest-joy",
                   facts=["Tea at four"])  # fmt: skip
    path.write_text(text, encoding="utf-8")
    return path


# ---------------------------------------------------------------- success


@pytest.mark.parametrize("verb", sorted(WRITERS))
def test_each_writer_writes_and_prints_ok(url, verb):
    before = version(url, "pottery-course")
    code, out, err = run_captured([*WRITERS[verb]("pottery-course"), *v(url, "pottery-course")])
    assert (code, err) == (0, ""), err
    cells = out.rstrip("\n").split("\t")
    assert cells[:3] == ["ok", "pottery-course", str(version(url, "pottery-course"))]
    assert version(url, "pottery-course") != before
    assert len(cells) == (4 if verb in ("add-fact", "replace-fact", "link") else 3)


def test_add_fact_lands_in_the_text(url):
    run_captured([*WRITERS["add-fact"]("pottery-course"), *v(url, "pottery-course")])
    assert "A new invented fact" in body(url, "pottery-course")


@pytest.mark.parametrize("verb", ["replace-fact", "remove-fact", "link", "unlink"])
def test_preview_writes_nothing(url, verb):
    before = dump(url)
    argv = [*WRITERS[verb]("pottery-course"), *v(url, "pottery-course"), "--preview"]
    code, out, _ = run_captured(argv)
    assert code == 0 and out.startswith("preview\tpottery-course\t")
    assert dump(url) == before


def test_add_note_then_undo(url, tmp_path):
    code, out, err = run_captured(["brain", "add-note", "--file", str(new_note(tmp_path))])
    assert (code, err) == (0, ""), err
    ok, slug, ver, undo_id = out.rstrip("\n").split("\t")
    assert (ok, slug, ver) == ("ok", "tea-ritual", str(version(url, "tea-ritual")))
    code, out, _ = run_captured(["brain", "undo", undo_id])
    assert code == 0 and out.startswith(f"ok\t{undo_id}\tadd-note\t")
    assert q(url, "SELECT count(*) FROM brain.notes WHERE slug='tea-ritual' "
                  "AND archived_at IS NULL")[0][0] == 0  # fmt: skip


# ---------------------------------------------------------------- not found (3)


@pytest.mark.parametrize("verb", sorted(WRITERS))
def test_a_missing_note_exits_3(url, verb):
    before = dump(url)
    code, out, err = run_captured([*WRITERS[verb]("no-such-note"), "--version", "1"])
    assert (code, out) == (3, "") and err.startswith("error\tnot_found\t")
    assert dump(url) == before


def test_a_missing_link_target_exits_3(url):
    argv = ["brain", "link", "pottery-course", "related_to", "no-such-note"]
    code, _, _ = run_captured([*argv, *v(url, "pottery-course")])
    assert code == 3


def test_undo_of_an_unknown_id_exits_3():
    code, _, err = run_captured(["brain", "undo", "00000000-0000-0000-0000-000000000000"])
    assert code == 3 and err.startswith("error\tnot_found\t")


def test_add_note_with_no_frontmatter_is_invalid(url, tmp_path):
    path = tmp_path / "bad.md"
    path.write_text("no frontmatter here\n", encoding="utf-8")
    assert run_captured(["brain", "add-note", "--file", str(path)])[0] == 6


# ---------------------------------------------------------------- not allowed (4)


@pytest.mark.parametrize("verb", sorted(WRITERS))
def test_a_restricted_note_exits_4_and_writes_nothing(url, verb):
    before = dump(url)
    code, out, err = run_captured([*WRITERS[verb]("ada-lin"), *v(url, "ada-lin")])
    assert (code, out) == (4, "") and err.startswith("error\tnot_allowed\t")
    assert "Ada" not in err
    assert dump(url) == before


def test_linking_to_a_restricted_note_exits_4(url):
    before = dump(url)
    argv = ["brain", "link", "odd-idea", "related_to", "ada-lin", *v(url, "odd-idea")]
    assert run_captured(argv)[0] == 4
    assert dump(url) == before


def test_add_note_over_a_restricted_slug_exits_4(url, tmp_path):
    before = dump(url)
    code, _, err = run_captured(["brain", "add-note", "--file", str(new_note(tmp_path, "ada-lin"))])
    assert code == 4 and "Ada" not in err
    assert dump(url) == before


def test_undo_of_a_permanent_change_is_not_allowed_or_invalid(url):
    _, out, _ = run_captured([*WRITERS["remove-fact"]("pottery-course"), *v(url, "pottery-course")])
    change = q(url, "SELECT undo_id FROM brain.undo WHERE operation='remove-fact'")[0][0]
    assert run_captured(["brain", "undo", str(change)])[0] == 6  # 400: permanent


# ---------------------------------------------------------------- stale (5)


@pytest.mark.parametrize("verb", sorted(WRITERS))
def test_a_stale_version_exits_5_and_writes_nothing(url, verb):
    stale = version(url, "pottery-course")
    run_captured(["brain", "add-fact", "glaze-chemistry", "x", *v(url, "glaze-chemistry")])
    assert run_captured([*WRITERS["add-fact"]("pottery-course"), "--version", str(stale)])[0] == 0
    before = dump(url)
    code, out, err = run_captured([*WRITERS[verb]("pottery-course"), "--version", str(stale)])
    assert (code, out) == (5, "") and err.startswith("error\tstale\t")
    assert dump(url) == before


def test_undo_used_twice_is_refused(url, tmp_path):
    _, out, _ = run_captured(["brain", "add-note", "--file", str(new_note(tmp_path))])
    undo_id = out.rstrip("\n").split("\t")[3]
    assert run_captured(["brain", "undo", undo_id])[0] == 0
    assert run_captured(["brain", "undo", undo_id])[0] == 6  # 409, not about a version


# ---------------------------------------------------------------- usage and help


@pytest.mark.parametrize("verb", sorted(WRITERS))
def test_version_is_required(verb):
    code, _, err = run_captured(WRITERS[verb]("pottery-course"))
    assert code == 2 and err.startswith("error\tusage\t")


@pytest.mark.parametrize("verb", ["add-note", *sorted(WRITERS), "undo"])
def test_help_exits_0(verb):
    code, out, _ = run_captured(["brain", verb, "--help"])
    assert code == 0 and "usage:" in out
