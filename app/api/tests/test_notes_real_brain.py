"""Optional integration with the Brain owner's actual HTTP API and disposable rows.

Set YGGDRAS_BRAIN_TEST_PROJECT to that checkout. Never loads .env, uses a personal
database, invokes a model, or changes the Brain implementation.
"""

import importlib.util
import os
import sys
from pathlib import Path

import pytest

from yggdress_app.notes_proxy import BrainNotesHTTP, NotesError, NotesProxy


@pytest.fixture
def real_brain(tmp_path, monkeypatch):
    project = os.environ.get("YGGDRAS_BRAIN_TEST_PROJECT")
    if not project:
        pytest.skip("Set YGGDRAS_BRAIN_TEST_PROJECT for actual Brain API integration.")
    project = Path(project).resolve()
    monkeypatch.syspath_prepend(str(project / "app" / "src"))
    # Optional integration reuses the Brain environment's pure-Python dependencies
    # as a fallback; the application's installed packages retain precedence.
    brain_packages = project / "app" / ".venv" / "Lib" / "site-packages"
    if brain_packages.is_dir():
        monkeypatch.setattr(sys, "path", [*sys.path, str(brain_packages)])
    fixture_path = project / "app" / "tests" / "brain_pg.py"
    spec = importlib.util.spec_from_file_location("integration_brain_pg", fixture_path)
    fixture = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture)
    import psycopg
    from yggdras.data.brain_db import api as reads
    from yggdras.data.brain_db import loader, migrate
    from yggdras.data.brain_db.store import RowStore
    from yggdras.data.brain_db.writes import BrainWrites
    from yggdras.interface.brain_api import BrainApi
    from yggdras.interface.note_server import start

    binaries = fixture.pg_bin()
    if binaries is None:
        pytest.skip("PostgreSQL binaries are required for the disposable test database.")
    cluster = fixture.Cluster(binaries, tmp_path / "postgres")
    url = cluster.start()
    server = None
    try:
        monkeypatch.setenv("YGGDRAS_BRAIN", str(tmp_path / "not-the-import"))
        with psycopg.connect(url) as conn:
            migrate.up(conn)
            loader.load(conn, fixture.make_brain(tmp_path / "invented"))
        store = RowStore(lambda: psycopg.connect(url), today="2030-03-10")

        def read(name, *args):
            with psycopg.connect(url) as conn:
                return getattr(reads, name)(conn, *args)

        api = BrainApi(
            "integration",
            "invented-credential",
            read,
            BrainWrites(store, lambda: True, lambda: "2030-03-10"),
        )
        port = fixture.free_port()
        server = start(lambda: None, port, None, api)
        assert server is not None
        http = BrainNotesHTTP(f"http://127.0.0.1:{port}", "integration", "invented-credential")
        yield NotesProxy(http), fixture, store
    finally:
        if server:
            server.shutdown()
            server.server_close()
        cluster.stop()


def test_actual_api_create_save_reopen_undo_and_remove(real_brain):
    proxy, fixture, store = real_brain
    _, text = fixture.note(
        "integration-note",
        "Integration Note",
        "concept",
        "04-learning",
        folder="10-ideas",
        facts=["An invented starting point"],
    )
    created = proxy.create("session", text, "integration-note")
    assert created["note"]["slug"] == "integration-note" and created["canUndo"]
    reopened = proxy.get("session", "integration-note")["note"]
    edited = reopened["rawBody"].replace("## Links", "- A second invented point\n\n## Links")
    preview = proxy.preview("session", reopened["slug"], reopened["fetchToken"], edited)
    assert preview["changes"][0]["kind"] == "add-fact"
    saved = proxy.confirm("session", preview["token"])
    assert "A second invented point" in saved["note"]["content"]
    # A new application proxy has no cached snapshot: this is database persistence.
    assert (
        "A second invented point"
        in NotesProxy(proxy.http).get("reloaded", "integration-note")["note"]["content"]
    )
    proxy.undo("session")
    original = proxy.get("session", "integration-note")["note"]
    assert "A second invented point" not in original["content"]
    edited = original["rawBody"].replace("An invented starting point", "A corrected point")
    preview = proxy.preview("session", original["slug"], original["fetchToken"], edited)
    saved = proxy.confirm("session", preview["token"])
    assert "A corrected point" in saved["note"]["content"]
    raw = proxy.get("session", "integration-note")["note"]
    edited = (
        "\n".join(
            line
            for line in raw["rawBody"].splitlines()
            if not line.startswith("- A corrected point")
        )
        + "\n"
    )
    preview = proxy.preview("session", raw["slug"], raw["fetchToken"], edited)
    assert preview["changes"][0]["permanent"]
    saved = proxy.confirm("session", preview["token"])
    assert "A corrected point" not in saved["note"]["content"]
    with store.connect() as conn:
        assert (
            conn.execute(
                "SELECT body FROM brain.note_bodies WHERE slug=%s", ("integration-note",)
            ).fetchone()[0]
            == saved["note"]["rawBody"]
        )


def test_actual_api_stale_confirm_and_authentication(real_brain):
    proxy, _, _ = real_brain
    note = proxy.get("first", "pottery-course")["note"]
    changed = note["rawBody"].replace("The course runs on Saturdays", "The course runs on Sundays")
    preview = proxy.preview("first", note["slug"], note["fetchToken"], changed)
    proxy.http.call("POST", "note/pottery-course/add-fact", {"line": "A concurrent point"})
    with pytest.raises(NotesError) as error:
        proxy.confirm("first", preview["token"])
    assert error.value.code == "brain_stale" and error.value.extra["completed"] == 0
    current = proxy.get("second", "pottery-course")["note"]
    assert "A concurrent point" in current["content"]
    assert "The course runs on Sundays" not in current["content"]
    unauthorized = BrainNotesHTTP(proxy.http.root, "integration", "wrong")
    with pytest.raises(NotesError) as error:
        unauthorized.call("GET", "search?q=")
    assert error.value.code == "brain_authentication"
