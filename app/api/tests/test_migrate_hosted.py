"""migrate_hosted brings a hosted database that stopped at an older migration up to date,
the way production stopped at 014 (2026-11-23): backup first, tables owned by the app
schema's owner, the app role granted, nothing lost, safe to run twice."""

import shutil

import psycopg
import pytest
from postgres_fixture import isolated_database
from psycopg.conninfo import make_conninfo

from yggdress_app import migrate_hosted
from yggdress_app.database import Database


def test_destructive_migrations_are_recognised_and_comments_ignored():
    assert migrate_hosted.DESTRUCTIVE.search("ALTER TABLE app.t RENAME COLUMN a TO b")
    assert migrate_hosted.DESTRUCTIVE.search("drop table app.t")
    text = "-- DROP TABLE app.t is only mentioned\nCREATE TABLE app.t (id int);"
    assert not migrate_hosted.DESTRUCTIVE.search(migrate_hosted.without_comments(text))


def test_every_shipped_migration_after_014_is_additive():
    late = [p for p in migrate_hosted.migration_files() if int(p.name[:3]) > 14]
    assert late and not [
        p.name
        for p in late
        if migrate_hosted.DESTRUCTIVE.search(
            migrate_hosted.without_comments(p.read_text(encoding="utf-8"))
        )
    ]


@pytest.fixture
def hosted_copy(tmp_path, monkeypatch):
    """A database like production: app schema owned by its own role, migrated to 014,
    one app login role with only the grants that existed then."""
    with isolated_database() as cluster:
        admin = cluster["admin"]
        with psycopg.connect(admin, autocommit=True) as db:
            db.execute("CREATE DATABASE yggdress_test_hosted_copy")
            db.execute("CREATE ROLE app_owner_t NOLOGIN")
            db.execute("CREATE ROLE app_runtime_t LOGIN PASSWORD 'invented-test-only'")
        url = make_conninfo(admin, dbname="yggdress_test_hosted_copy")
        with psycopg.connect(url, autocommit=True) as db:
            db.execute("CREATE SCHEMA app AUTHORIZATION app_owner_t")
        old = tmp_path / "migrations-to-014"
        old.mkdir()
        for path in Database.migration_folder().glob("*.sql"):
            if int(path.name[:3]) <= 14:
                shutil.copy(path, old / path.name)
        # As cloud_move.install did: the owner may create in the database only while
        # building it (migration 001 runs CREATE SCHEMA IF NOT EXISTS), then not again.
        with psycopg.connect(admin, autocommit=True) as db:
            db.execute("GRANT CREATE ON DATABASE yggdress_test_hosted_copy TO app_owner_t")
        with monkeypatch.context() as patch:
            patch.setattr(Database, "migration_folder", staticmethod(lambda: old))
            Database(url).migrate(role="app_owner_t")
        with psycopg.connect(admin, autocommit=True) as db:
            db.execute("REVOKE CREATE ON DATABASE yggdress_test_hosted_copy FROM app_owner_t")
        with psycopg.connect(url, autocommit=True) as db:
            db.execute("GRANT USAGE ON SCHEMA app TO app_runtime_t")
            db.execute("GRANT SELECT,UPDATE ON app.login_guard TO app_runtime_t")
        yield url


@pytest.mark.slow  # starts a scratch cluster and a verified backup
def test_apply_backs_up_migrates_as_owner_grants_and_is_safe_to_rerun(hosted_copy, tmp_path):
    url = hosted_copy
    plan = migrate_hosted.plan(url)
    late = [p.name for p in migrate_hosted.migration_files() if int(p.name[:3]) > 14]
    assert plan["pending"] == late and plan["destructive"] == []
    assert (plan["owner_role"], plan["runtime_role"]) == ("app_owner_t", "app_runtime_t")

    out = migrate_hosted.apply(url, tmp_path / "backups")
    assert out["applied"] == late and out["still_pending"] == []
    assert (tmp_path / "backups" / out["backup"]).stat().st_size > 0

    with psycopg.connect(url) as db:
        owners = {
            r[0]
            for r in db.execute(
                "SELECT tableowner FROM pg_tables WHERE schemaname='app'"
            ).fetchall()
        }
        assert owners == {"app_owner_t"}  # new tables belong to the same owner as old ones
        for table, privilege in (("app.conductor_runs", "INSERT"),
                                 ("app.daily_routine_settings", "SELECT"),
                                 ("app.scheduled_jobs", "UPDATE")):  # fmt: skip
            assert db.execute(
                "SELECT has_table_privilege('app_runtime_t', %s, %s)", (table, privilege)
            ).fetchone()[0], (table, privilege)

    again = migrate_hosted.apply(url, tmp_path / "backups")
    assert again["applied"] == [] and again["backup"] is None and again["still_pending"] == []


def test_more_than_one_candidate_app_role_needs_a_name(hosted_copy):
    with psycopg.connect(hosted_copy, autocommit=True) as db:
        db.execute("CREATE ROLE app_runtime_two LOGIN")
        db.execute("GRANT USAGE ON SCHEMA app TO app_runtime_two")
        db.execute("GRANT SELECT ON app.login_guard TO app_runtime_two")
    with pytest.raises(SystemExit, match="--runtime-role"):
        migrate_hosted.plan(hosted_copy)
    assert migrate_hosted.plan(hosted_copy, "app_runtime_t")["runtime_role"] == "app_runtime_t"


def test_a_missing_admin_file_stops_without_touching_anything(tmp_path):
    with pytest.raises(SystemExit, match="railway admin connection"):
        migrate_hosted.main(["plan", "--home", str(tmp_path)])
