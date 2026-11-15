import json
import os
import zipfile
from pathlib import Path

import pytest

from yggdress_app.backup import (
    BackupError,
    client_environment,
    markdown_archive,
    publish,
    sha256,
    tool,
    verify_markdown,
)


def test_full_database_restore_matches_schema_rows_sequences_and_large_objects(postgres, tmp_path):
    import shutil

    import psycopg

    from yggdress_app.backup import database_backup

    with psycopg.connect(postgres["admin"]) as connection:
        connection.execute("CREATE SCHEMA backup_fixture")
        connection.execute(
            "CREATE TABLE backup_fixture.observations (id bigserial PRIMARY KEY, body text, score numeric(10,3), details jsonb, raw bytea)"
        )
        connection.execute(
            "INSERT INTO backup_fixture.observations(body,score,details,raw) VALUES (%s,%s,%s,%s)",
            ("Invented ünicode\nsecond line", "1.230", '{"invented": true}', b"\x00fake-data"),
        )
        connection.execute(
            "CREATE MATERIALIZED VIEW backup_fixture.preview AS SELECT id,body FROM backup_fixture.observations"
        )
        connection.execute("SELECT nextval('backup_fixture.observations_id_seq')")
        connection.execute("SELECT lo_from_bytea(0,%s)", (b"synthetic large object",))
    pg_dump = Path(shutil.which("pg_dump") or "C:/Program Files/PostgreSQL/18/bin/pg_dump.exe")
    outcome = database_backup(
        postgres["admin"], tmp_path / "invented.dump", pg_dump.parent, tmp_path
    )
    assert outcome["status"] == "restore_verified"
    assert outcome["snapshot"]["tables"]["backup_fixture.observations"]["rows"] == 1
    assert outcome["snapshot"]["tables"]["backup_fixture.preview"]["rows"] == 1
    assert outcome["snapshot"]["sequences"]["backup_fixture.observations_id_seq"] == [2, True]
    assert len(outcome["snapshot"]["large_objects"]) == 1


def test_markdown_archive_preserves_bytes_and_excludes_dependencies(tmp_path):
    root = tmp_path / "invented-brain"
    (root / "library").mkdir(parents=True)
    original = b"# Invented\r\n\nA fact: \xc3\xbc.\r\n"
    (root / "library/note.md").write_bytes(original)
    (root / "README.MD").write_text("Original README")
    (root / ".env").write_text("synthetic secret, not Markdown")
    (root / "node_modules").mkdir()
    (root / "node_modules/omit.md").write_text("dependency")
    target = tmp_path / "markdown.zip"
    records = markdown_archive([root], target)
    assert len(records) == 2
    assert (root / "library/note.md").read_bytes() == original
    with zipfile.ZipFile(target) as archive:
        assert archive.read("invented-brain/library/note.md") == original
        assert all("node_modules" not in name and ".env" not in name for name in archive.namelist())
    verify_markdown(target, records)
    with pytest.raises(FileExistsError):
        markdown_archive([root], target)


def test_duplicate_source_names_are_refused(tmp_path):
    roots = [tmp_path / "one/brain", tmp_path / "two/brain"]
    for root in roots:
        root.mkdir(parents=True)
    with pytest.raises(BackupError):
        markdown_archive(roots, tmp_path / "archive.zip")


def test_linked_markdown_is_refused(tmp_path):
    root = tmp_path / "brain"
    root.mkdir()
    outside = tmp_path / "outside.md"
    outside.write_text("outside selected root")
    try:
        (root / "linked.md").symlink_to(outside)
    except OSError:
        pytest.skip("Creating symbolic links is not permitted on this test host")
    with pytest.raises(BackupError):
        markdown_archive([root], tmp_path / "archive.zip")


def test_corrupted_manifest_or_zip_is_not_verified(tmp_path):
    root = tmp_path / "brain"
    root.mkdir()
    (root / "note.md").write_text("invented")
    target = tmp_path / "archive.zip"
    records = markdown_archive([root], target)
    records[0]["sha256"] = "wrong"
    with pytest.raises(BackupError):
        verify_markdown(target, records)


def test_publish_checks_bytes_and_never_overwrites(tmp_path):
    stage = tmp_path / "stage"
    stage.mkdir()
    (stage / "database.dump").write_bytes(b"invented archive")
    (stage / "manifest.json").write_text(json.dumps({"status": "verified"}))
    destination = tmp_path / "cloud-folder"
    final = publish(stage, destination, "dated-snapshot")
    assert sha256(final / "database.dump") == sha256(stage / "database.dump")
    assert not (destination / "dated-snapshot.incomplete").exists()
    with pytest.raises(BackupError):
        publish(stage, destination, "dated-snapshot")


def test_publish_detects_bad_copies_and_leaves_incomplete_label(tmp_path, monkeypatch):
    import shutil

    stage = tmp_path / "stage"
    stage.mkdir()
    (stage / "file").write_text("original")
    copy = shutil.copytree

    def bad_copy(source, target):
        result = copy(source, target)
        (Path(target) / "file").write_text("corrupted")
        return result

    monkeypatch.setattr(shutil, "copytree", bad_copy)
    with pytest.raises(BackupError):
        publish(stage, tmp_path / "cloud", "snapshot")
    assert not (tmp_path / "cloud/snapshot").exists()
    assert (tmp_path / "cloud/snapshot.incomplete").exists()


def test_database_credentials_are_environment_only_and_not_inherited_accidentally(monkeypatch):
    monkeypatch.setenv("PGHOST", "wrong-server")
    monkeypatch.setenv("PGPASSWORD", "wrong-password")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "not-for-postgres")
    env = client_environment(
        "host=127.0.0.1 port=12345 dbname=synthetic user=tester password='has spaces'"
    )
    assert env["PGDATABASE"] == "synthetic" and env["PGPORT"] == "12345"
    assert env["PGPASSWORD"] == "has spaces"
    assert "ANTHROPIC_API_KEY" not in env
    local = client_environment("host=127.0.0.1 port=23456 dbname=postgres user=backup_verify")
    assert "PGPASSWORD" not in local and local["PGPORT"] == "23456"
    assert os.environ["PGHOST"] == "wrong-server"


def test_tool_error_does_not_expose_stderr_or_credentials(monkeypatch):
    class Result:
        returncode = 1
        stdout = b""
        stderr = b"sensitive details that must not be printed"

    monkeypatch.setattr("subprocess.run", lambda *_args, **_kwargs: Result())
    with pytest.raises(BackupError) as error:
        tool(Path("pg_dump"), ["--format=custom"])
    assert "sensitive" not in str(error.value)
