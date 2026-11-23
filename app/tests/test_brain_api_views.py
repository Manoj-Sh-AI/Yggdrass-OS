"""N1: the brain's api.* views (brain migration 0005) on a throwaway cluster and the invented
brain. `ada-lin` is the invented `sensitivity: high` note; `pottery-course` links to it."""

import pytest

from brain_pg import Cluster, make_brain, pg_bin

psycopg = pytest.importorskip("psycopg")

from yggdras.data.brain_db import api as reads  # noqa: E402
from yggdras.data.brain_db import loader, migrate  # noqa: E402

VIEWS = ("brain_areas", "brain_notes", "brain_note_bodies", "brain_note_areas", "brain_links",
         "brain_search")  # fmt: skip
SECRET_MARKS = ("ada-lin", "Ada Lin", "Ada teaches", "Ada runs")


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
def conn(pg_url, tmp_path):
    with psycopg.connect(pg_url) as c:
        migrate.down(c, 0)
        migrate.up(c)
        loader.load(c, make_brain(tmp_path / "brain"))
        yield c


def rows(conn, sql, args=None):
    return conn.execute(sql, args).fetchall()


def everything(conn) -> str:
    """Every value of every api.brain_* view as one string (the leak scan)."""
    out = []
    for view in VIEWS:
        cols = "*" if view != "brain_search" else "slug, title, type, area_code, version"
        out += [repr(r) for r in rows(conn, f"SELECT {cols} FROM api.{view}")]
    return "\n".join(out)


def test_no_view_contains_anything_from_the_restricted_note(conn):
    assert rows(conn, "SELECT sensitivity FROM brain.notes WHERE slug='ada-lin'") == [("high",)]
    text = everything(conn)
    for mark in SECRET_MARKS:
        assert mark not in text, mark


def test_tree_shows_a_masked_row_for_the_restricted_note(conn):
    masked = rows(conn, "SELECT slug, title, type, version, area_code FROM api.brain_notes "
                        "WHERE sensitivity='restricted'")  # fmt: skip
    assert masked == [(None, "Sensitive note", None, None, "08")]
    live = rows(conn, "SELECT count(*) FROM brain.notes WHERE archived_at IS NULL")[0][0]
    assert rows(conn, "SELECT count(*) FROM api.brain_notes")[0][0] == live


def test_normal_notes_match_the_tables(conn):
    expected = reads.note_with_relationships(conn, "glaze-chemistry")
    got = rows(conn, "SELECT slug, title, version, body FROM api.brain_note_bodies "
                     "WHERE slug='glaze-chemistry'")  # fmt: skip
    assert got == [("glaze-chemistry", expected["title"], expected["version"], expected["body"])]
    assert rows(conn, "SELECT version FROM api.brain_notes WHERE slug='glaze-chemistry'") == [
        (expected["version"],)
    ]


def test_links_to_or_from_a_restricted_note_are_left_out(conn):
    raw = rows(conn, "SELECT count(*) FROM brain.relationships "
                     "WHERE 'ada-lin' IN (from_slug, to_slug)")[0][0]  # fmt: skip
    assert raw > 0  # the fixture really links to it
    assert rows(conn, "SELECT count(*) FROM api.brain_links "
                      "WHERE 'ada-lin' IN (from_slug, to_slug)") == [(0,)]  # fmt: skip
    # a normal-normal link is still there
    assert ("pottery-course", "related_to", "glaze-chemistry") in [
        r[:3] for r in rows(conn, "SELECT from_slug, verb, to_slug FROM api.brain_links")
    ]


def test_search_finds_normal_notes_and_never_the_restricted_one(conn):
    def search(q):
        return [r[0] for r in rows(conn, "SELECT slug FROM api.brain_search, "
                                         "websearch_to_tsquery('simple', %s) q WHERE document @@ q",
                                   (q,))]  # fmt: skip

    assert search("Saturdays") == ["pottery-course"]
    assert search("teaches") == []  # only ada-lin's body says it
    assert reads.search(conn, "teaches")  # the raw table has it, so the filter did the work


def test_access_tells_not_allowed_from_not_found(conn):
    def access(slug):
        return rows(conn, "SELECT api.brain_note_access(%s)", (slug,))[0][0]

    assert access("pottery-course") == "normal"
    assert access("ada-lin") == "restricted"
    assert access("no-such-note") is None
    conn.execute("UPDATE brain.notes SET archived_at = now() WHERE slug='kiln-decision'")
    assert access("kiln-decision") is None


def slugs(conn) -> set:
    found = set()
    for view, col in (("brain_notes", "slug"), ("brain_note_bodies", "slug"),
                      ("brain_note_areas", "slug"), ("brain_search", "slug"),
                      ("brain_links", "from_slug"), ("brain_links", "to_slug")):  # fmt: skip
        found |= {r[0] for r in rows(conn, f"SELECT {col} FROM api.{view}")}
    return found


def test_a_body_naming_the_restricted_note_is_masked(conn):
    raw = rows(conn, "SELECT body FROM brain.note_bodies WHERE slug='pottery-course'")[0][0]
    assert "[[ada-lin]]" in raw
    shown = rows(conn, "SELECT body FROM api.brain_note_bodies WHERE slug='pottery-course'")[0][0]
    assert "[[ada-lin]]" not in shown and "[[sensitive-note]]" in shown
    assert shown.replace("[[sensitive-note]]", "[[ada-lin]]") == raw  # nothing else changed
    found = rows(conn, "SELECT slug FROM api.brain_search, websearch_to_tsquery('simple', "
                       "'ada') q WHERE document @@ q")  # fmt: skip
    assert found == []


def test_archived_notes_are_never_shown(conn):
    conn.execute("UPDATE brain.notes SET archived_at = now() WHERE slug='kiln-decision'")
    assert "kiln-decision" not in slugs(conn)  # other notes may still mention it in text


def test_a_note_marked_high_disappears_at_once(conn):
    conn.execute("UPDATE brain.notes SET sensitivity='HIGH' WHERE slug='glaze-chemistry'")
    assert "glaze-chemistry" not in everything(conn)  # its row, its links, and [[links]] to it
    assert rows(conn, "SELECT api.brain_note_access('glaze-chemistry')") == [("restricted",)]


def test_a_child_does_not_name_a_restricted_parent(conn):
    conn.execute("UPDATE brain.notes SET sensitivity='high' WHERE slug='clay-handbook'")
    parents = rows(conn, "SELECT parent_slug FROM api.brain_notes "
                         "WHERE slug LIKE 'clay-handbook-part-%'")  # fmt: skip
    assert parents == [(None,), (None,)]


def test_down_then_up_again(conn):
    assert migrate.current(conn) == 5
    migrate.down(conn, 4)
    assert rows(conn, "SELECT to_regclass('api.brain_notes')") == [(None,)]
    migrate.up(conn)
    assert rows(conn, "SELECT count(*) FROM api.brain_notes")[0][0] > 0
