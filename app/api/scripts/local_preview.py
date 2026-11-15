"""Keep an authenticated, synthetic local preview running. Never uses a personal database."""

import argparse
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from threading import Thread

import uvicorn

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tests")]
from postgres_fixture import free_port, isolated_database

from yggdress_app.application import create_app
from yggdress_app.config import Settings
from yggdress_app.database import Database
from yggdress_app.notes_proxy import BrainNotesHTTP, NotesProxy
from yggdress_app.security import password_hash


def preview_restore_list(listing):
    """Keep fresh login/migration state while restoring saved application records."""
    return (
        "\n".join(
            line
            for line in listing.splitlines()
            if not re.search(r"\bTABLE DATA app (login_guard|sessions|schema_migrations)\b", line)
        )
        + "\n"
    )


def preview_password():
    """Optionally keep the owner's existing local-preview password across a refresh."""
    value = os.environ.get("YGGDRESS_PREVIEW_PASSWORD")
    if value is not None:
        if len(value) < 24:
            raise ValueError("The private preview password must have at least 24 characters.")
        return value
    return secrets.token_urlsafe(32)


def main():
    parser = argparse.ArgumentParser(description="Private synthetic application preview")
    parser.add_argument(
        "--restore-data", help="Optional pg_dump data backup inside app/api/runtime"
    )
    parser.add_argument(
        "--brain-env", type=Path, help="Private backend-only environment file for the Notes API"
    )
    args = parser.parse_args()
    notes = None
    if args.brain_env:
        values = {}
        for line in args.brain_env.read_text(encoding="utf-8").splitlines():
            key, sep, value = line.partition("=")
            if sep and key.strip() in ("BRAIN_SERVER_URL", "BRAIN_API_USER", "BRAIN_API_PASSWORD"):
                values[key.strip()] = value.strip().strip('"').strip("'")
        notes = NotesProxy(
            BrainNotesHTTP(
                values.get("BRAIN_SERVER_URL", "http://localhost:8100"),
                values.get("BRAIN_API_USER", ""),
                values.get("BRAIN_API_PASSWORD", ""),
            )
        )
    # A preview always starts its own local cluster, even if CI/test env vars exist.
    os.environ.pop("YGGDRESS_TEST_ADMIN_URL", None)
    os.environ.pop("YGGDRESS_TEST_POSTGRES", None)
    runtime = ROOT / "runtime"
    runtime.mkdir(exist_ok=True)
    credentials = runtime / "preview-session.json"
    web = ROOT.parent / "web"
    origin = "http://127.0.0.1:3000"
    with isolated_database() as database:
        if args.restore_data:
            backup = Path(args.restore_data).resolve()
            if backup.parent != runtime.resolve() or not backup.is_file():
                raise ValueError(
                    "Preview restore accepts only an existing backup in app/api/runtime."
                )
            binary = (
                shutil.which("pg_restore") or "C:/Program Files/PostgreSQL/18/bin/pg_restore.exe"
            )
            listing = subprocess.run(
                [binary, "--list", str(backup)], check=True, capture_output=True, text=True
            ).stdout
            # A full data snapshot also includes singleton login/migration rows that
            # already exist in the brand-new cluster. Sessions belong to the old run.
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".restore-list", delete=False
            ) as file:
                file.write(preview_restore_list(listing))
                restore_list = Path(file.name)
            try:
                subprocess.run(
                    [
                        binary,
                        "--data-only",
                        "--disable-triggers",
                        "--single-transaction",
                        "--exit-on-error",
                        "--use-list",
                        str(restore_list),
                        "--dbname",
                        database["admin"],
                        str(backup),
                    ],
                    check=True,
                )
            finally:
                restore_list.unlink(missing_ok=True)
            with Database(database["admin"]).connect() as db:
                db.execute("UPDATE app.tasks SET objective=title WHERE objective=''")
                db.execute(
                    "UPDATE app.tasks SET state='completed',progress=100,completed_at=updated_at WHERE done AND state<>'completed'"
                )
            print("Restored application records into a new isolated preview database.", flush=True)
        password = preview_password()
        port = free_port()
        settings = Settings(database["runtime"], password_hash(password), origin, True, "mock")
        server = uvicorn.Server(
            uvicorn.Config(
                create_app(settings, notes=notes), host="127.0.0.1", port=port, log_level="error"
            )
        )
        worker = Thread(target=server.run, daemon=True)
        worker.start()
        descriptor = os.open(credentials, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            json.dump({"origin": origin, "password": password}, file)
        environment = {
            **{key: value for key, value in os.environ.items() if not key.startswith("BRAIN_")},
            "YGGDRESS_API_URL": f"http://127.0.0.1:{port}",
            "YGGDRESS_ORIGIN": origin,
        }
        environment.pop("YGGDRESS_PREVIEW_PASSWORD", None)
        frontend = None
        try:
            frontend = subprocess.Popen(
                [
                    shutil.which("node"),
                    str(web / "node_modules/next/dist/bin/next"),
                    "start",
                    "--hostname",
                    "127.0.0.1",
                    "--port",
                    "3000",
                ],
                cwd=web,
                env=environment,
            )
            print(
                f"Synthetic application preview: {origin}/tasks and {origin}/calendar", flush=True
            )
            print(
                "Authentication is enabled. Temporary sign-in details are private under app/api/runtime/preview-session.json.",
                flush=True,
            )
            print(
                "Keep this process running. Its isolated mock database is removed when it stops.",
                flush=True,
            )
            return frontend.wait()
        except KeyboardInterrupt:
            return 0
        finally:
            if frontend and frontend.poll() is None:
                frontend.terminate()
                frontend.wait(timeout=10)
            credentials.unlink(missing_ok=True)
            server.should_exit = True
            worker.join(timeout=10)


if __name__ == "__main__":
    sys.exit(main())
