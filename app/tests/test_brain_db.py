"""The brain in PostgreSQL: schema rules, the loader, and the maps rendered into map_cache.

Runs on a throwaway local cluster (brain_pg.py) and a brain of invented notes.
"""

import datetime as dt
import re

import pytest

from brain_pg import Cluster, make_brain, pg_bin

psycopg = pytest.importorskip("psycopg")

from yggdras.data.brain_db import loader, migrate, render  # noqa: E402
from yggdras.data.graph import structural as st  # noqa: E402
from yggdras.data.maps.build import build_maps  # noqa: E402
from yggdras.data.maps.notes import load_notes  # noqa: E402
from yggdras.data.maps.relations import relationship_map  # noqa: E402

TABLES = ("areas", "notes", "verbs", "relationships", "note_bodies", "aliases", "dated_items",
          "changes", "map_cache")  # fmt: skip


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
def conn(pg_url):
    c = psycopg.connect(pg_url)
    migrate.down(c, 0)
    assert migrate.up(c) == [1]
    yield c
    c.rollback()
    c.close()


@pytest.fixture
def brain(tmp_path, monkeypatch):
    monkeypatch.setenv("YGGDRAS_BRAIN", str(tmp_path / "the-real-one"))
    return make_brain(tmp_path / "copy")


def run(c, sql, args=()):
    with c.cursor() as cur:
        cur.execute(sql, args)
        rows = cur.fetchall() if cur.description else None
    c.commit()
    return rows


def rejected(c, sql, args=()):
    with pytest.raises(psycopg.errors.IntegrityError):
        run(c, sql, args)
    c.rollback()


def seed(c):
    """Two areas, two notes, one verb, the smallest legal brain."""
    run(c, "INSERT INTO brain.areas (area_code, name, sort_order) VALUES "
           "('04', 'learning', 4), ('08', 'rest-joy', 8)")  # fmt: skip
    run(c, "INSERT INTO brain.verbs VALUES ('uses', 'used_in', 'x'), ('knows', 'knows', 'y')")
    for slug, area in (("a", "04"), ("b", "08")):
        run(c, "INSERT INTO brain.notes (slug, title, type, area_code) VALUES (%s, %s, 't', %s)",
            (slug, slug.upper(), area))  # fmt: skip


def dump(c) -> dict[str, list]:
    return {t: run(c, f"SELECT * FROM brain.{t} ORDER BY 1, 2") for t in TABLES}


# ---------------------------------------------------------------- schema


def test_migrations_roll_forward_and_back(conn):
    names = lambda: {r[0] for r in run(conn, "SELECT table_name FROM information_schema.tables "  # noqa: E731
                                              "WHERE table_schema = 'brain'")}  # fmt: skip
    assert names() == {*TABLES, "schema_migrations"}
    assert not run(conn, "SELECT 1 FROM information_schema.tables WHERE table_schema = 'public'")
    assert migrate.down(conn) == [1] and migrate.current(conn) == 0
    assert names() == {"schema_migrations"}
    assert migrate.up(conn) == [1] and migrate.up(conn) == []


def test_bad_rows_are_rejected(conn):
    seed(conn)
    rejected(conn, "INSERT INTO brain.notes (slug, title, type, area_code) "
                   "VALUES ('c', 'C', 't', '99')")  # bad FK  # fmt: skip
    rejected(conn, "INSERT INTO brain.notes (slug, title, type, area_code) "
                   "VALUES ('a', 'A again', 't', '04')")  # duplicate slug  # fmt: skip
    run(conn, "INSERT INTO brain.relationships VALUES ('a', 'uses', 'b', 'link')")
    rejected(conn, "INSERT INTO brain.relationships VALUES ('a', 'uses', 'b', 'link')")  # dup
    rejected(conn, "INSERT INTO brain.relationships VALUES ('a', 'frobs', 'b', 'link')")  # verb
    rejected(conn, "INSERT INTO brain.relationships VALUES ('a', 'knows', 'a', 'link')")  # self
    rejected(conn, "INSERT INTO brain.relationships VALUES ('a', 'knows', 'zz', 'link')")  # FK
    rejected(conn, "INSERT INTO brain.areas (area_code, name, sort_order) VALUES ('4', 'x', 1)")


def test_deleting_a_note_cascades_but_keeps_its_history(conn):
    seed(conn)
    run(conn, "INSERT INTO brain.note_bodies VALUES ('a', 'text')")
    run(conn, "INSERT INTO brain.aliases VALUES ('alpha', 'a')")
    run(conn, "INSERT INTO brain.dated_items (slug, date, kind) VALUES ('a', '2030-01-01', "
              "'review')")  # fmt: skip
    run(conn, "INSERT INTO brain.relationships VALUES ('a', 'uses', 'b', 'link'), "
              "('b', 'knows', 'a', 'link')")  # fmt: skip
    run(conn, "INSERT INTO brain.changes (slug, slug_text, kind, new_text, actor) "
              "VALUES ('a', 'a', 'add', 'a fact', 'test')")  # fmt: skip
    run(conn, "UPDATE brain.areas SET hub_slug = 'a' WHERE area_code = '04'")
    run(conn, "DELETE FROM brain.notes WHERE slug = 'a'")
    for table in ("note_bodies", "aliases", "dated_items", "relationships"):
        assert run(conn, f"SELECT count(*) FROM brain.{table}") == [(0,)], table
    assert run(conn, "SELECT slug, slug_text, new_text FROM brain.changes") == [
        (None, "a", "a fact")
    ]
    assert run(conn, "SELECT hub_slug FROM brain.areas WHERE area_code = '04'") == [(None,)]


def test_an_area_holding_notes_and_a_verb_in_use_cannot_be_deleted(conn):
    seed(conn)
    run(conn, "INSERT INTO brain.relationships VALUES ('a', 'uses', 'b', 'link')")
    with pytest.raises(psycopg.errors.IntegrityError):
        run(conn, "DELETE FROM brain.areas WHERE area_code = '04'")
    conn.rollback()
    with pytest.raises(psycopg.errors.IntegrityError):
        run(conn, "DELETE FROM brain.verbs WHERE verb = 'uses'")
    conn.rollback()
    run(conn, "DELETE FROM brain.verbs WHERE verb = 'knows'")  # unused: fine


def test_every_write_to_a_note_or_its_body_bumps_its_version(conn):
    seed(conn)
    run(conn, "INSERT INTO brain.note_bodies VALUES ('a', 'text')")
    run(conn, "UPDATE brain.notes SET description = 'd' WHERE slug = 'a'")
    run(conn, "UPDATE brain.note_bodies SET body = 'more text' WHERE slug = 'a'")
    assert run(conn, "SELECT slug, version FROM brain.notes ORDER BY slug") == [("a", 3), ("b", 1)]


# ---------------------------------------------------------------- loader

CLEAN_COUNTS = {"notes": (11, 11), "facts": (10, 10), "links": (18, 18), "aliases": (5, 5),
                "dated items": (5, 5), "areas": (8, 8), "verbs": (22, 22)}  # fmt: skip


def counts(report: str) -> dict[str, tuple[int, int]]:
    out = {}
    for line in report.splitlines():
        m = re.match(r"^(\w+(?: \w+)?)\s+(\d+)\s+(\d+)$", line)
        if m:
            out[m.group(1)] = (int(m.group(2)), int(m.group(3)))
    return out


def test_the_count_report_is_correct_on_an_invented_brain(conn, brain):
    report = loader.load(conn, brain)
    assert counts(report) == CLEAN_COUNTS, report
    assert "couldn't place (1):" in report  # the one [[mention]], not stored
    assert "1 [[mentions]]" in report
    assert "notes.status: " in report and "areas.node_range" in report  # left null, reported
    assert "id: 11 note(s)" in report and "pages: 2 note(s)" in report  # kept in bodies only
    assert (
        "written with an inverse verb, stored as pottery-course part_of glaze-chemistry" in report
    )


def test_the_circular_areas_and_notes_load_fills_every_hub(conn, brain):
    loader.load(conn, brain)
    hubs = dict(run(conn, "SELECT area_code, hub_slug FROM brain.areas WHERE hub_slug IS NOT NULL"))
    assert hubs == {"04": "hub-learning", "08": "hub-rest-joy"}
    assert run(conn, "SELECT max(version) FROM brain.notes") == [(1,)]


def test_two_runs_give_identical_tables(conn, brain):
    loader.load(conn, brain)
    first = dump(conn)
    loader.load(conn, brain)
    assert dump(conn) == first
    assert all(first[t] for t in TABLES if t != "changes")


def test_history_survives_a_reload(conn, brain):
    loader.load(conn, brain)
    run(conn, "INSERT INTO brain.changes (slug, slug_text, kind, new_text, actor) "
              "VALUES ('ada-lin', 'ada-lin', 'add', 'x', 'test')")  # fmt: skip
    loader.load(conn, brain)
    assert run(conn, "SELECT slug, slug_text FROM brain.changes") == [("ada-lin", "ada-lin")]


def test_what_does_not_fit_is_listed_never_forced(conn, tmp_path, monkeypatch):
    monkeypatch.setenv("YGGDRAS_BRAIN", str(tmp_path / "elsewhere"))
    repo = make_brain(tmp_path / "messy", messy=True)
    report = loader.load(conn, repo)
    got = counts(report)
    assert got["notes"] == (13, 12) and got["links"] == (23, 18) and got["aliases"] == (7, 5)
    assert got["dated items"] == (6, 5) and got["facts"] == (12, 11)
    for expected in (
        "odd-idea: area 'cross' (areas holds 01–08 only)",
        "night-walks: also ['08-rest-joy', '02-relationships']",
        "night-walks: review 'someday' is not a date; column left null, no dated item",
        "alias 'Ada' of night-walks: already an alias of ada-lin",
        "related_to [[night-walks]]: a note linking to itself",
        "related_to [[missing-note]]: no such note",
        "related_to [[odd-idea]]: odd-idea is not in the database",
        "frobs [[ada-lin]]: verb not in the verb list",
    ):
        assert expected in report, (expected, report)
    assert run(
        conn, "SELECT also_area, review_date FROM brain.notes WHERE slug = 'night-walks'"
    ) == [("08", None)]


def test_the_real_brain_is_refused_without_real(tmp_path, monkeypatch):
    repo = make_brain(tmp_path / "brain")
    monkeypatch.setenv("YGGDRAS_BRAIN", str(repo))
    with pytest.raises(loader.Refused, match="not a copy"):
        loader.check_copy(repo, real=False)
    loader.check_copy(repo, real=True)
    monkeypatch.setenv("YGGDRAS_BRAIN", "")
    monkeypatch.setenv("YGGDRAS_ENV_FILE", str(tmp_path / "no.env"))
    with pytest.raises(loader.Refused, match="can't be told"):
        loader.check_copy(repo, real=False)
    assert loader.main([str(repo)]) == 2  # refused before any connection


def test_the_loader_never_prints_the_connection_string(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("YGGDRAS_BRAIN", str(tmp_path / "elsewhere"))
    secret = "postgresql://someone:hunter2@127.0.0.1:1/nowhere"
    monkeypatch.setenv("BRAIN_DATABASE_URL", secret)
    assert loader.main([str(make_brain(tmp_path / "copy"))]) == 2
    out = capsys.readouterr()
    assert "hunter2" not in out.out + out.err and "someone" not in out.out + out.err


# ---------------------------------------------------------------- maps


def strip_version(text: str) -> str:
    return re.sub(r"map_version \w*", "map_version V", text)


def test_rendering_twice_is_byte_identical(conn, brain):
    loader.load(conn, brain)
    assert render.render_maps(conn) == render.render_maps(conn)
    cached = dict(run(conn, "SELECT map_name, rendered_text FROM brain.map_cache"))
    assert cached == {name: text for name, (text, _) in render.render_maps(conn).items()}


def test_map_version_changes_when_and_only_when_the_text_does(conn, brain):
    loader.load(conn, brain)
    before = dict(run(conn, "SELECT map_name, map_version FROM brain.map_cache"))
    built = dict(run(conn, "SELECT map_name, built_at FROM brain.map_cache"))
    assert render.build_cache(conn) == before  # nothing changed: same versions, same rows
    assert dict(run(conn, "SELECT map_name, built_at FROM brain.map_cache")) == built
    run(conn, "UPDATE brain.notes SET decided_date = '2030-02-11' WHERE slug = 'kiln-decision'")
    assert render.build_cache(conn) == before  # not shown in any map
    run(conn, "UPDATE brain.notes SET description = 'Changed' WHERE slug = 'ada-lin'")
    after = render.build_cache(conn)
    assert after["shelf"] != before["shelf"]
    assert after["atlas"] == before["atlas"] and after["relationships"] == before["relationships"]
    text, version = run(conn, "SELECT rendered_text, map_version FROM brain.map_cache "
                              "WHERE map_name = 'shelf'")[0]  # fmt: skip
    assert f"map_version {version}" in text.splitlines()[0]
    assert render.version_of(text.replace(f"map_version {version}", "map_version ")) == version


def test_the_maps_match_the_markdown_build(conn, brain):
    """Same format as today's maps: the rows render what the files render, except the
    [[mentions]], which are not stored (the markdown side is built without them here)."""
    loader.load(conn, brain)
    root = brain / st.LIBRARY
    files = build_maps(root)
    notes = load_notes(root, st.mapped_shelves())
    graph = st.build_map(root, st.mapped_shelves())
    files["relationship-map.md"] = relationship_map(graph, notes, "V", mentions=False)
    rows = {name: text for name, (text, _) in render.render_maps(conn).items()}
    assert strip_version(rows["atlas"]) == strip_version(files["atlas.md"])
    assert strip_version(rows["shelf"]) == strip_version(files["shelf-map.md"])
    assert strip_version(rows["relationships"]) == strip_version(files["relationship-map.md"])
    assert "chain clay-handbook: -part-1 > -part-2" in rows["relationships"]
    assert "C:clay-handbook P:1 to 20" in rows["shelf"]


def test_dated_items_come_from_frontmatter_dates(conn, brain):
    loader.load(conn, brain)
    assert run(conn, "SELECT slug, date, kind, label FROM brain.dated_items ORDER BY id") == [
        ("kiln-decision", dt.date(2030, 2, 10), "decided", "Kiln Decision (decided)"),
        ("kiln-decision", dt.date(2030, 6, 1), "review", "Kiln Decision (review)"),
        ("pottery-course", dt.date(2030, 5, 1), "review", "Pottery Course (review)"),
        ("studio-open-day", dt.date(2030, 4, 12), "event", "Studio Open Day (event)"),
        ("studio-open-day", dt.date(2030, 4, 13), "end", "Studio Open Day (end)"),
    ]
