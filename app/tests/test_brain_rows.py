"""Lia on rows (D44): reading a snapshot, writing one transaction per request, history and
Undo on `changes`, the maps in map_cache, the app's endpoints and the note server.

Runs on a throwaway local cluster (brain_pg.py) with a brain of invented notes.
"""

import json
import re
import urllib.request

import pytest

from brain_pg import Cluster, make_brain, pg_bin

psycopg = pytest.importorskip("psycopg")

from yggdras.data.brain.ops import build_change  # noqa: E402
from yggdras.data.brain_db import api, loader, migrate, render  # noqa: E402
from yggdras.data.brain_db.store import RowStore, write_note  # noqa: E402
from yggdras.data.graph import structural as st  # noqa: E402
from yggdras.interface import note_server  # noqa: E402
from yggdras.processing.lia.library import Library, RowLibrary  # noqa: E402

TODAY = "2030-03-10"
FACT = "The course runs on Saturdays (src: self, 2030-01-05)"


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
def loaded(pg_url, tmp_path, monkeypatch):
    """The invented brain, loaded into fresh tables; returns (store, markdown repo)."""
    monkeypatch.setenv("YGGDRAS_BRAIN", str(tmp_path / "the-real-one"))
    repo = make_brain(tmp_path / "copy")
    with psycopg.connect(pg_url) as conn:
        migrate.down(conn, 0)
        migrate.up(conn)
        loader.load(conn, repo)
    store = RowStore(lambda: psycopg.connect(pg_url), today=TODAY,
                     viewer_dirs=(tmp_path / "view",), raw_root=tmp_path / "raw")  # fmt: skip
    return store, repo


def q(store, sql, args=()):
    with store.connect() as conn, conn.cursor() as cur:
        cur.execute(sql, args)
        return cur.fetchall() if cur.description else None


def write(store, ops):
    change = build_change(store.root, False, ops, TODAY, builder=store.builder)
    return store.apply(change, "test"), change


def body(store, slug):
    return q(store, "SELECT body FROM brain.note_bodies WHERE slug = %s", (slug,))[0][0]


def version(store, slug):
    return q(store, "SELECT version FROM brain.notes WHERE slug = %s", (slug,))[0][0]


# ---------------------------------------------------------------- reading


def test_lia_reads_from_rows_exactly_what_she_read_from_files(loaded):
    store, repo = loaded
    rows, files = RowLibrary(store.snapshot()), Library(repo / st.LIBRARY)
    assert rows.notes.keys() == files.notes.keys()
    for slug in files.notes:
        assert rows.note_text(slug) == files.note_text(slug), slug  # History put back
        assert rows.blocks(slug) == files.blocks(slug), slug  # the same citable lines
    assert "## History" not in body(store, "pottery-course")  # but never stored
    content, results, _ = rows.open_notes(["pottery-course", "ada-lin"])
    assert [c["type"] for c in content] == ["search_result", "search_result"]  # never text
    assert all(c["citations"] == {"enabled": True} for c in content)
    assert content == files.open_notes(["pottery-course", "ada-lin"])[0]
    for query in ("pottery saturday", "Ada", "clay firing", "kiln"):
        assert rows.search_notes(query) == files.search_notes(query), query
    assert rows.manual() == files.manual()
    strip = lambda t: re.sub(r"map_version \w+", "map_version V", t)  # noqa: E731
    assert {k: strip(v) for k, v in rows.maps().items()} == {
        k: strip(v) for k, v in files.maps().items()
    }


def test_maps_come_from_map_cache_and_two_builds_are_byte_identical(loaded):
    store, _ = loaded
    with store.connect() as conn:
        first = render.render_maps(conn)
        assert render.render_maps(conn) == first
        cached = dict(q(store, "SELECT map_name, rendered_text FROM brain.map_cache"))
    assert cached == {name: text for name, (text, _) in first.items()}
    assert RowLibrary(store.snapshot()).maps()["atlas.md"] == cached["atlas"]


# ---------------------------------------------------------------- writing


def test_an_add_is_written_at_once_with_its_history_row_and_new_maps(loaded):
    store, _ = loaded
    before_v, before_maps = version(store, "ada-lin"), q(store, "SELECT * FROM brain.map_cache")
    out, _ = write(store, [{"op": "add_fact", "slug": "ada-lin", "text": "Ada fires on Sundays"}])
    assert out.status == "written", out.message
    assert "Ada fires on Sundays" in body(store, "ada-lin")
    assert version(store, "ada-lin") > before_v
    rows = q(store, "SELECT kind, section, new_text, request_id FROM brain.changes "
                    "WHERE slug = 'ada-lin' AND kind = 'add'")  # fmt: skip
    assert any("Ada fires on Sundays" in r[2] and r[1] == "## Facts" for r in rows)
    assert rows[0][3] == out.sha
    assert q(store, "SELECT * FROM brain.map_cache") != before_maps  # updated: new `updated`


def test_replace_keeps_only_the_new_text_in_the_note(loaded):
    store, _ = loaded
    op = {"op": "replace_fact", "slug": "pottery-course", "old": FACT,
          "text": "The course runs on Sundays", "mode": "until"}  # fmt: skip
    out, change = write(store, [op])
    assert out.status == "written", out.message
    stored = body(store, "pottery-course")
    assert "Sundays" in stored and "Saturdays" not in stored and "## History" not in stored
    old, new, tag = q(store, "SELECT old_text, new_text, tag FROM brain.changes "
                             "WHERE request_id = %s AND kind = 'replace' "
                             "AND section = '## Facts'", (out.sha,))[0]  # fmt: skip
    assert "Saturdays" in old and "Sundays" in new and tag == f"until: {TODAY}"
    text = RowLibrary(store.snapshot()).note_text("pottery-course")
    assert "Saturdays" in text.split("## History")[1]  # Lia can say what it used to say
    assert "old text kept in history" in change.lines[0]


def test_remove_erases_for_good_and_cannot_be_undone(loaded):
    store, _ = loaded
    op = {"op": "remove_fact", "slug": "pottery-course", "old": FACT, "mode": "wrong",
          "reason": "never true"}  # fmt: skip
    out, change = write(store, [op])
    assert out.status == "written", out.message
    assert "this cannot be undone" in change.lines[0]
    assert "Saturdays" not in body(store, "pottery-course")
    assert q(store, "SELECT old_text, new_text FROM brain.changes WHERE request_id = %s "
                    "AND kind = 'remove'", (out.sha,)) == [(None, None)]  # no copy  # fmt: skip
    assert not q(store, "SELECT 1 FROM brain.changes WHERE old_text LIKE %s "
                        "AND actor <> 'markdown-history'", ("%Saturdays%",))  # fmt: skip
    undo = store.undo(out.sha, "test")
    assert undo.status == "blocked" and "can't be undone" in undo.message


def test_unlink_deletes_the_row_for_good(loaded):
    """Unlink is permanent (Manoj, 2026-11-12): no copy kept, no Undo."""
    store, _ = loaded
    link = ("pottery-course", "uses", "wheel-throwing")
    has = lambda: q(store, "SELECT count(*) FROM brain.relationships WHERE from_slug = %s "  # noqa: E731
                           "AND verb = %s AND to_slug = %s", link)[0][0]  # fmt: skip
    assert has() == 1
    out, _ = write(store, [{"op": "unlink", "from": link[0], "verb": link[1], "to": link[2]}])
    assert out.status == "written", out.message
    assert has() == 0
    assert q(store, "SELECT kind, old_text FROM brain.changes WHERE request_id = %s AND section "
                    "= '## Links'", (out.sha,)) == [("unlink", None)]  # fmt: skip
    undone = store.undo(out.sha, "test")
    assert undone.status == "blocked" and "permanent" in undone.message
    assert has() == 0


def test_undo_of_a_new_note_takes_it_out_but_keeps_its_history(loaded):
    store, _ = loaded
    op = {"op": "create_note", "type": "concept", "name": "Slip Casting", "area": "04-learning",
          "description": "Pouring liquid clay into moulds", "summary": "Liquid clay in moulds.",
          "facts": [{"text": "Slip casting uses plaster moulds"}],
          "links": [{"verb": "related_to", "to": "glaze-chemistry"}]}  # fmt: skip
    out, _ = write(store, [op])
    assert out.status == "written", out.message
    assert q(store, "SELECT 1 FROM brain.notes WHERE slug = 'slip-casting'")
    assert store.undo(out.sha, "test").status == "written"
    assert not q(store, "SELECT 1 FROM brain.notes WHERE slug = 'slip-casting'")
    assert q(store, "SELECT count(*) FROM brain.changes WHERE slug_text = 'slip-casting' "
                    "AND slug IS NULL")[0][0] >= 2  # fmt: skip


def test_a_stale_version_is_rejected_never_overwritten(loaded):
    store, _ = loaded
    op = {"op": "replace_fact", "slug": "pottery-course", "old": FACT,
          "text": "The course runs on Mondays", "mode": "until"}  # fmt: skip
    change = build_change(store.root, False, [op], TODAY, builder=store.builder)
    seen = store.versions_of(change)  # what a preview remembers
    other = RowStore(store.connect, today=TODAY)
    out, _ = write(other, [{"op": "add_fact", "slug": "pottery-course", "text": "Clay is wet"}])
    assert out.status == "written"
    late = store.apply(change, "test", expect=seen)
    assert late.status == "blocked" and "reload and review" in late.message
    assert "Mondays" not in body(store, "pottery-course")


def test_one_failed_step_rolls_back_the_whole_request(loaded, monkeypatch):
    store, _ = loaded
    before = {t: q(store, f"SELECT * FROM brain.{t} ORDER BY 1") for t in
              ("notes", "note_bodies", "changes", "relationships", "map_cache")}  # fmt: skip

    def boom(*a, **k):
        raise RuntimeError("the map build failed")

    monkeypatch.setattr(render, "build_cache", boom)
    out, _ = write(store, [{"op": "add_fact", "slug": "ada-lin", "text": "Ada fires on Sundays"},
                           {"op": "link", "from": "ada-lin", "verb": "knows",
                            "to": "pottery-course"}])  # fmt: skip
    assert out.status == "blocked" and "nothing was written" in out.message
    after = {t: q(store, f"SELECT * FROM brain.{t} ORDER BY 1") for t in before}
    assert after == before


def test_archive_hides_a_note_everywhere_and_restore_brings_back_what_it_took(loaded):
    store, _ = loaded
    original = {s: body(store, s) for s in ("wheel-throwing", "pottery-course", "odd-idea")}
    out, _ = write(store, [{"op": "archive_note", "slug": "wheel-throwing"}])
    assert out.status == "written", out.message
    lib = RowLibrary(store.snapshot())
    assert "wheel-throwing" not in lib.notes
    assert "wheel-throwing" not in {s for s, _ in lib.search_notes("centre the clay")[1]}
    content, _, notices = lib.open_notes(["wheel-throwing"])
    assert content == [] and "no such note" in notices[0]
    with store.connect() as conn:
        assert all(n["slug"] != "wheel-throwing" for a in api.note_tree(conn) for n in a["notes"])
        assert api.note_with_relationships(conn, "wheel-throwing") is None
        maps = render.render_maps(conn)
    assert all("wheel-throwing" not in text for text, _ in maps.values())
    assert "[[wheel-throwing]]" not in body(store, "pottery-course")
    back = build_change(store.root, False, [{"op": "restore_note", "slug": "wheel-throwing"}],
                        TODAY, builder=store.builder)  # fmt: skip
    res = store.apply(back, "test")
    assert res.status == "written", res.message
    assert "wheel-throwing" in RowLibrary(store.snapshot()).notes
    for slug in ("pottery-course", "odd-idea"):  # their link lines and mentions came back
        assert "[[wheel-throwing]]" in body(store, slug), slug
    assert body(store, "wheel-throwing") == original["wheel-throwing"]


def test_changes_survive_the_note_being_deleted(loaded):
    store, _ = loaded
    write(store, [{"op": "add_fact", "slug": "ada-lin", "text": "Ada fires on Sundays"}])
    q(store, "DELETE FROM brain.notes WHERE slug = 'ada-lin'")
    left = q(store, "SELECT slug, slug_text FROM brain.changes WHERE slug_text = 'ada-lin'")
    assert left and all(s is None and t == "ada-lin" for s, t in left)


def test_the_app_write_carries_the_version_token(loaded):
    store, _ = loaded
    with store.connect() as conn:
        v = api.version(conn, "ada-lin")
    text = body(store, "ada-lin").replace("Ada teaches pottery", "Ada teaches wheel pottery")
    assert write_note(store, "ada-lin", text, v - 1, "app").status == "blocked"  # stale
    ok = write_note(store, "ada-lin", text, v, "app")
    assert ok.status == "written", ok.message
    with store.connect() as conn:
        assert api.version(conn, "ada-lin") > v


# ---------------------------------------------------------------- endpoints and the note server


def test_the_three_endpoints(loaded):
    store, _ = loaded
    with store.connect() as conn:
        tree = api.note_tree(conn)
        note = api.note_with_relationships(conn, "pottery-course")
        v = api.version(conn, "pottery-course")
    assert [a["code"] for a in tree] == ["01", "02", "03", "04", "05", "06", "07", "08", "09"]
    assert tree[-1]["name"] == "cross" and tree[-1]["notes"][0]["slug"] == "odd-idea"
    assert note["version"] == v and note["areas"] == ["04"]
    assert {"verb": "uses", "to": "wheel-throwing", "kind": "link"} in note["outgoing"]
    assert {"verb": "has_part", "from_": "glaze-chemistry", "kind": "link"} not in note["incoming"]
    assert any(i["from_"] == "studio-open-day" and i["verb"] == "subject_of"
               for i in note["incoming"])  # fmt: skip
    assert note["mentions"] == ["ada-lin"]


def test_the_note_server_serves_notes_graph_and_api_from_rows(loaded):
    store, _ = loaded
    store.render_viewers()
    library = RowLibrary(store.snapshot())

    def call(name, *args):
        with store.connect() as conn:
            return getattr(api, name)(conn, *args)

    import base64

    from yggdras.data.brain_db.writes import BrainWrites
    from yggdras.interface.brain_api import BrainApi

    brain = BrainApi("tester", "not-a-real-secret", call,
                     BrainWrites(store, lambda: True, lambda: TODAY))  # fmt: skip
    auth = {"Authorization": "Basic " + base64.b64encode(b"tester:not-a-real-secret").decode()}
    get = lambda url: urllib.request.urlopen(urllib.request.Request(url, headers=auth))  # noqa: E731
    port = __import__("brain_pg").free_port()
    server = note_server.start(lambda: library, port, store.viewer_dirs[0], brain)
    try:
        base = f"http://127.0.0.1:{port}"
        page = urllib.request.urlopen(f"{base}/note/pottery-course").read().decode()
        assert "The course runs on Saturdays" in page
        assert urllib.request.urlopen(f"{base}/graph").status == 200
        tree = json.loads(get(f"{base}/api/tree").read())
        assert tree[3]["code"] == "04"
        note = json.loads(get(f"{base}/api/note/ada-lin").read())
        assert note["slug"] == "ada-lin" and isinstance(note["version"], int)
    finally:
        server.shutdown()


def test_lia_previews_a_remove_as_permanent_and_refuses_a_stale_confirm(loaded, tmp_path):
    from test_lia import FakeClient
    from yggdras.data.brain.pending import Store
    from yggdras.processing.lia.write import EXPECT, WriteSide

    store, _ = loaded
    side = WriteSide(FakeClient([]), RowLibrary(store.snapshot()), store,
                     Store(tmp_path / "y.db"), today=TODAY)  # fmt: skip
    ops = [{"op": "remove_fact", "slug": "pottery-course", "old": FACT, "mode": "until"}]
    change = side.plan(ops)
    preview = side.preview_text(change, "drop the saturday line")
    assert "this cannot be undone" in preview
    item = side.store.add("drop it", "test", ops + [{"op": EXPECT,
                          "versions": store.versions_of(change)}], preview)  # fmt: skip
    out, _ = write(
        RowStore(store.connect, today=TODAY),
        [{"op": "add_fact", "slug": "pottery-course", "text": "Clay is wet"}],
    )
    assert out.status == "written"
    card = side.confirm(item.id, item.token, "test")
    assert card.kind == "refused" and "reload and review" in card.text
    assert "Saturdays" in body(store, "pottery-course")  # nothing was erased
    fresh = side.store.add("drop it", "test", ops, preview)  # re-reviewed: confirm writes
    store.refresh()
    card = side.confirm(fresh.id, fresh.token, "test")
    assert card.kind == "summary", card.text
    assert "cannot be undone" in card.text and "change " in card.text
