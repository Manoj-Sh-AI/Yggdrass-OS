"""The brain in PostgreSQL: schema rules, the loader, and the maps rendered into map_cache.

Runs on a throwaway local cluster (brain_pg.py) and brains of invented notes.
"""

import datetime as dt
import re

import pytest

from brain_pg import Cluster, make_brain, pg_bin

psycopg = pytest.importorskip("psycopg")

from yggdras.data.brain_db import loader, migrate, render  # noqa: E402
from yggdras.data.graph import structural as st  # noqa: E402
from yggdras.data.maps.build import build_maps  # noqa: E402

TABLES = ("areas", "notes", "note_areas", "verbs", "relationships", "note_bodies", "aliases",
          "dated_items", "changes", "map_cache")  # fmt: skip
MIGRATIONS = [1, 2, 3, 4]


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
    assert migrate.up(c) == MIGRATIONS
    yield c
    c.rollback()
    c.close()


@pytest.fixture
def brain(tmp_path, monkeypatch):
    monkeypatch.setenv("YGGDRAS_BRAIN", str(tmp_path / "the-real-one"))
    return make_brain(tmp_path / "copy")


@pytest.fixture
def messy(tmp_path, monkeypatch):
    monkeypatch.setenv("YGGDRAS_BRAIN", str(tmp_path / "the-real-one"))
    return make_brain(tmp_path / "messy", messy=True)


def run(c, sql, args=()):
    with c.cursor() as cur:
        cur.execute(sql, args)
        rows = cur.fetchall() if cur.description else None
    c.commit()
    return rows


def rejected(c, *statements):
    """The statements, in one transaction, are refused (at once or at commit)."""
    with pytest.raises(psycopg.errors.IntegrityError):
        with c.transaction(), c.cursor() as cur:
            for sql in statements:
                cur.execute(sql)
    c.rollback()


def add_note(c, slug, area, *also):
    with c.transaction(), c.cursor() as cur:
        cur.execute(
            "INSERT INTO brain.notes (slug, title, type, area_code) VALUES (%s, %s, 't', %s)",
            (slug, slug.upper(), area),
        )
        for i, code in enumerate([area, *also]):
            cur.execute("INSERT INTO brain.note_areas VALUES (%s, %s, %s, %s)",
                        (slug, code, i == 0, i))  # fmt: skip
    c.commit()


def seed(c):
    """Three areas, two notes, two verbs: the smallest legal brain."""
    run(c, "INSERT INTO brain.areas (area_code, name, sort_order) VALUES "
           "('04', 'learning', 4), ('08', 'rest-joy', 8), ('09', 'cross', 9)")  # fmt: skip
    run(c, "INSERT INTO brain.verbs VALUES ('uses', 'used_in', 'x'), ('knows', 'knows', 'y')")
    add_note(c, "a", "04", "09")
    add_note(c, "b", "08")


def dump(c) -> dict[str, list]:
    return {t: run(c, f"SELECT * FROM brain.{t} ORDER BY 1, 2") for t in TABLES}


# ---------------------------------------------------------------- schema


def test_migrations_roll_forward_and_back(conn):
    def names():
        rows = run(conn, "SELECT table_name FROM information_schema.tables "
                         "WHERE table_schema = 'brain'")  # fmt: skip
        return {r[0] for r in rows}

    assert names() == {*TABLES, "manual", "undo", "schema_migrations"}
    assert migrate.down(conn) == [4] and "undo" not in names()
    assert not run(conn, "SELECT 1 FROM information_schema.tables WHERE table_schema = 'public'")
    assert migrate.down(conn) == [3] and migrate.current(conn) == 2
    assert "manual" not in names()
    assert migrate.down(conn) == [2] and migrate.current(conn) == 1
    assert "note_areas" not in names()
    assert migrate.down(conn) == [1] and names() == {"schema_migrations"}
    assert migrate.up(conn) == MIGRATIONS and migrate.up(conn) == []


def test_migration_2_moves_also_area_into_note_areas_and_back(conn):
    migrate.down(conn, 1)
    run(conn, "INSERT INTO brain.areas (area_code, name, sort_order) VALUES "
              "('04', 'learning', 4), ('08', 'rest-joy', 8)")  # fmt: skip
    run(conn, "INSERT INTO brain.notes (slug, title, type, area_code, also_area) VALUES "
              "('a', 'A', 't', '04', '08'), ('b', 'B', 't', '08', NULL)")  # fmt: skip
    migrate.up(conn)
    assert run(conn, "SELECT * FROM brain.note_areas ORDER BY slug, ord") == [
        ("a", "04", True, 0), ("a", "08", False, 1), ("b", "08", True, 0)
    ]  # fmt: skip
    migrate.down(conn, 1)
    assert run(conn, "SELECT slug, also_area FROM brain.notes ORDER BY slug") == [
        ("a", "08"), ("b", None)
    ]  # fmt: skip


def test_bad_rows_are_rejected(conn):
    seed(conn)
    rejected(
        conn, "INSERT INTO brain.notes (slug, title, type, area_code) VALUES ('c', 'C', 't', '99')"
    )  # noqa: E501  bad FK
    rejected(
        conn, "INSERT INTO brain.notes (slug, title, type, area_code) VALUES ('a', 'A', 't', '04')"
    )  # noqa: E501  duplicate slug
    run(conn, "INSERT INTO brain.relationships VALUES ('a', 'uses', 'b', 'link')")
    rejected(conn, "INSERT INTO brain.relationships VALUES ('a', 'uses', 'b', 'link')")  # dup
    rejected(conn, "INSERT INTO brain.relationships VALUES ('a', 'frobs', 'b', 'link')")  # verb
    rejected(conn, "INSERT INTO brain.relationships VALUES ('a', 'knows', 'a', 'link')")  # self
    rejected(conn, "INSERT INTO brain.relationships VALUES ('a', 'knows', 'zz', 'link')")  # FK
    rejected(conn, "INSERT INTO brain.areas (area_code, name, sort_order) VALUES ('4', 'x', 1)")
    rejected(conn, "UPDATE brain.notes SET parent_slug = 'a' WHERE slug = 'a'")  # own parent
    rejected(conn, "UPDATE brain.notes SET parent_slug = 'zz' WHERE slug = 'a'")  # no such note


def test_every_note_has_exactly_one_primary_area(conn):
    seed(conn)
    note = "INSERT INTO brain.notes (slug, title, type, area_code) VALUES ('c', 'C', 't', '04')"
    rejected(conn, note)  # no primary area
    rejected(conn, note, "INSERT INTO brain.note_areas VALUES ('c', '04', true, 0)",
             "INSERT INTO brain.note_areas VALUES ('c', '08', true, 1)")  # two  # fmt: skip
    rejected(
        conn, note, "INSERT INTO brain.note_areas VALUES ('c', '08', true, 0)"
    )  # not area_code
    rejected(conn, "DELETE FROM brain.note_areas WHERE slug = 'a' AND is_primary")
    add_note(conn, "c", "04", "08", "09")  # any number of secondary areas
    assert run(conn, "SELECT count(*) FROM brain.note_areas WHERE slug = 'c'") == [(3,)]


def test_deleting_a_note_cascades_but_keeps_its_history(conn):
    seed(conn)
    run(conn, "INSERT INTO brain.note_bodies VALUES ('a', 'text')")
    run(conn, "INSERT INTO brain.aliases VALUES ('alpha', 'a', 0)")
    run(conn, "INSERT INTO brain.dated_items (slug, date, kind) VALUES ('a', '2030-01-01', "
              "'review')")  # fmt: skip
    run(conn, "INSERT INTO brain.relationships VALUES ('a', 'uses', 'b', 'link'), "
              "('b', 'knows', 'a', 'link')")  # fmt: skip
    run(conn, "INSERT INTO brain.changes (slug, slug_text, kind, new_text, actor) "
              "VALUES ('a', 'a', 'add', 'a fact', 'test')")  # fmt: skip
    run(conn, "UPDATE brain.areas SET hub_slug = 'a' WHERE area_code = '04'")
    run(conn, "UPDATE brain.notes SET parent_slug = 'a' WHERE slug = 'b'")
    run(conn, "DELETE FROM brain.notes WHERE slug = 'a'")
    for table in ("note_bodies", "aliases", "dated_items", "relationships"):
        assert run(conn, f"SELECT count(*) FROM brain.{table}") == [(0,)], table
    assert run(conn, "SELECT slug FROM brain.note_areas") == [("b",)]
    assert run(conn, "SELECT slug, slug_text, new_text FROM brain.changes") == [
        (None, "a", "a fact")
    ]
    assert run(conn, "SELECT hub_slug FROM brain.areas WHERE area_code = '04'") == [(None,)]
    assert run(conn, "SELECT parent_slug FROM brain.notes WHERE slug = 'b'") == [(None,)]


def test_an_area_holding_notes_and_a_verb_in_use_cannot_be_deleted(conn):
    seed(conn)
    run(conn, "INSERT INTO brain.relationships VALUES ('a', 'uses', 'b', 'link')")
    rejected(conn, "DELETE FROM brain.areas WHERE area_code = '04'")  # a primary area
    rejected(conn, "DELETE FROM brain.areas WHERE area_code = '09'")  # a secondary one
    rejected(conn, "DELETE FROM brain.verbs WHERE verb = 'uses'")
    run(conn, "DELETE FROM brain.verbs WHERE verb = 'knows'")  # unused: fine


def test_every_write_to_a_note_or_its_body_bumps_its_version(conn):
    seed(conn)
    run(conn, "INSERT INTO brain.note_bodies VALUES ('a', 'text')")
    run(conn, "UPDATE brain.notes SET description = 'd' WHERE slug = 'a'")
    run(conn, "UPDATE brain.note_bodies SET body = 'more text' WHERE slug = 'a'")
    assert run(conn, "SELECT slug, version FROM brain.notes ORDER BY slug") == [("a", 3), ("b", 1)]


# ---------------------------------------------------------------- loader

CLEAN_COUNTS = {
    "notes": (12, 12), "facts": (14, 14), "history lines": (1, 1), "links": (19, 19),
    "mentions": (2, 2), "aliases": (6, 6), "dated items": (8, 8), "areas": (9, 9),
    "verbs": (23, 23),
}  # fmt: skip


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
    assert "couldn't place (0):" in report, report
    assert "today's upcoming code finds 5 (fact lines and reviews, all dates); 5 of them" in report
    assert "notes.status: " in report and "areas.node_range" in report  # left null, reported
    assert "id: 12 note(s)" in report and "pages: 2 note(s)" in report  # kept in bodies only
    assert "verb 'mentions' (inverse 'mentioned_in') added by the loader" in report
    assert "area 09-cross added by the loader" in report
    assert (
        "written with an inverse verb, stored as pottery-course part_of glaze-chemistry" in report
    )


def test_areas_aliases_and_chunk_parents_are_stored_as_written(conn, brain):
    loader.load(conn, brain)
    areas = run(conn, "SELECT slug, area_code, is_primary FROM brain.note_areas "
                      "WHERE slug IN ('glaze-chemistry', 'odd-idea') "
                      "ORDER BY slug, ord")  # fmt: skip
    assert areas == [
        ("glaze-chemistry", "04", True), ("glaze-chemistry", "08", False),
        ("glaze-chemistry", "01", False), ("odd-idea", "09", True), ("odd-idea", "04", False),
    ]  # fmt: skip
    assert run(conn, "SELECT alias FROM brain.aliases WHERE slug = 'pottery-course' "
                     "ORDER BY ord") == [("pottery",), ("clay class",)]  # fmt: skip
    assert run(conn, "SELECT slug, parent_slug FROM brain.notes WHERE parent_slug IS NOT NULL "
                     "ORDER BY slug") == [("clay-handbook-part-1", "clay-handbook"),
                                          ("clay-handbook-part-2", "clay-handbook")]  # fmt: skip
    assert run(conn, "SELECT from_slug, to_slug FROM brain.relationships WHERE kind = 'mention' "
                     "ORDER BY 1") == [("odd-idea", "wheel-throwing"),
                                       ("pottery-course", "ada-lin")]  # fmt: skip


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
    mine = "SELECT slug, slug_text FROM brain.changes WHERE actor <> 'markdown-history'"
    assert run(conn, mine) == [("ada-lin", "ada-lin")]
    imported = "SELECT count(*) FROM brain.changes WHERE actor = 'markdown-history'"
    assert run(conn, imported) == [(2,)]  # pottery-course: its History line + its section


def test_what_does_not_fit_is_listed_never_forced(conn, messy):
    report = loader.load(conn, messy)
    got = counts(report)
    assert got["notes"] == (14, 14) and got["links"] == (23, 20) and got["aliases"] == (7, 6)
    assert got["dated items"] == (8, 8) and got["facts"] == (16, 16), report
    expected = [
        "night-walks: review 'someday' is not a date; column left null, no dated item",
        "lost-book-part-1: a chunk in folder 'lost-book', which is no note; parent_slug left null",
        "alias 'Ada' of night-walks: already an alias of ada-lin",
        "link night-walks → related_to [[night-walks]]: a note linking to itself",
        "link night-walks → frobs [[ada-lin]]: verb not in the verb list",
        "link night-walks → related_to [[missing-note]]: no such note",
    ]
    for line in expected:
        assert line in report, (line, report)
    assert f"couldn't place ({len(expected)}):" in report, report


def test_an_area_that_fits_no_area_stops_the_load(conn, brain):
    loader.load(conn, brain)
    before = dump(conn)
    odd = brain / "library/10-ideas/odd-idea.md"
    odd.write_text(odd.read_text(encoding="utf-8").replace("area: cross", "area: 11-people"),
                   encoding="utf-8")  # fmt: skip
    with pytest.raises(loader.Refused, match="odd-idea: area '11-people' fits no area"):
        loader.load(conn, brain)
    assert dump(conn) == before  # nothing written


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


def test_dated_items_come_from_frontmatter_and_fact_lines(conn, brain):
    loader.load(conn, brain)
    assert run(conn, "SELECT slug, date, kind, label FROM brain.dated_items ORDER BY id") == [
        ("ada-lin", dt.date(2030, 2, 1), "start", "Ada Lin (start)"),
        ("kiln-decision", dt.date(2030, 2, 10), "decided", "Kiln Decision (decided)"),
        ("kiln-decision", dt.date(2030, 3, 1), "event", "Kiln Decision (event)"),
        ("kiln-decision", dt.date(2030, 6, 1), "review", "Kiln Decision (review)"),
        ("pottery-course", dt.date(2030, 5, 1), "review", "Pottery Course (review)"),
        ("pottery-course", dt.date(2030, 7, 15), "event", "Pottery Course (event)"),
        ("studio-open-day", dt.date(2030, 4, 12), "event", "Studio Open Day (event)"),
        ("studio-open-day", dt.date(2030, 4, 13), "end", "Studio Open Day (end)"),
    ]


# ---------------------------------------------------------------- maps


def strip_version(text: str) -> str:
    return re.sub(r"map_version \w*", "map_version V", text)


def maps_from_rows_and_files(conn, repo):
    loader.load(conn, repo)
    files = build_maps(repo / st.LIBRARY)
    rows = {name: text for name, (text, _) in render.render_maps(conn).items()}
    pairs = {"atlas": "atlas.md", "shelf": "shelf-map.md", "relationships": "relationship-map.md"}
    return {name: (strip_version(rows[name]), strip_version(files[f])) for name, f in pairs.items()}


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


def test_the_maps_match_the_markdown_build_byte_for_byte(conn, brain):
    """Cross notes, several areas, mentions, alias order and chunks included: the only
    difference is map_version."""
    for name, (rows, files) in maps_from_rows_and_files(conn, brain).items():
        assert rows == files, name
    rows = {name: text for name, (text, _) in render.render_maps(conn).items()}
    assert "chain clay-handbook: -part-1 > -part-2" in rows["relationships"]
    assert "mentions wheel-throwing" in rows["relationships"]
    assert "C:clay-handbook P:1 to 20" in rows["shelf"]
    assert "A:08,01" in rows["shelf"] and "## cross" in rows["shelf"]
    assert "cross-area (1)" in rows["atlas"]


def test_on_the_messy_brain_only_rows_the_loader_refused_differ(conn, messy):
    """What the loader reported it couldn't place is all that differs: the duplicate alias,
    the review that is no date, and the chunk whose parent is no note."""
    diffs = {}
    for name, (rows, files) in maps_from_rows_and_files(conn, messy).items():
        a, b = rows.splitlines(), files.splitlines()
        assert len(a) == len(b), name
        diffs[name] = [(x, y) for x, y in zip(a, b, strict=True) if x != y]
    assert diffs["atlas"] == [] and diffs["relationships"] == []
    assert diffs["shelf"] == [  # rows | files, in map order (area 01 first)
        (
            "night-walks|topic|Night Walks|Night Walks in a few invented words||—|2030-03-02|",
            "night-walks|topic|Night Walks|Night Walks in a few invented words|Ada|—|2030-03-02|"
            "R:someday",
        ),
        (
            "lost-book-part-1|source|Lost Book, part 1|Lost Book, part 1 in a few invented "
            "words||—|2030-03-02|P:1 to 9",
            "lost-book-part-1|source|Lost Book, part 1|Lost Book, part 1 in a few invented "
            "words||—|2030-03-02|C:lost-book P:1 to 9",
        ),
    ]
