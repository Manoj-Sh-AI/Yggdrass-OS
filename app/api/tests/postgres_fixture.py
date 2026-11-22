"""Disposable application-only PostgreSQL fixture. Never uses the application's DB URL."""

import os
import secrets
import shutil
import socket
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from yggdress_app.database import Database


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@contextmanager
def isolated_database():
    """CI supplies an explicitly named test database; local runs start a fresh cluster."""
    configured = os.environ.get("YGGDRESS_TEST_ADMIN_URL")
    if os.environ.get("YGGDRESS_TEST_POSTGRES") == "1" and not configured:
        configured = make_conninfo(dbname=os.environ.get("PGDATABASE", "yggdress_test"))
    process = None
    with tempfile.TemporaryDirectory(prefix="yggdress-test-") as directory:
        root = Path(directory)
        if configured:
            config = conninfo_to_dict(configured)
            if not config.get("dbname", "").startswith("yggdress_test"):
                raise ValueError("Test database name must start with yggdress_test.")
            admin = configured
        else:
            binary = Path(shutil.which("initdb") or "C:/Program Files/PostgreSQL/18/bin/initdb.exe")
            if not binary.is_file():
                raise RuntimeError("Install PostgreSQL tools or configure YGGDRESS_TEST_ADMIN_URL.")
            port = free_port()
            pg_ctl = binary.with_name("pg_ctl.exe" if os.name == "nt" else "pg_ctl")
            data = root / "cluster"
            subprocess.run(
                [
                    str(binary),
                    "-D",
                    str(data),
                    "-A",
                    "trust",
                    "-U",
                    "fixture",
                    "--no-locale",
                    "--encoding=UTF8",
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.STDOUT,
            )
            subprocess.run(
                [
                    str(pg_ctl),
                    "-D",
                    str(data),
                    "-l",
                    str(root / "postgres.log"),
                    "-o",
                    f"-h 127.0.0.1 -p {port}",
                    "-w",
                    "start",
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.STDOUT,
            )
            process = (pg_ctl, data)
            admin = make_conninfo(host="127.0.0.1", port=port, user="fixture", dbname="postgres")
        try:
            # Unique database and role, even on the dedicated CI PostgreSQL service.
            name = "yggdress_test_" + secrets.token_hex(6)
            role = "app_test_" + secrets.token_hex(6)
            password = secrets.token_urlsafe(32)
            with psycopg.connect(admin, autocommit=True) as connection:
                connection.execute(sql.SQL("CREATE DATABASE {} ").format(sql.Identifier(name)))
                connection.execute(
                    sql.SQL(
                        "CREATE ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT"
                    ).format(sql.Identifier(role), sql.Literal(password))
                )
            migrated = make_conninfo(admin, dbname=name)
            Database(migrated).migrate()
            with psycopg.connect(migrated) as connection:
                connection.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
                connection.execute(
                    sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                        sql.Identifier(name), sql.Identifier(role)
                    )
                )
                connection.execute(
                    sql.SQL("GRANT USAGE ON SCHEMA app TO {}").format(sql.Identifier(role))
                )
                for grants in (
                    "GRANT SELECT,INSERT,DELETE ON app.sessions TO {}",
                    "GRANT UPDATE(expires_at) ON app.sessions TO {}",
                    "GRANT SELECT,UPDATE ON app.login_guard TO {}",
                    "GRANT SELECT,INSERT ON app.routines,app.routine_progress,app.tasks TO {}",
                    "GRANT UPDATE(status,progress,started_at,completed_at,updated_at) ON app.routines TO {}",
                    "GRANT UPDATE ON app.tasks TO {}",
                    "GRANT SELECT,INSERT,UPDATE ON app.planning_goals,app.projects,app.routine_templates,app.calendar_events,app.execution_blocks,app.execution_sessions,app.daily_plans,app.reminder_requests TO {}",
                    "GRANT SELECT,INSERT,DELETE ON app.task_dependencies TO {}",
                    "GRANT SELECT,INSERT ON app.routine_exceptions,app.task_history,app.planning_commands TO {}",
                    "GRANT SELECT,INSERT ON app.note_refs TO {}",
                    "GRANT UPDATE(observed_title,observed_revision,last_verified_at) ON app.note_refs TO {}",
                    "GRANT SELECT,INSERT,DELETE ON app.task_note_links,app.event_note_links,app.event_task_links TO {}",
                    "GRANT SELECT ON app.workspace_changes,app.background_runs,app.operational_edges TO {}",
                    "GRANT SELECT,INSERT,UPDATE,DELETE ON app.chat_conversations,app.chat_messages,app.chat_requests,app.chat_attachments TO {}",
                    "GRANT SELECT,INSERT ON app.receiver_receipts TO {}",
                    "GRANT SELECT,INSERT,UPDATE ON app.calendar_date_items,app.availability_windows TO {}",
                    "GRANT SELECT,INSERT,DELETE ON app.date_item_note_links,app.availability_note_links TO {}",
                    "GRANT UPDATE(source_revision) ON app.task_note_links,app.event_note_links,app.date_item_note_links,app.availability_note_links TO {}",
                    "GRANT SELECT,INSERT,UPDATE ON app.workflow_sources,app.workflow_bindings,app.workflow_reviews,app.background_runs TO {}",
                    "GRANT SELECT,INSERT ON app.workflow_changes TO {}",
                    "GRANT SELECT,INSERT,UPDATE ON app.note_handoffs TO {}",
                    "GRANT UPDATE(external_id) ON app.note_refs TO {}",
                    "GRANT SELECT,INSERT,UPDATE ON app.agent_runs,app.agent_steps,app.agent_proposals,app.agent_note_events,app.agent_write_intents TO {}",
                    "GRANT SELECT,INSERT,UPDATE ON app.agent_executions,app.agent_effects TO {}",
                    "GRANT SELECT,INSERT ON app.yggdras_runs,app.yggdras_feedback,app.notifications TO {}",
                    "GRANT SELECT,INSERT,UPDATE ON app.devices,app.calls,app.call_schedules TO {}",
                    "GRANT SELECT,INSERT,UPDATE ON app.call_preferences,app.call_events,app.call_delivery,app.voice_worker_lease,app.call_commands,app.call_reviews TO {}",
                    "GRANT SELECT,INSERT,UPDATE,DELETE ON app.call_briefs TO {}",
                    "GRANT SELECT,INSERT ON app.item_outcomes TO {}",
                    "GRANT SELECT,INSERT,UPDATE ON app.conductor_runs TO {}",
                    "GRANT SELECT,INSERT ON app.conductor_events TO {}",
                ):
                    connection.execute(sql.SQL(grants).format(sql.Identifier(role)))
                connection.execute(
                    sql.SQL("GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA app TO {}").format(
                        sql.Identifier(role)
                    )
                )
            runtime = make_conninfo(migrated, user=role, password=password)
            yield {"admin": migrated, "runtime": runtime, "role": role}
        finally:
            if "name" in locals():
                with psycopg.connect(admin, autocommit=True) as connection:
                    connection.execute(
                        sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(
                            sql.Identifier(name)
                        )
                    )
                    connection.execute(
                        sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(role))
                    )
            if process:
                subprocess.run(
                    [str(process[0]), "-D", str(process[1]), "-m", "immediate", "-w", "stop"],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.STDOUT,
                )
