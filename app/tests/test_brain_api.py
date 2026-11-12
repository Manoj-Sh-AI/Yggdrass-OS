"""The brain API's auth and write endpoints (D44 §6), on a throwaway cluster and a brain of
invented notes. Writes are checked like Lia's, saved in one transaction, and undone once."""

import base64
import json
import urllib.error
import urllib.request

import pytest

from brain_pg import Cluster, free_port, make_brain, note, pg_bin

psycopg = pytest.importorskip("psycopg")

from yggdras.data.brain_db import api as reads  # noqa: E402
from yggdras.data.brain_db import loader, migrate  # noqa: E402
from yggdras.data.brain_db.store import RowStore  # noqa: E402
from yggdras.data.brain_db.writes import BrainWrites  # noqa: E402
from yggdras.interface import brain_api, note_server  # noqa: E402
from yggdras.processing.lia.library import RowLibrary  # noqa: E402

TODAY = "2030-03-10"
FACT = "The course runs on Saturdays (src: self, 2030-01-05)"
MENTION = "Taught by [[ada-lin]] at the studio (src: self, 2030-01-05)"
USER, PASSWORD = "tester", "not-a-real-secret"
TABLES = ("notes", "note_bodies", "relationships", "aliases", "changes", "map_cache", "undo")


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
def env(pg_url, tmp_path, monkeypatch):
    """(api, store, live switch): the invented brain loaded, the brain on rows."""
    monkeypatch.setenv("YGGDRAS_BRAIN", str(tmp_path / "the-real-one"))
    with psycopg.connect(pg_url) as conn:
        migrate.down(conn, 0)
        migrate.up(conn)
        loader.load(conn, make_brain(tmp_path / "copy"))
    store = RowStore(lambda: psycopg.connect(pg_url), today=TODAY)
    live = {"rows": True}

    def read(name, *args):
        with psycopg.connect(pg_url) as conn:
            return getattr(reads, name)(conn, *args)

    writes = BrainWrites(store, lambda: live["rows"], lambda: TODAY)
    return brain_api.BrainApi(USER, PASSWORD, read, writes), store, live


def q(store, sql, args=()):
    with store.connect() as conn:
        return conn.execute(sql, args).fetchall()


def dump(store):
    return {t: q(store, f"SELECT * FROM brain.{t} ORDER BY 1") for t in TABLES}


def body(store, slug):
    return q(store, "SELECT body FROM brain.note_bodies WHERE slug = %s", (slug,))[0][0]


def post(api, route, data=None):
    return api.post(route, data or {})


# ---------------------------------------------------------------- auth


def call(port, path, auth=None, data=None):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}",
                                 data=json.dumps(data).encode() if data is not None else None)  # noqa: E501  # fmt: skip
    if auth:
        req.add_header("Authorization", "Basic " + base64.b64encode(auth.encode()).decode())
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("WWW-Authenticate")


def test_every_api_route_needs_the_credential(env):
    api, store, _ = env
    port = free_port()
    server = note_server.start(lambda: RowLibrary(store.snapshot()), port, None, api)
    try:
        assert call(port, "/api/tree")[0] == 401  # no header
        status, challenge = call(port, "/api/tree", auth=f"{USER}:wrong")
        assert status == 401 and challenge.startswith("Basic")
        assert call(port, "/api/note/ada-lin", auth="someone:else")[0] == 401
        assert call(port, "/api/note", data={"text": "x"})[0] == 401  # writes too
        status, tree = call(port, "/api/tree", auth=f"{USER}:{PASSWORD}")
        assert status == 200 and tree[3]["code"] == "04"
        status, v = call(port, "/api/version/ada-lin", auth=f"{USER}:{PASSWORD}")
        assert status == 200 and isinstance(v["version"], int)
        page = urllib.request.urlopen(f"http://127.0.0.1:{port}/note/ada-lin")  # footnotes: open
        assert page.status == 200
    finally:
        server.shutdown()


def test_the_api_does_not_start_without_both_credentials(monkeypatch):
    monkeypatch.setenv("BRAIN_API_USER", "someone")
    monkeypatch.delenv("BRAIN_API_PASSWORD", raising=False)
    with pytest.raises(brain_api.ApiConfigError) as exc:
        brain_api.credentials()
    assert "BRAIN_API_PASSWORD" in str(exc.value) and "someone" not in str(exc.value)


def test_writes_wait_for_the_switch_to_rows(env):
    api, store, live = env
    live["rows"] = False
    before = dump(store)
    status, out = post(api, "note/ada-lin/add-fact", {"line": "Ada fires on Sundays"})
    assert status == 409 and "still on markdown" in out["error"]
    assert dump(store) == before


# ---------------------------------------------------------------- adding: at once, with Undo


def test_add_note_writes_at_once_and_undoes_once(env):
    api, store, _ = env
    _, text = note("slip-casting", "Slip Casting", "concept", "04-learning", folder="10-ideas",
                   facts=["Slip casting uses [[glaze-chemistry]] ideas"],
                   links=["related_to [[wheel-throwing]]"])  # fmt: skip
    status, out = post(api, "note", {"text": text})
    assert status == 200, out
    assert q(store, "SELECT 1 FROM brain.notes WHERE slug = 'slip-casting'")
    assert "slip-casting related_to wheel-throwing" in out["links_added"]
    assert "slip-casting mentions glaze-chemistry (mention)" in out["links_added"]
    assert post(api, f"undo/{out['undo_id']}")[0] == 200
    assert not q(store, "SELECT 1 FROM brain.notes WHERE slug = 'slip-casting'")
    status, again = post(api, f"undo/{out['undo_id']}")
    assert status == 409 and "used already" in again["error"]


def test_add_fact_after_a_line_then_undo(env):
    api, store, _ = env
    before = body(store, "pottery-course")
    status, out = post(api, "note/pottery-course/add-fact",
                       {"line": "Clay is ordered on Fridays", "after_line": FACT})  # fmt: skip
    assert status == 200, out
    lines = body(store, "pottery-course").split("\n")
    i = lines.index(f"- {FACT}")
    assert lines[i + 1].startswith("- Clay is ordered on Fridays. (src: manoj, 2030-03-10)")
    assert post(api, f"undo/{out['undo_id']}")[0] == 200
    assert body(store, "pottery-course") == before
    assert post(api, f"undo/{out['undo_id']}")[0] == 409


def test_link_preview_shows_the_reverse_and_writes_one_row(env):
    api, store, _ = env
    before = dump(store)
    status, view = post(api, "note/ada-lin/link",
                        {"target_slug": "glaze-chemistry", "verb": "uses", "preview": True})  # noqa: E501  # fmt: skip
    assert status == 200 and view["preview"] is True
    assert view["reverse_reads_as"] == "glaze-chemistry used_in ada-lin"
    assert dump(store) == before  # a preview writes nothing
    status, out = post(api, "note/ada-lin/link", {"target_slug": "glaze-chemistry", "verb": "uses",
                                                  "preview": False, "back_link": True})  # fmt: skip
    assert status == 200, out and "not written" in out["back_link"]
    rows = q(store, "SELECT from_slug, verb, to_slug FROM brain.relationships "
                    "WHERE 'glaze-chemistry' IN (from_slug, to_slug) AND 'ada-lin' IN "
                    "(from_slug, to_slug)")  # fmt: skip
    assert rows == [("ada-lin", "uses", "glaze-chemistry")]  # one row, one direction (D31)
    assert post(api, f"undo/{out['undo_id']}")[0] == 200
    assert not q(store, "SELECT 1 FROM brain.relationships WHERE from_slug = 'ada-lin' "
                        "AND to_slug = 'glaze-chemistry'")  # fmt: skip
    assert post(api, f"undo/{out['undo_id']}")[0] == 409


# ---------------------------------------------------------------- replace: preview, Confirm, Undo


def test_replace_preview_is_one_object_with_its_links_and_writes_nothing(env):
    api, store, _ = env
    before = dump(store)
    new = "The course runs on Saturdays, on the [[wheel-throwing]] wheels"
    status, view = post(api, "note/pottery-course/replace-fact",
                        {"old_line": FACT, "new_line": new, "preview": True})  # fmt: skip
    assert status == 200 and view["preview"] is True
    assert view["old_line"] == FACT and view["new_line"] == new
    assert view["links_added"] == ["wheel-throwing"] and view["links_removed"] == []
    assert dump(store) == before


def test_replace_writes_history_detects_the_new_link_and_undoes(env):
    api, store, _ = env
    before = body(store, "pottery-course")
    new = "The course runs on Sundays, on the [[wheel-throwing]] wheels (src: manoj, 2030-03-10)"
    status, out = post(api, "note/pottery-course/replace-fact",
                       {"old_line": FACT, "new_line": new, "preview": False})  # fmt: skip
    assert status == 200, out
    assert "pottery-course mentions wheel-throwing (mention)" in out["links_added"]
    stored = body(store, "pottery-course")
    assert "Sundays" in stored and "Saturdays" not in stored and "## History" not in stored
    slug, slug_text, kind, old, newtext = q(
        store, "SELECT slug, slug_text, kind, old_text, new_text FROM brain.changes "
               "WHERE request_id = %s AND section = '## Facts'", (out["change_id"],))[0]  # noqa: E501  # fmt: skip
    assert (slug, slug_text, kind) == ("pottery-course", "pottery-course", "replace")
    assert "Saturdays" in old and "Sundays" in newtext
    assert post(api, f"undo/{out['undo_id']}")[0] == 200
    assert body(store, "pottery-course") == before
    assert post(api, f"undo/{out['undo_id']}")[0] == 409


def test_a_replace_that_drops_a_link_warns_and_keeps_the_link_lines(env):
    api, store, _ = env
    new = "Taught at the studio (src: self, 2030-01-05)"
    status, view = post(api, "note/pottery-course/replace-fact",
                        {"old_line": MENTION, "new_line": new, "preview": True})  # fmt: skip
    assert view["links_removed"] == ["ada-lin"]
    status, out = post(api, "note/pottery-course/replace-fact",
                       {"old_line": MENTION, "new_line": new, "preview": False})  # fmt: skip
    assert status == 200 and out["warnings"] and "ada-lin" in out["warnings"][0]
    # text is the truth: the mention went with its line; the note's link line to ada-lin stays
    assert q(store, "SELECT kind FROM brain.relationships WHERE from_slug = 'pottery-course' "
                    "AND to_slug = 'ada-lin'") == [("link",)]  # fmt: skip


# ---------------------------------------------------------------- permanent: remove and unlink


def test_remove_fact_previews_then_erases_for_good(env):
    api, store, _ = env
    before = dump(store)
    status, view = post(api, "note/pottery-course/remove-fact", {"line": FACT, "preview": True})
    assert status == 200 and "cannot be undone" in view["permanent"]
    assert dump(store) == before
    status, out = post(api, "note/pottery-course/remove-fact", {"line": FACT, "preview": False})
    assert status == 200 and out["done"] and out["undo"] is None
    assert "Saturdays" not in body(store, "pottery-course")
    assert not q(store, "SELECT 1 FROM brain.changes WHERE old_text LIKE '%%Saturdays%%' "
                        "AND actor <> 'markdown-history'")  # no copy anywhere  # fmt: skip
    status, err = post(api, f"undo/{out['change_id']}")
    assert status == 400 and "permanent" in err["error"]


def test_unlink_previews_then_removes_for_good(env):
    api, store, _ = env
    link = {"target_slug": "wheel-throwing", "verb": "uses"}
    has = lambda: q(store, "SELECT count(*) FROM brain.relationships WHERE from_slug = "  # noqa: E731
                           "'pottery-course' AND verb = 'uses' AND to_slug = 'wheel-throwing'")[0][0]  # noqa: E501  # fmt: skip
    before = dump(store)
    status, view = post(api, "note/pottery-course/unlink", {**link, "preview": True})
    assert status == 200 and "cannot be undone" in view["permanent"] and dump(store) == before
    status, out = post(api, "note/pottery-course/unlink", {**link, "preview": False})
    assert status == 200 and out["done"] and has() == 0
    assert q(store, "SELECT old_text FROM brain.changes WHERE kind = 'unlink'") == [(None,)]
    status, err = post(api, f"undo/{out['change_id']}")
    assert status == 400 and "permanent" in err["error"]


def test_a_stale_version_is_refused(env):
    api, store, _ = env
    v = q(store, "SELECT version FROM brain.notes WHERE slug = 'ada-lin'")[0][0]
    assert (
        post(api, "note/ada-lin/add-fact", {"line": "Ada fires on Sundays", "version": v})[0] == 200
    )
    status, err = post(api, "note/ada-lin/add-fact", {"line": "Ada glazes too", "version": v})
    assert status == 409 and "reload and review" in err["error"]


def test_unknown_routes_and_ids(env):
    api, _, _ = env
    assert post(api, "note/ada-lin/frobnicate")[0] == 404
    assert post(api, "undo/not-a-uuid")[0] == 404
    assert post(api, "undo/00000000-0000-0000-0000-000000000000")[0] == 404
    assert post(api, "note/no-such-note/add-fact", {"line": "x"})[0] == 404


def test_search_lists_every_note_or_full_text_matches_behind_auth(env):
    api, store, _ = env
    port = free_port()
    server = note_server.start(lambda: RowLibrary(store.snapshot()), port, None, api)
    me = f"{USER}:{PASSWORD}"
    try:
        assert call(port, "/api/search?q=kiln")[0] == 401  # same auth as every route
        status, every = call(port, "/api/search", auth=me)
        slugs = [n["slug"] for n in every]
        assert status == 200 and slugs == sorted(slugs) and len(slugs) == 12
        status, empty = call(port, "/api/search?q=", auth=me)
        assert empty == every
        status, hits = call(port, "/api/search?q=kiln", auth=me)
        assert status == 200 and hits[0]["slug"] == "kiln-decision"  # best match first
        assert all(h["rank"] > 0 for h in hits)
        status, phrase = call(port, "/api/search?q=%22shared%20kiln%22", auth=me)
        assert [h["slug"] for h in phrase] == ["kiln-decision"]
        assert call(port, "/api/search?q=zzzunknownword", auth=me) == (200, [])
    finally:
        server.shutdown()
    with store.connect() as conn:  # archived notes are never found
        conn.execute("UPDATE brain.notes SET archived_at = now() WHERE slug = 'kiln-decision'")
        assert "kiln-decision" not in {n["slug"] for n in reads.search(conn, "kiln")}
        assert "kiln-decision" not in {n["slug"] for n in reads.search(conn, "")}
