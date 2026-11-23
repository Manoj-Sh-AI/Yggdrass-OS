"""Real disposable PostgreSQL consolidation; no personal data or inference calls."""

import hashlib
import json
import secrets
import shutil
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import psycopg
import pytest
from fastapi.testclient import TestClient
from postgres_fixture import isolated_database
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from yggdress_app import local_consolidation
from yggdress_app.application import create_app
from yggdress_app.backup import fingerprints
from yggdress_app.database import Database
from yggdress_app.notes_proxy import NotesError
from yggdress_app.shared_database import (
    LAYOUT,
    ConsolidationError,
    _source_guard,
    brain_snapshot,
    migration_connection,
    prepare,
    text_settings,
    verify_boundaries,
)


@pytest.fixture(scope="module")
def postgres():
    # Other modules intentionally create extra backup schemas in their shared
    # fixture. A consolidation source must be an isolated app-only database.
    with isolated_database() as value:
        yield value


@pytest.fixture
def brain_source(postgres):
    name = "yggdress_test_brain_" + secrets.token_hex(5)
    with psycopg.connect(postgres["admin"], autocommit=True) as admin:
        if sys.platform == "win32":
            admin.execute(
                sql.SQL(
                    "CREATE DATABASE {} TEMPLATE template0 ENCODING 'UTF8' "
                    "LC_COLLATE 'English_India.1252' LC_CTYPE 'English_India.1252'"
                ).format(sql.Identifier(name))
            )
        else:
            admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    url = make_conninfo(postgres["admin"], dbname=name)
    with psycopg.connect(url) as db:
        db.execute("CREATE SCHEMA brain")
        db.execute("CREATE TABLE brain.notes(id bigserial PRIMARY KEY,body text NOT NULL)")
        db.execute(
            "CREATE TABLE brain.links(source bigint REFERENCES brain.notes(id),target bigint REFERENCES brain.notes(id))"
        )
        db.execute(
            "INSERT INTO brain.notes(body) VALUES ('Synthetic ünicode\nsecond line'),('Related synthetic note')"
        )
        db.execute("INSERT INTO brain.links VALUES (1,2)")
        db.execute("SELECT nextval('brain.notes_id_seq')")
        db.execute("CREATE VIEW brain.note_view AS SELECT id,body FROM brain.notes")
        db.execute(
            "CREATE FUNCTION brain.preview() RETURNS text LANGUAGE sql SECURITY DEFINER AS 'SELECT body FROM brain.notes WHERE id=1'"
        )
    try:
        yield url
    finally:
        with psycopg.connect(postgres["admin"], autocommit=True) as admin:
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))


@pytest.mark.slow  # > 40 s (timed 2026-11-22); CI only, not gates
def test_copy_preserves_data_definitions_roles_and_future_migration_boundaries(
    postgres, brain_source, tmp_path, setup, monkeypatch
):
    binary = Path(
        shutil.which("pg_dump") or "C:/Program Files/PostgreSQL/18/bin/pg_dump.exe"
    ).parent
    name = "yggdras_unified_test_" + secrets.token_hex(5)
    with psycopg.connect(postgres["admin"]) as db:
        app_before = fingerprints(db)
    with psycopg.connect(brain_source) as db:
        brain_before = fingerprints(db)
        brain_text = text_settings(db)
    copied = None
    home = tmp_path / "runtime"
    archive = home / "backups" / "copy"
    try:
        copied = prepare(
            postgres["admin"],
            postgres["runtime"],
            brain_source,
            binary,
            archive,
            name,
        )
        assert copied["storage_layout"] == LAYOUT
        assert all(
            copied["report"][key]
            for key in (
                "source_backups_verified",
                "combined_backup_verified",
                "schema_definitions_preserved",
                "source_records_preserved",
                "role_boundaries_verified",
            )
        )
        assert not copied["report"]["activated"]
        assert verify_boundaries(
            copied["admin_url"],
            copied["database_url"],
            copied["migration_url"],
            copied["brain_url"],
        )
        with psycopg.connect(copied["admin_url"]) as db:
            assert brain_snapshot(fingerprints(db)) == brain_snapshot(brain_before)
            assert text_settings(db) == brain_text
            assert _source_guard(db, "brain", shared=True) == brain_before
        with psycopg.connect(postgres["admin"]) as db:
            assert fingerprints(db) == app_before
        with psycopg.connect(brain_source) as db:
            assert fingerprints(db) == brain_before
        # A process-start failure restores both real private configuration files.
        # Database connections/permissions are real; no actual service is spawned.
        brain_env = home / "brain.env"
        brain_raw = ("BRAIN_DATABASE_URL='" + brain_source + "'\nOTHER=preserved\n").encode()
        brain_env.write_bytes(brain_raw)
        config_raw = json.dumps(
            {
                "admin_url": postgres["admin"],
                "database_url": postgres["runtime"],
                "brain_env": str(brain_env),
                "postgres_bin": str(binary),
            }
        ).encode()
        (home / "runtime.json").write_bytes(config_raw)
        copied["runtime_sha256"] = hashlib.sha256(config_raw).hexdigest()
        copied["brain_environment_sha256"] = hashlib.sha256(brain_raw).hexdigest()
        (archive / "runtime-before.json").write_bytes(config_raw)
        (archive / "brain-before.env").write_bytes(brain_raw)
        (archive / "prepared.json").write_text(json.dumps(copied))
        (home / "consolidation.json").write_text(
            json.dumps({"archive": str(archive), "state": "prepared"})
        )
        (home / "maintenance.json").write_text("{}")
        starts = iter(({"ready": False}, {"ready": True}))
        monkeypatch.setattr(local_consolidation, "ensure", lambda _: next(starts))
        monkeypatch.setattr(local_consolidation, "_stop_application", lambda _: None)
        monkeypatch.setattr(local_consolidation, "_stop_brain_launcher", lambda _: None)
        monkeypatch.setattr(local_consolidation, "pg_start", lambda *_: None)
        with pytest.raises(ConsolidationError, match="did not become ready"):
            local_consolidation.activate_local(home)
        assert (home / "runtime.json").read_bytes() == config_raw
        assert brain_env.read_bytes() == brain_raw
        assert json.loads((home / "consolidation.json").read_text())["state"] == "rolled_back"
        # A healthy website with an unreadable Brain is also a failed cutover.
        (home / "consolidation.json").write_text(
            json.dumps({"archive": str(archive), "state": "prepared"})
        )
        (home / "maintenance.json").write_text("{}")
        monkeypatch.setattr(local_consolidation, "ensure", lambda _: {"ready": True})

        def unavailable(*_):
            raise NotesError(503, "Synthetic unavailable Brain")

        monkeypatch.setattr(
            local_consolidation, "brain_http", lambda _: SimpleNamespace(call=unavailable)
        )
        monkeypatch.setattr(local_consolidation.time, "sleep", lambda _: None)
        with pytest.raises(ConsolidationError, match="Brain API did not become readable"):
            local_consolidation.activate_local(home)
        assert (home / "runtime.json").read_bytes() == config_raw
        assert brain_env.read_bytes() == brain_raw
        # Exercise application writes under the Brain's locale in the combined
        # database, then reload through a fresh service instance.
        _, _, password, settings = setup
        settings = replace(settings, database_url=copied["database_url"])
        client = TestClient(create_app(settings), base_url=settings.origin)
        login = client.post(
            "/v1/auth/login",
            json={"password": password},
            headers={"Origin": settings.origin, "X-Yggdress-Login": "1"},
        )
        assert login.status_code == 200
        client.headers.update({"Origin": settings.origin, "X-Yggdress-CSRF": login.json()["csrf"]})
        response = client.post(
            "/v1/application/tasks",
            json={"title": "Übung – synthetic task", "area": "work", "date": "2030-03-01"},
        )
        assert response.status_code == 201, response.text
        task = response.json()["task"]
        assert task["title"] == "\u00dcbung \u2013 synthetic task"
        assert (
            client.patch("/v1/application/tasks/" + task["id"], json={"done": True}).status_code
            == 200
        )
        reloaded = TestClient(create_app(settings), base_url=settings.origin)
        reloaded.cookies.update(client.cookies)
        assert reloaded.get("/v1/application/tasks").json()["tasks"][0]["done"]
        with psycopg.connect(copied["database_url"]) as db:
            assert db.execute("SELECT count(*) FROM app.chat_conversations").fetchone()[0] >= 0
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                db.execute("SELECT * FROM brain.notes")
        with (
            psycopg.connect(copied["database_url"]) as db,
            pytest.raises(psycopg.errors.InsufficientPrivilege),
        ):
            db.execute("SELECT brain.preview()")
        with (
            psycopg.connect(copied["database_url"]) as db,
            pytest.raises(psycopg.errors.InsufficientPrivilege),
        ):
            db.execute("CREATE TABLE app.runtime_must_not_create(id int)")
        with psycopg.connect(copied["brain_url"]) as db:
            assert db.execute("SELECT brain.preview()").fetchone()[0].startswith("Synthetic")
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                db.execute("SELECT * FROM app.chat_messages")
        Database(copied["migration_url"]).migrate()
        with psycopg.connect(copied["migration_url"]) as db:
            db.execute("CREATE TABLE app.synthetic_future_migration(id int)")
            db.execute(
                "CREATE FUNCTION app.future_function() RETURNS int LANGUAGE sql AS 'SELECT 1'"
            )
        with psycopg.connect(copied["admin_url"]) as db:
            assert not db.execute(
                "SELECT has_function_privilege(%s,'app.future_function()','EXECUTE')",
                (conninfo_to_dict(copied["brain_url"])["user"],),
            ).fetchone()[0]
            assert brain_snapshot(fingerprints(db)) == brain_snapshot(brain_before)
        with (
            psycopg.connect(copied["migration_url"]) as db,
            pytest.raises(psycopg.errors.InsufficientPrivilege),
        ):
            db.execute("DROP TABLE brain.links")
        with pytest.raises(ConsolidationError, match="already exists"):
            prepare(
                postgres["admin"],
                postgres["runtime"],
                brain_source,
                binary,
                tmp_path / "must-not-create",
                name,
            )
        assert not (tmp_path / "must-not-create").exists()
    finally:
        # This entire cluster is test-owned. Clean a partial destination as well
        # so an expected restore failure cannot leave the fixture role in use.
        with psycopg.connect(postgres["admin"], autocommit=True) as db:
            db.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name))
            )
            roles = db.execute(
                "SELECT rolname FROM pg_roles WHERE rolname LIKE 'ygg_app_owner_%' OR rolname LIKE 'ygg_brain_%'"
            ).fetchall()
            for (role,) in roles:
                db.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))


def test_extra_schema_and_public_objects_are_rejected(brain_source):
    with psycopg.connect(brain_source) as db:
        db.execute("CREATE SCHEMA unexpected")
        with pytest.raises(ConsolidationError, match="Source schemas"):
            _source_guard(db, "brain")
        db.rollback()
        db.execute("CREATE TABLE public.must_not_omit(id int)")
        with pytest.raises(ConsolidationError, match="Public schema objects"):
            _source_guard(db, "brain")


def test_large_objects_are_rejected(brain_source):
    with psycopg.connect(brain_source) as db:
        db.execute("SELECT lo_from_bytea(0,'synthetic'::bytea)")
        with pytest.raises(ConsolidationError, match="Large objects"):
            _source_guard(db, "brain")


def test_shared_layout_requires_a_distinct_migration_role():
    admin = "host=localhost port=5432 dbname=synthetic user=admin"
    assert migration_connection({"admin_url": admin}) == admin
    with pytest.raises(ConsolidationError, match="requires an application-only"):
        migration_connection({"admin_url": admin, "storage_layout": LAYOUT})
    with pytest.raises(ConsolidationError, match="separate role"):
        migration_connection({"admin_url": admin, "storage_layout": LAYOUT, "migration_url": admin})
    with pytest.raises(ConsolidationError, match="same database"):
        migration_connection(
            {
                "admin_url": admin,
                "storage_layout": LAYOUT,
                "migration_url": "host=localhost port=5432 dbname=other user=migrate",
            }
        )


def test_private_environment_update_preserves_other_settings_and_line_endings():
    original = b"\xef\xbb\xbf# private\r\nBRAIN_DATABASE_URL='old'\r\nUNCHANGED=keep\r\n"
    changed = local_consolidation.replace_brain_connection(
        original, "host=localhost dbname=combined"
    )
    assert changed == original.replace(b"'old'", b"'host=localhost dbname=combined'")
    for value in (b"OTHER=keep\n", b"BRAIN_DATABASE_URL=one\nBRAIN_DATABASE_URL=two\n"):
        with pytest.raises(ConsolidationError, match="exactly one"):
            local_consolidation.replace_brain_connection(value, "synthetic")


def test_fingerprints_are_independent_of_session_timezone(postgres):
    with psycopg.connect(postgres["admin"]) as db:
        db.execute("SET TIME ZONE 'Pacific/Auckland'")
        expected = fingerprints(db)
        db.execute("SET TIME ZONE 'America/New_York'")
        assert fingerprints(db) == expected
