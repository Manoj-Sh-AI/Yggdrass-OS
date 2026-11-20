"""Real app-only import, least privilege and restart persistence; no Brain calls."""

import json
from pathlib import Path

import psycopg
import pytest
from psycopg.conninfo import conninfo_to_dict

from yggdress_app.backup import tool
from yggdress_app.database import Database
from yggdress_app.local_runtime import pg_binary, pg_start, provision
from yggdress_app.security import password_hash


def test_verified_import_restart_and_reprovision_refusal(postgres, tmp_path):
    project = Path(__file__).resolve().parents[2]
    web = project / "web"
    binary = Path("C:/Program Files/PostgreSQL/18/bin")
    if not binary.is_dir() or not (web / ".next-desktop/BUILD_ID").exists():
        pytest.skip("Local PostgreSQL tools and a desktop candidate build are required.")
    home = tmp_path / "owned-application"
    with Database(postgres["admin"]).connect() as db:
        db.execute(
            "INSERT INTO app.chat_conversations(title) VALUES ('Synthetic persistent conversation')"
        )
    hashed = password_hash("synthetic-test-password")
    report = provision(
        home, postgres["admin"], binary, hashed, tmp_path / "no-brain.env", web, ".next-desktop"
    )
    config = json.loads((home / "runtime.json").read_text())
    try:
        assert report == {"backup_verified": True, "existing_records_preserved": True}
        assert config["password_hash"] == hashed and "password" not in config
        assert conninfo_to_dict(config["database_url"])["host"] == "127.0.0.1"
        with Database(config["database_url"]).connect() as db:
            assert (
                db.execute(
                    "SELECT title FROM app.chat_conversations ORDER BY created_at DESC LIMIT 1"
                ).fetchone()["title"]
                == "Synthetic persistent conversation"
            )
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                db.execute("CREATE TABLE app.should_not_exist(id int)")
        tool(
            pg_binary(config, "pg_ctl"),
            ["-D", home / "postgres", "-m", "fast", "-w", "stop"],
            capture=False,
        )
        pg_start(home, config)
        with Database(config["database_url"]).connect() as db:
            assert (
                db.execute(
                    "SELECT count(*) AS n FROM app.chat_conversations WHERE title='Synthetic persistent conversation'"
                ).fetchone()["n"]
                >= 1
            )
            assert db.execute("SELECT to_regnamespace('brain') AS name").fetchone()["name"] is None
        with pytest.raises(RuntimeError, match="Already provisioned"):
            provision(
                home,
                postgres["admin"],
                binary,
                hashed,
                tmp_path / "no-brain.env",
                web,
                ".next-desktop",
            )
    finally:
        tool(
            pg_binary(config, "pg_ctl"),
            ["-D", home / "postgres", "-m", "fast", "-w", "stop"],
            capture=False,
        )


def test_stopping_a_child_also_stops_what_it_started(tmp_path):
    """A .venv python.exe on Windows is a launcher whose real interpreter is its child;
    terminate() alone left the brain service, voice worker and web server running."""
    import subprocess
    import sys
    import time

    from yggdress_app.local_runtime import quietly, stop_tree

    marker = tmp_path / "grandchild.pid"
    launcher = subprocess.Popen(
        [sys.executable, "-c",
         ("import subprocess, sys, time; "
          "c = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)']); "
          f"open(r'{marker}', 'w').write(str(c.pid)); time.sleep(120)")],
    )  # fmt: skip
    for _ in range(100):
        if marker.exists() and marker.read_text():
            break
        time.sleep(0.1)
    grandchild = int(marker.read_text())
    stop_tree(launcher)
    assert launcher.poll() is not None

    def alive(pid):
        if sys.platform == "win32":
            out = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}"], check=False, capture_output=True, text=True
            )
            return str(pid) in out.stdout
        import os

        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True

    for _ in range(50):
        if not alive(grandchild):
            break
        time.sleep(0.1)
    assert not alive(grandchild)
    stop_tree(None)  # nothing to stop is fine
    quietly(lambda: 1 / 0)  # a failing shutdown step never raises
