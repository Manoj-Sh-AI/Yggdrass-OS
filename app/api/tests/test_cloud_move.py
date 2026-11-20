"""Moving the database to Supabase: schema-scoped backups, nightly backups, the hosted
(remote) database mode and the read-only check. Isolated local clusters only."""

from datetime import datetime
from pathlib import Path

import psycopg
import pytest

from yggdress_app import local_runtime
from yggdress_app.backup import database_backup, fingerprints
from yggdress_app.cloud_move import admin_url, check


def test_fingerprints_and_backups_can_be_limited_to_the_apps_schemas(postgres, tmp_path):
    with psycopg.connect(postgres["admin"], autocommit=True) as db:
        db.execute("CREATE SCHEMA IF NOT EXISTS host_owned")
        db.execute("CREATE TABLE IF NOT EXISTS host_owned.invented(id int)")
        db.execute("INSERT INTO host_owned.invented VALUES (1)")
        scoped = fingerprints(db, ["app"])
        everything = fingerprints(db)
    assert scoped["tables"] and all(k.startswith("app.") for k in scoped["tables"])
    assert "host_owned.invented" in everything["tables"]
    pg_dump = Path(
        local_runtime.shutil.which("pg_dump") or "C:/Program Files/PostgreSQL/18/bin/pg_dump.exe"
    )
    try:
        report = database_backup(
            postgres["admin"], tmp_path / "scoped.dump", pg_dump.parent, tmp_path, schemas=["app"]
        )
    finally:
        with psycopg.connect(postgres["admin"], autocommit=True) as db:
            db.execute("DROP SCHEMA host_owned CASCADE")  # leave the shared fixture as found
    assert report["status"] == "restore_verified" and report["scope"] == "schemas app"
    assert "host_owned.invented" not in report["snapshot"]["tables"]


def test_one_verified_nightly_backup_after_3am_kept_14_days(tmp_path, monkeypatch):
    made = []

    def fake_backup(url, target, binary, work, schemas=None):
        made.append(schemas)
        Path(target).write_bytes(b"dump")
        return {"status": "restore_verified"}

    monkeypatch.setattr("yggdress_app.backup.database_backup", fake_backup)
    folder = tmp_path / "backups"
    folder.mkdir()
    (folder / "nightly-20301001.dump").write_bytes(b"old")  # older than 14 days
    (folder / "nightly-20301105.dump").write_bytes(b"recent")
    config = {"admin_url": "x", "postgres_bin": str(tmp_path), "database_host": "remote"}
    assert local_runtime.nightly_backup(tmp_path, config, datetime(2030, 11, 10, 2, 30)) is None
    first = local_runtime.nightly_backup(tmp_path, config, datetime(2030, 11, 10, 3, 5))
    again = local_runtime.nightly_backup(tmp_path, config, datetime(2030, 11, 10, 23, 0))
    assert first.name == "nightly-20301110.dump" and again is None
    assert made == [["app", "brain"]]  # hosted: only the app's own schemas
    names = sorted(p.name for p in folder.glob("nightly-*.dump"))
    assert names == ["nightly-20301105.dump", "nightly-20301110.dump"]
    assert (folder / "nightly-latest.json").is_file()


def test_a_hosted_database_is_verified_and_never_started_as_a_local_cluster(postgres, monkeypatch):
    monkeypatch.setattr(local_runtime, "pg_start", lambda *a: pytest.fail("local cluster used"))
    config = {"admin_url": postgres["admin"], "database_host": "remote"}
    with psycopg.connect(postgres["admin"], autocommit=True) as db:
        had_brain = db.execute("SELECT to_regnamespace('brain')").fetchone()[0] is not None
    if not had_brain:
        with pytest.raises(RuntimeError, match="does not hold the application schemas"):
            local_runtime.db_start(Path("."), config)
        with psycopg.connect(postgres["admin"], autocommit=True) as db:
            db.execute("CREATE SCHEMA brain")
    try:
        local_runtime.db_start(Path("."), config)
    finally:
        if not had_brain:  # leave the shared fixture as found
            with psycopg.connect(postgres["admin"], autocommit=True) as db:
                db.execute("DROP SCHEMA brain")
    assert local_runtime.remote(config) and not local_runtime.remote({})


def test_the_check_refuses_the_ipv6_only_host_and_reads_facts_only(postgres, tmp_path):
    with pytest.raises(SystemExit, match="first"):
        admin_url(tmp_path)
    (tmp_path / "supabase-admin.url").write_text(
        "postgresql://postgres:x@db.example123.supabase.co:5432/postgres"
    )
    with pytest.raises(SystemExit, match="IPv6-only"):
        admin_url(tmp_path)
    facts = check(postgres["admin"])
    assert facts["version_ok"] and facts["encoding"] == "UTF8"
    assert facts["app_schemas_exposed"] == []


def test_install_recreates_owners_data_and_isolated_grants_in_a_hosted_database(postgres, tmp_path):
    """The cutover's core, between two throwaway databases: each schema is restored by
    its own owner, the runtime role keeps exactly its grants, nothing crosses schemas."""
    from uuid import uuid4

    from psycopg.conninfo import make_conninfo

    from yggdress_app.cloud_move import install, isolated, login, read_brain_url, write_brain_url

    tag = uuid4().hex[:8]
    src, dst = f"cut_src_{tag}", f"cut_dst_{tag}"
    roles = {"app": f"cut_app_{tag}", "brain": f"cut_brain_{tag}", "runtime": f"cut_rt_{tag}"}
    admin = postgres["admin"]
    with psycopg.connect(admin, autocommit=True) as db:
        db.execute(f'CREATE DATABASE "{src}"')
        db.execute(f'CREATE DATABASE "{dst}"')
        db.execute(f'CREATE ROLE "{roles["runtime"]}" LOGIN')
    src_url, dst_url = make_conninfo(admin, dbname=src), make_conninfo(admin, dbname=dst)
    try:
        with psycopg.connect(src_url, autocommit=True) as db:
            db.execute("CREATE SCHEMA app; CREATE SCHEMA brain")
            db.execute("CREATE TABLE app.tasks(id serial PRIMARY KEY, title text)")
            db.execute("INSERT INTO app.tasks(title) VALUES ('Invented one'),('Invented two')")
            db.execute("CREATE TABLE brain.notes(slug text PRIMARY KEY, body text)")
            db.execute("INSERT INTO brain.notes VALUES ('invented-note','A fact.')")
            db.execute(f'GRANT USAGE ON SCHEMA app TO "{roles["runtime"]}"')
            db.execute(f'GRANT SELECT,INSERT ON app.tasks TO "{roles["runtime"]}"')
            db.execute(f'GRANT UPDATE(title) ON app.tasks TO "{roles["runtime"]}"')
        pg_dump = Path(
            local_runtime.shutil.which("pg_dump")
            or "C:/Program Files/PostgreSQL/18/bin/pg_dump.exe"
        )
        report = database_backup(src_url, tmp_path / "cut.dump", pg_dump.parent, tmp_path,
                                 schemas=["app", "brain"])  # fmt: skip
        urls = install(dst_url, src_url, tmp_path / "cut.dump", pg_dump.parent, roles)
        with psycopg.connect(dst_url) as db:
            copied = fingerprints(db, ["app", "brain"])
            owners = dict(db.execute(
                "SELECT nspname, pg_get_userbyid(nspowner) FROM pg_namespace "
                "WHERE nspname IN ('app','brain')").fetchall())  # fmt: skip
        assert copied["tables"] == report["snapshot"]["tables"]
        assert owners == {"app": roles["app"], "brain": roles["brain"]}
        isolated(urls, roles)
        with psycopg.connect(urls["runtime"]) as db:
            assert db.execute("SELECT count(*) FROM app.tasks").fetchone()[0] == 2
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                db.execute("SELECT * FROM brain.notes")
        with psycopg.connect(urls["brain"]) as db:
            assert db.execute("SELECT slug FROM brain.notes").fetchone()[0] == "invented-note"
    finally:
        with psycopg.connect(admin, autocommit=True) as db:
            for name in (src, dst):
                db.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
            for role in roles.values():
                db.execute(f'DROP ROLE IF EXISTS "{role}"')
    assert login("user=postgres.abc123 host=x", "ygg_brain") == "ygg_brain.abc123"
    assert login("user=postgres host=x", "ygg_brain") == "ygg_brain"
    env = tmp_path / ".env"
    env.write_text("OTHER=1\nBRAIN_DATABASE_URL='user=a password=b'\nLAST=2\n", encoding="utf-8")
    write_brain_url(env, "user=c password=d host=e")
    assert read_brain_url(env) == "user=c password=d host=e"
    assert env.read_text(encoding="utf-8").splitlines()[0::2] == ["OTHER=1", "LAST=2"]
