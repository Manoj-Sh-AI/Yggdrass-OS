import pytest

from scripts.local_preview import preview_password, preview_restore_list


def test_preview_restore_retains_business_records_without_replaying_login_and_migrations():
    listing = """; Archive listing
1; 0 1 TABLE DATA app login_guard fixture
2; 0 2 TABLE DATA app sessions fixture
3; 0 3 TABLE DATA app schema_migrations fixture
4; 0 4 TABLE DATA app tasks fixture
5; 0 5 TABLE DATA app routine_progress fixture
6; 0 6 TABLE DATA app task_history fixture
7; 0 7 SEQUENCE SET app task_history_id_seq fixture
"""
    actual = preview_restore_list(listing)
    assert "login_guard fixture" not in actual
    assert "sessions fixture" not in actual
    assert "schema_migrations fixture" not in actual
    assert "TABLE DATA app tasks fixture" in actual
    assert "TABLE DATA app routine_progress fixture" in actual
    assert "TABLE DATA app task_history fixture" in actual
    assert "SEQUENCE SET app task_history_id_seq fixture" in actual


def test_private_preview_password_can_be_preserved_without_changing_auth(monkeypatch):
    monkeypatch.delenv("YGGDRESS_PREVIEW_PASSWORD", raising=False)
    assert len(preview_password()) >= 32
    monkeypatch.setenv("YGGDRESS_PREVIEW_PASSWORD", "an-invented-preview-password")
    assert preview_password() == "an-invented-preview-password"
    monkeypatch.setenv("YGGDRESS_PREVIEW_PASSWORD", "short")
    with pytest.raises(ValueError, match="at least 24"):
        preview_password()


@pytest.mark.slow  # > 40 s (timed 2026-11-22); CI only, not gates
def test_data_restore_preserves_connections_and_journal_without_reemitting(
    signed_in, postgres, tmp_path
):
    import shutil
    import subprocess
    from pathlib import Path
    from uuid import uuid4

    from notes_fixture import SyntheticBrain
    from postgres_fixture import isolated_database

    from yggdress_app.database import Database

    client, app, settings = signed_in
    app.state.notes_proxy.http = SyntheticBrain()
    response = client.post(
        "/v1/application/planning/commands",
        json={
            "key": str(uuid4()),
            "op": "task.create",
            "data": {"title": "Synthetic restore", "objective": "Preserve original history"},
        },
    )
    assert response.status_code == 200
    created = response.json()
    attached = client.post(
        "/v1/application/connections/commands",
        json={
            "key": str(uuid4()),
            "operation": "task.link_note",
            "entity_id": created["id"],
            "version": created["version"],
            "note_slug": "sample",
        },
    )
    assert attached.status_code == 200
    with Database(settings.database_url).connect() as db:
        before = db.execute(
            "SELECT event_id,entity_id,detail FROM app.workspace_changes ORDER BY sequence"
        ).fetchall()
    pg_dump = Path(shutil.which("pg_dump") or "C:/Program Files/PostgreSQL/18/bin/pg_dump.exe")
    pg_restore = pg_dump.with_name("pg_restore.exe" if pg_dump.suffix == ".exe" else "pg_restore")
    dump = tmp_path / "application.dump"
    subprocess.run(
        [
            str(pg_dump),
            "--data-only",
            "--schema=app",
            "--format=custom",
            "--file",
            str(dump),
            "--dbname",
            postgres["admin"],
        ],
        check=True,
        capture_output=True,
    )
    listing = subprocess.run(
        [str(pg_restore), "--list", str(dump)], check=True, capture_output=True, text=True
    ).stdout
    restore_list = tmp_path / "restore.list"
    restore_list.write_text(preview_restore_list(listing), encoding="utf-8")
    with isolated_database() as restored:
        subprocess.run(
            [
                str(pg_restore),
                "--data-only",
                "--disable-triggers",
                "--single-transaction",
                "--exit-on-error",
                "--use-list",
                str(restore_list),
                "--dbname",
                restored["admin"],
                str(dump),
            ],
            check=True,
            capture_output=True,
        )
        with Database(restored["runtime"]).connect() as db:
            after = db.execute(
                "SELECT event_id,entity_id,detail FROM app.workspace_changes ORDER BY sequence"
            ).fetchall()
            assert after == before
            assert db.execute("SELECT count(*) AS n FROM app.task_note_links").fetchone()["n"] == 1
            assert (
                db.execute("SELECT objective FROM app.tasks").fetchone()["objective"]
                == "Preserve original history"
            )
