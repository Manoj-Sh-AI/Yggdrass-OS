"""migrate_hosted brings a hosted database that stopped at an older migration up to date,
the way production stopped at 014 (2026-11-23): backup first, tables owned by the app
schema's owner, the app role granted, nothing lost, safe to run twice."""

import shutil
import uuid

import psycopg
import pytest
from postgres_fixture import isolated_database
from psycopg import sql
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
    one app login role with only the grants that existed then. Names are unique per test
    and removed afterwards: in CI every test shares one PostgreSQL service."""
    tag = uuid.uuid4().hex[:10]
    names = {"db": f"yggdress_test_hosted_{tag}", "owner": f"app_owner_{tag}",
             "runtime": f"app_runtime_{tag}", "other": f"app_other_{tag}"}  # fmt: skip
    with isolated_database() as cluster:
        admin = cluster["admin"]
        db_name, owner, runtime = (sql.Identifier(names[k]) for k in ("db", "owner", "runtime"))
        with psycopg.connect(admin, autocommit=True) as db:
            db.execute(sql.SQL("CREATE DATABASE {}").format(db_name))
            db.execute(sql.SQL("CREATE ROLE {} NOLOGIN").format(owner))
            db.execute(
                sql.SQL("CREATE ROLE {} LOGIN PASSWORD 'invented-test-only'").format(runtime)
            )
        url = make_conninfo(admin, dbname=names["db"])
        try:
            with psycopg.connect(url, autocommit=True) as db:
                db.execute(sql.SQL("CREATE SCHEMA app AUTHORIZATION {}").format(owner))
            old = tmp_path / "migrations-to-014"
            old.mkdir()
            for path in Database.migration_folder().glob("*.sql"):
                if int(path.name[:3]) <= 14:
                    shutil.copy(path, old / path.name)
            # As cloud_move.install did: the owner may create in the database only while
            # building it (migration 001 runs CREATE SCHEMA IF NOT EXISTS), then not again.
            with psycopg.connect(admin, autocommit=True) as db:
                db.execute(sql.SQL("GRANT CREATE ON DATABASE {} TO {}").format(db_name, owner))
            with monkeypatch.context() as patch:
                patch.setattr(Database, "migration_folder", staticmethod(lambda: old))
                Database(url).migrate(role=names["owner"])
            with psycopg.connect(admin, autocommit=True) as db:
                db.execute(sql.SQL("REVOKE CREATE ON DATABASE {} FROM {}").format(db_name, owner))
            with psycopg.connect(url, autocommit=True) as db:
                db.execute(sql.SQL("GRANT USAGE ON SCHEMA app TO {}").format(runtime))
                db.execute(sql.SQL("GRANT SELECT,UPDATE ON app.login_guard TO {}").format(runtime))
            yield {"url": url, **names}
        finally:
            with psycopg.connect(admin, autocommit=True) as db:
                db.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(db_name))
                for key in ("other", "runtime", "owner"):
                    db.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(names[key])))


@pytest.mark.slow  # starts a scratch cluster and a verified backup
def test_apply_backs_up_migrates_as_owner_grants_and_is_safe_to_rerun(hosted_copy, tmp_path):
    url = hosted_copy["url"]
    plan = migrate_hosted.plan(url)
    late = [p.name for p in migrate_hosted.migration_files() if int(p.name[:3]) > 14]
    assert plan["pending"] == late and plan["destructive"] == []
    assert (plan["owner_role"], plan["runtime_role"]) == (
        hosted_copy["owner"],
        hosted_copy["runtime"],
    )

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
        assert owners == {hosted_copy["owner"]}  # new tables: same owner as the old ones
        for table, privilege in (("app.conductor_runs", "INSERT"),
                                 ("app.daily_routine_settings", "SELECT"),
                                 ("app.scheduled_jobs", "UPDATE")):  # fmt: skip
            assert db.execute(
                "SELECT has_table_privilege(%s, %s, %s)",
                (hosted_copy["runtime"], table, privilege),
            ).fetchone()[0], (table, privilege)

    again = migrate_hosted.apply(url, tmp_path / "backups")
    assert again["applied"] == [] and again["backup"] is None and again["still_pending"] == []


def test_more_than_one_candidate_app_role_needs_a_name(hosted_copy):
    other = sql.Identifier(hosted_copy["other"])
    with psycopg.connect(hosted_copy["url"], autocommit=True) as db:
        db.execute(sql.SQL("CREATE ROLE {} LOGIN").format(other))
        db.execute(sql.SQL("GRANT USAGE ON SCHEMA app TO {}").format(other))
        db.execute(sql.SQL("GRANT SELECT ON app.login_guard TO {}").format(other))
    with pytest.raises(SystemExit, match="--runtime-role"):
        migrate_hosted.plan(hosted_copy["url"])
    named = migrate_hosted.plan(hosted_copy["url"], hosted_copy["runtime"])
    assert named["runtime_role"] == hosted_copy["runtime"]
    with psycopg.connect(hosted_copy["url"], autocommit=True) as db:
        db.execute(sql.SQL("DROP OWNED BY {}").format(other))  # so the role can be dropped


def test_a_missing_admin_file_stops_without_touching_anything(tmp_path):
    with pytest.raises(SystemExit, match="railway admin connection"):
        migrate_hosted.main(["plan", "--home", str(tmp_path)])
