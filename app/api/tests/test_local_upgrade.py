import json

import psycopg
import pytest

from yggdress_app.local_runtime import ensure
from yggdress_app.local_upgrade import columns, projection, upgrade


def test_original_column_projection_detects_changes_but_allows_additive_metadata(postgres):
    with psycopg.connect(postgres["admin"]) as db:
        try:
            db.execute(
                "CREATE TABLE app.projection_fixture(id integer PRIMARY KEY, title text, happened_at timestamptz)"
            )
            db.execute(
                "INSERT INTO app.projection_fixture VALUES (1,'Keep the original value','2030-01-02T12:00:00+01:00')"
            )
            spec = {"projection_fixture": columns(db)["projection_fixture"]}
            before = projection(db, spec)
            db.execute("ALTER TABLE app.projection_fixture ADD COLUMN metadata text DEFAULT 'new'")
            assert projection(db, spec) == before
            db.execute("UPDATE app.projection_fixture SET title='Different value'")
            assert projection(db, spec) != before
        finally:
            db.execute("DROP TABLE app.projection_fixture")


def test_maintenance_does_not_start_or_adopt_a_service(tmp_path):
    (tmp_path / "maintenance.json").write_text("{}")
    with pytest.raises(RuntimeError, match="update is in progress"):
        ensure(tmp_path)


def test_upgrade_refuses_the_active_build_before_connecting(tmp_path):
    (tmp_path / "runtime.json").write_text(
        json.dumps({"web": str(tmp_path), "build_dir": ".next-active"})
    )
    with pytest.raises(RuntimeError, match="separate verified"):
        upgrade(tmp_path, ".next-active")
