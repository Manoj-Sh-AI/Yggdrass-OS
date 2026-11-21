"""Persistent loopback application services for the owner's laptop.

Provisioning is explicit and never connects to Brain PostgreSQL. Normal startup
never migrates, seeds, imports, drops, or resets data. The Brain service remains
independently owned and is contacted only through its existing HTTP API.
"""

import argparse
import contextlib
import hmac
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

import psycopg
import uvicorn
from psycopg import sql
from psycopg.conninfo import make_conninfo

from .application import create_app
from .backup import client_environment, database_backup, fingerprints, tool
from .config import Settings
from .database import Database
from .notes_proxy import BrainNotesHTTP, NotesProxy
from .runtime_grants import grant_runtime


def default_home():
    return Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local/share")) / "Yggdras"


def atomic_json(path, value):
    temporary = path.with_suffix(".pending")
    descriptor = os.open(temporary, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(value, stream)
    temporary.replace(path)


def private_folder(home):
    home.mkdir(parents=True, exist_ok=True)
    if home.is_symlink() or home.is_junction():
        raise RuntimeError("The application data directory must not be a link.")
    if os.name == "nt":
        # Restrict the directory before storing passwords, data or backups.
        identity = subprocess.check_output(
            [
                "powershell.exe",
                "-NoProfile",
                "-Command",
                "[System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value",
            ],
            text=True,
        ).strip()
        subprocess.run(
            [
                "icacls.exe",
                str(home),
                "/inheritance:r",
                "/grant:r",
                f"*{identity}:(OI)(CI)F",
                "*S-1-5-18:(OI)(CI)F",
            ],
            check=True,
            capture_output=True,
        )
    else:
        home.chmod(0o700)


def port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def pg_binary(config, name):
    return Path(config["postgres_bin"]) / (name + (".exe" if os.name == "nt" else ""))


SCHEMAS = ["app", "brain"]  # the app's own schemas on a hosted database
NIGHTLY_KEEP = 14  # days of nightly backups kept on the laptop
NIGHTLY_HOUR = 3  # local hour after which the nightly backup runs


def remote(config) -> bool:
    """The database is hosted (Supabase) instead of the laptop's own PostgreSQL."""
    return config.get("database_host") == "remote"


def db_start(home, config):
    """Start the owned local cluster, or for a hosted database only verify it answers and
    holds the app's schemas (it is never started, stopped or adopted from here)."""
    if not remote(config):
        pg_start(home, config)
        return
    with psycopg.connect(config["admin_url"], connect_timeout=15) as db:
        found = {
            r[0]
            for r in db.execute(
                "SELECT nspname FROM pg_namespace WHERE nspname = ANY(%s)", (SCHEMAS,)
            )
        }
    if found != set(SCHEMAS):
        raise RuntimeError("The hosted database does not hold the application schemas.")


def nightly_backup(home, config, now=None):
    """One verified backup per night, kept NIGHTLY_KEEP days (Supabase Free has no
    downloadable backups). Returns the new file, or None when today's exists."""
    import tempfile
    from datetime import datetime, timedelta

    from .backup import database_backup

    now = now or datetime.now()
    folder = home / "backups"
    folder.mkdir(exist_ok=True)
    target = folder / f"nightly-{now:%Y%m%d}.dump"
    if now.hour < NIGHTLY_HOUR or target.exists():
        return None
    with tempfile.TemporaryDirectory(prefix="yggdress-nightly-") as work:
        partial = folder / (target.name + ".incomplete")
        partial.unlink(missing_ok=True)
        report = database_backup(
            config["admin_url"],
            partial,
            Path(config["postgres_bin"]),
            Path(work),
            schemas=SCHEMAS if remote(config) else None,
        )
        partial.rename(target)
    atomic_json(folder / "nightly-latest.json", {"file": target.name, **report})
    oldest = (now - timedelta(days=NIGHTLY_KEEP)).strftime("%Y%m%d")
    for old in folder.glob("nightly-*.dump"):
        if old.stem.removeprefix("nightly-") < oldest:
            old.unlink()
    return target


def backup_quietly(home, config):
    """The nightly backup never stops the app; a failure is logged by its type only (its
    message could hold a connection string)."""
    try:
        made = nightly_backup(home, config)
        if made:
            print(f"Nightly backup verified: {made.name}", flush=True)
    except Exception as exc:  # noqa: BLE001
        print(f"Nightly backup failed: {type(exc).__name__}", flush=True)


def pg_start(home, config):
    data = home / "postgres"
    if not data.is_dir() or data.is_symlink() or data.is_junction():
        raise RuntimeError("The private application cluster is missing or unsafe.")
    result = subprocess.run(
        [str(pg_binary(config, "pg_ctl")), "-D", str(data), "status"],
        capture_output=True,
        check=False,
    )
    if result.returncode:
        tool(
            pg_binary(config, "pg_ctl"),
            [
                "-D",
                data,
                "-l",
                home / "postgres.log",
                "-o",
                f"-h 127.0.0.1 -p {config['postgres_port']}",
                "-w",
                "start",
            ],
            capture=False,
        )
    # Verify credentials and exact owned directory; never adopt an unrelated listener.
    with psycopg.connect(config["admin_url"]) as db:
        actual = Path(db.execute("SHOW data_directory").fetchone()[0]).resolve()
        if actual != data.resolve():
            raise RuntimeError("Unexpected database listener; startup refused.")


def provision(home, source, pg_bin, password_hash, brain_env, web, build_dir):
    """Copy only an app-owned DB after full backup/restore verification."""
    if (home / "runtime.json").exists() or (home / "postgres").exists():
        raise RuntimeError("Already provisioned. Existing application data will not be replaced.")
    if not build_dir.startswith(".next-") or not (web / build_dir / "BUILD_ID").is_file():
        raise RuntimeError("Build and verify a dedicated frontend before provisioning.")
    private_folder(home)
    backups = home / "backups"
    backups.mkdir(exist_ok=True)
    with (
        psycopg.connect(source) as guard,
        tempfile.TemporaryDirectory(prefix="yggdress-local-check-") as temp,
    ):
        namespaces = {r[0] for r in guard.execute("SELECT nspname FROM pg_namespace")}
        if "brain" in namespaces or "app" not in namespaces:
            raise RuntimeError("Provisioning accepts an application database only.")
        guard.execute("SET lock_timeout='5s'")
        guard.execute("SET idle_in_transaction_session_timeout='300s'")
        names = [
            r[0]
            for r in guard.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname='app' ORDER BY tablename"
            )
        ]
        guard.execute(
            sql.SQL("LOCK TABLE {} IN SHARE MODE").format(
                sql.SQL(",").join(sql.Identifier("app", name) for name in names)
            )
        )
        dump = backups / ("application-before-desktop-" + time.strftime("%Y%m%d-%H%M%S") + ".dump")
        report = database_backup(source, dump, pg_bin, Path(temp))
        atomic_json(backups / "import-verification.json", report)
        admin_password = secrets.token_urlsafe(40)
        config = {
            "postgres_bin": str(pg_bin),
            "postgres_port": port(),
            "origin": "http://127.0.0.1:3000",
            "password_hash": password_hash,
            "brain_env": str(brain_env),
            "web": str(web),
            "build_dir": build_dir,
            "node": shutil.which("node"),
            "version": 1,
        }
        pwfile = home / "init-password"
        pwfile.write_text(admin_password, encoding="utf-8")
        try:
            tool(
                pg_binary(config, "initdb"),
                [
                    "-D",
                    home / "postgres",
                    "-A",
                    "scram-sha-256",
                    "-U",
                    "yggdras_owner",
                    "--pwfile",
                    pwfile,
                    "--no-locale",
                    "--encoding=UTF8",
                ],
            )
        finally:
            pwfile.unlink(missing_ok=True)
        config["admin_url"] = make_conninfo(
            host="127.0.0.1",
            port=config["postgres_port"],
            user="yggdras_owner",
            password=admin_password,
            dbname="postgres",
        )
        pg_start(home, config)
        tool(
            pg_binary(config, "pg_restore"),
            [
                "--no-owner",
                "--no-privileges",
                "--single-transaction",
                "--exit-on-error",
                "--dbname",
                "postgres",
                dump,
            ],
            client_environment(config["admin_url"]),
        )
        with psycopg.connect(config["admin_url"]) as db:
            db.execute("SET TIME ZONE 'UTC'")
            if fingerprints(db) != report["snapshot"]:
                raise RuntimeError("Restored records differ. Original service remains untouched.")
        Database(config["admin_url"]).migrate()
        with psycopg.connect(config["admin_url"]) as db:
            db.execute("SET TIME ZONE 'UTC'")
            after = fingerprints(db)
            for name, before in report["snapshot"]["tables"].items():
                if name != "app.schema_migrations" and after["tables"].get(name) != before:
                    raise RuntimeError("An existing application table changed during migration.")
            role, password = "yggdras_application", secrets.token_urlsafe(40)
            db.execute(
                sql.SQL(
                    "CREATE ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT"
                ).format(sql.Identifier(role), sql.Literal(password))
            )
            db.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
            grant_runtime(db, role)
        config["database_url"] = make_conninfo(config["admin_url"], user=role, password=password)
        atomic_json(home / "runtime.json", config)
        # Freeze and compare again; a concurrent successful save cannot be lost.
        guard.execute("SET TIME ZONE 'UTC'")
        if fingerprints(guard) != report["snapshot"]:
            raise RuntimeError("Source changed while importing. Do not activate this copy.")
    return {"backup_verified": True, "existing_records_preserved": True}


@contextlib.contextmanager
def manager_lock(home):
    stream = (home / "manager.lock").open("a+b")
    try:
        if os.name == "nt":
            import msvcrt

            stream.seek(0)
            if not stream.read(1):
                stream.write(b"0")
                stream.flush()
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        stream.close()


def clean_environment():
    return {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("BRAIN_", "YGGDRESS_", "YGGDRAS_", "PG", "ANTHROPIC_", "OPENAI_"))
    }


def brain_http(path):
    values = {}
    if Path(path).is_file():
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            key, sep, value = line.partition("=")
            if sep and key.strip() in ("BRAIN_SERVER_URL", "BRAIN_API_USER", "BRAIN_API_PASSWORD"):
                values[key.strip()] = value.strip().strip('"').strip("'")
    return BrainNotesHTTP(
        values.get("BRAIN_SERVER_URL", "http://localhost:8100"),
        values.get("BRAIN_API_USER", ""),
        values.get("BRAIN_API_PASSWORD", ""),
    )


def sweep_calls(calls, every=15.0, rounds=None):
    """The call scheduler without Temporal: one sweep every 15 s, a failure logged by its
    type only and never ending the loop. `rounds` bounds it for tests."""
    done = 0
    while rounds is None or done < rounds:
        try:
            calls.tick()
        except Exception as exc:  # noqa: BLE001 -- the next sweep retries
            print(f"call sweep failed: {type(exc).__name__}", flush=True)
        done += 1
        if rounds is None or done < rounds:
            time.sleep(every)


@contextlib.contextmanager
def child_log(path):
    """Where a child service writes: its private log file on the laptop, or the host's
    own log stream in a hosted container (YGGDRAS_LOG_STDOUT=1), so failures are visible."""
    if os.environ.get("YGGDRAS_LOG_STDOUT") == "1":
        yield None  # inherit this process's stdout/stderr
        return
    with path.open("a", encoding="utf-8") as log:
        yield log


def start_brain_if_needed(config, home):
    """Reuse the previously approved service launcher, never replace a listener."""
    from urllib.parse import urlsplit

    target = urlsplit(brain_http(config["brain_env"]).root)
    if target.hostname not in ("localhost", "127.0.0.1") or target.port != 8100:
        return None
    with socket.socket() as probe:
        probe.settimeout(1)
        if probe.connect_ex(("127.0.0.1", 8100)) == 0:
            return None
    project = Path(config["brain_env"]).parent
    venv = ".venv/Scripts/python.exe" if os.name == "nt" else ".venv/bin/python"
    python = project / venv
    if not python.is_file():
        python = project / "app" / venv
    launcher = Path(__file__).resolve().parents[2] / "scripts/brain_api_service.py"
    if not python.is_file() or not launcher.is_file():
        return None
    with child_log(home / "brain-service.log") as log:
        return subprocess.Popen(
            [str(python), str(launcher), "--brain-project", str(project), "--port", "8100"],
            cwd=project,
            env=clean_environment(),
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=log,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )


def stop_tree(process):
    """Stop a child and everything it started. On Windows a .venv python.exe is a launcher
    that starts the real interpreter as its own child, so terminate() alone left it running."""
    if process is None or process.poll() is not None:
        return
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/T", "/F", "/PID", str(process.pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=30,
                check=False,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        else:
            process.terminate()
        process.wait(timeout=15)
    except Exception:  # noqa: BLE001 -- the remaining shutdown steps must still run
        with contextlib.suppress(Exception):
            process.kill()


def quietly(step, *args):
    try:
        step(*args)
    except Exception:  # noqa: BLE001, S110 -- one failed shutdown step never skips the rest
        pass


def web_environment(config, api_port):
    """Settings for the laptop's web server. A hosted backend has no web server and no
    build folder, so nothing here may be required of it. With `backend_url` the web app
    talks to the hosted backend instead of a local one."""
    return {
        **clean_environment(),
        "YGGDRESS_API_URL": config.get("backend_url") or f"http://127.0.0.1:{api_port}",
        "YGGDRESS_ORIGIN": config["origin"],
        "YGGDRESS_BUILD_DIR": config.get("build_dir", ".next"),
    }


def serve_web_only(home, config):
    """The laptop when the backend is hosted (runtime.json `backend_url`): only the web app
    runs here, talking to the hosted backend; the laptop keeps its nightly backups of the
    hosted database. No local API, Lia, scheduler, voice worker or PostgreSQL."""
    with manager_lock(home):
        frontend_port = urlsplit(config["origin"]).port
        if urlsplit(config["origin"]).hostname != "127.0.0.1" or not frontend_port:
            raise RuntimeError("The local web app must use an explicit loopback port.")
        for attempt in range(30):  # a just-stopped web server may still hold the port
            try:
                with socket.socket() as probe:
                    probe.bind(("127.0.0.1", frontend_port))
                break
            except OSError:
                if attempt == 29:
                    raise
                time.sleep(0.5)
        control_port, token = port(), secrets.token_urlsafe(40)
        state = {"pid": os.getpid(), "control_port": control_port, "token": token,
                 "origin": config["origin"], "ready": False, "backend": "hosted"}  # fmt: skip
        frontend, stopping = None, False

        class Control(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def do_GET(self):
                if self.path != "/health" or not hmac.compare_digest(
                    self.headers.get("Authorization", ""), "Bearer " + token
                ):
                    self.send_error(403)
                    return
                ready = state["ready"] and frontend is not None and frontend.poll() is None
                body = json.dumps({"origin": config["origin"], "ready": ready}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self):
                nonlocal stopping
                if self.path != "/stop" or not hmac.compare_digest(
                    self.headers.get("Authorization", ""), "Bearer " + token
                ):
                    self.send_error(403)
                    return
                stopping = True
                self.send_response(204)
                self.end_headers()

        control = ThreadingHTTPServer(("127.0.0.1", control_port), Control)
        Thread(target=control.serve_forever, daemon=True).start()
        atomic_json(home / "service.json", state)
        try:
            with (home / "frontend.log").open("a", encoding="utf-8") as log:
                frontend = subprocess.Popen(
                    [config["node"], str(Path(config["web"]) / "node_modules/next/dist/bin/next"),
                     "start", "--hostname", "127.0.0.1", "--port", str(frontend_port)],
                    cwd=config["web"], env=web_environment(config, 0), stdout=log, stderr=log,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                )  # fmt: skip
                for _ in range(180):
                    if frontend.poll() is not None:
                        raise RuntimeError("Frontend startup failed. Inspect the private log.")
                    try:
                        with urlopen(config["origin"] + "/login", timeout=2) as response:
                            if response.status == 200:
                                state["ready"] = True
                                atomic_json(home / "service.json", state)
                                break
                    except OSError:
                        pass
                    time.sleep(0.25)
                else:
                    raise RuntimeError("Application startup timed out.")
                backups, checked = None, 0.0
                while not stopping and frontend.poll() is None:
                    if time.monotonic() - checked > 600 and not (backups and backups.is_alive()):
                        checked = time.monotonic()
                        backups = Thread(target=backup_quietly, args=(home, config), daemon=True)
                        backups.start()
                    time.sleep(0.5)
        finally:
            stop_tree(frontend)
            state["ready"] = False
            quietly(atomic_json, home / "service.json", state)
            quietly(control.shutdown)


def serve(home, hosted=False):
    """The laptop runtime, or with `hosted` the same backend in a hosted container
    (hosted.py): no web server, no local PostgreSQL, the API on the host's PORT."""
    config = json.loads((home / "runtime.json").read_text(encoding="utf-8"))
    if config.get("backend_url") and not hosted:
        serve_web_only(home, config)
        return
    with manager_lock(home):
        db_start(home, config)
        frontend_port = urlsplit(config["origin"]).port
        if not hosted:
            # Fail before starting children if another application occupies our origin.
            if urlsplit(config["origin"]).hostname != "127.0.0.1" or not frontend_port:
                raise RuntimeError("The local service must use an explicit loopback port.")
            with socket.socket() as probe:
                probe.bind(("127.0.0.1", frontend_port))
        brain_process = start_brain_if_needed(config, home)
        api_port = int(os.environ.get("PORT", "8080")) if hosted else port()
        control_port, token = port(), secrets.token_urlsafe(40)
        from .agent_receivers import Receivers
        from .agent_worker import AgentWorker, prepare_agent_configuration

        agent_config, agent_issue = prepare_agent_configuration(config)
        receiver_tokens = dict(config.get("receiver_tokens", {}))
        if agent_config:
            for scope in ("chat", "note_signals", "workflow_dispatch", "workflow", "background"):
                receiver_tokens.setdefault(scope, secrets.token_urlsafe(40))
        settings = Settings(
            config["database_url"],
            config["password_hash"],
            config["origin"],
            # Insecure (HTTP) cookies only when every web app is a loopback one; as soon as
            # an HTTPS web app is allowed, cookies are secure (the laptop's still works).
            all(urlsplit(o.strip()).scheme == "http" for o in config["origin"].split(",")),
            "unavailable",
            mobile_sensitive_access=config.get("mobile_sensitive_access") is True,
        )
        from .voice_runtime import load_voice_environment

        load_voice_environment(config["brain_env"])
        application = create_app(
            settings,
            notes=NotesProxy(brain_http(config["brain_env"])),
            receiver_tokens=receiver_tokens,
            chat_catalog=agent_config["catalog"] if agent_config else config.get("chat_catalog"),
            agents_enabled=bool(config.get("agents", {}).get("enabled")),
            agents_ready=bool(agent_config),
            agent_issue=agent_issue,
        )
        if agent_config:
            from .call_briefs import BriefPreparer

            # Voice reminders: Lia is asked in the background 10 minutes before each item.
            application.state.calls.briefs = BriefPreparer(
                Database(config["database_url"]),
                agent_config["lia"],
                agent_config["model_factory"],
                notes=application.state.notes_proxy,
            )
        worker = (
            AgentWorker(
                application.state.agent_store,
                Receivers(f"http://127.0.0.1:{api_port}", receiver_tokens),
                application.state.notes_proxy,
                agent_config["lia"],
                agent_config["model_factory"],
                agent_config["default_model"],
                config.get("agents", {}).get("activated_at"),
            )
            if agent_config
            else None
        )
        if worker and config.get("agents", {}).get("execution_backend") == "temporal":
            from .temporal_agent_service import TemporalAgentService

            temporal_config = config["agents"].get("temporal", {})
            worker = TemporalAgentService(
                worker,
                namespace="default",
                local={**temporal_config, "database": str(home / "temporal/history.sqlite")},
                calls=application.state.calls,
            )
            application.state.agent_runtime = worker
        api = uvicorn.Server(
            # Temporal changes execution plumbing; the HTTP service stays the same.
            uvicorn.Config(
                application,
                # "::" also answers on Railway's IPv6 private network (and on IPv4).
                host="::" if hosted else "127.0.0.1",
                port=api_port,
                log_level="error",
            )
        )
        api_thread = Thread(target=api.run, daemon=True)
        api_thread.start()
        environment = web_environment(config, api_port)
        frontend = None
        voice_process = None
        if application.state.calls.mode == "live":
            from .voice import LIVEKIT_VARS, missing

            if not missing(LIVEKIT_VARS):
                with child_log(home / "voice-worker.log") as voice_log:
                    voice_process = subprocess.Popen(
                        [sys.executable, "-m", "yggdress_app.voice_worker", "--home", str(home)],
                        env={
                            **clean_environment(),
                            "PYTHONPATH": str(Path(__file__).resolve().parents[1]),
                        },
                        stdin=subprocess.DEVNULL,
                        stdout=voice_log,
                        stderr=voice_log,
                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                    )
        state = {
            "pid": os.getpid(),
            "control_port": control_port,
            "token": token,
            "origin": config["origin"],
            "ready": False,
        }
        stopping = False

        class Control(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def do_GET(self):
                if self.path != "/health" or not hmac.compare_digest(
                    self.headers.get("Authorization", ""), "Bearer " + token
                ):
                    self.send_error(403)
                    return
                body = json.dumps(
                    {
                        "origin": config["origin"],
                        "ready": state["ready"]
                        and api.started
                        and (hosted or (frontend is not None and frontend.poll() is None)),
                    }
                ).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self):
                nonlocal stopping
                if self.path != "/stop" or not hmac.compare_digest(
                    self.headers.get("Authorization", ""), "Bearer " + token
                ):
                    self.send_error(403)
                    return
                stopping = True
                self.send_response(204)
                self.end_headers()

        control = ThreadingHTTPServer(("127.0.0.1", control_port), Control)
        Thread(target=control.serve_forever, daemon=True).start()
        atomic_json(home / "service.json", state)
        try:
            if hosted:  # no web server here: ready once the API answers
                for _ in range(240):
                    if api.started:
                        break
                    time.sleep(0.25)
                else:
                    raise RuntimeError("Application startup timed out.")
                state["ready"] = True
                atomic_json(home / "service.json", state)
                # YGGDRAS_BACKGROUND=off: a test deploy beside the laptop never competes
                # with the laptop's agent worker for the same queued requests.
                if worker and os.environ.get("YGGDRAS_BACKGROUND", "on") != "off":
                    worker.start()
                    if config.get("agents", {}).get("execution_backend") != "temporal":
                        # Without Temporal a plain thread sweeps the calls (as its workflow does).
                        Thread(target=sweep_calls, args=(application.state.calls,),
                               daemon=True, name="yggdras-call-sweep").start()  # fmt: skip
                while not stopping and api_thread.is_alive():
                    time.sleep(0.5)
                return
            with (home / "frontend.log").open("a", encoding="utf-8") as log:
                frontend = subprocess.Popen(
                    [
                        config["node"],
                        str(Path(config["web"]) / "node_modules/next/dist/bin/next"),
                        "start",
                        "--hostname",
                        "127.0.0.1",
                        "--port",
                        str(frontend_port),
                    ],
                    cwd=config["web"],
                    env=environment,
                    stdout=log,
                    stderr=log,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                )
                for _ in range(180):
                    if frontend.poll() is not None:
                        raise RuntimeError(
                            "Frontend startup failed. Inspect the private application log."
                        )
                    try:
                        with urlopen(config["origin"] + "/login", timeout=2) as response:
                            if response.status == 200 and api.started:
                                state["ready"] = True
                                atomic_json(home / "service.json", state)
                                if worker:
                                    worker.start()
                                break
                    except OSError:
                        pass
                    time.sleep(0.25)
                else:
                    raise RuntimeError("Application startup timed out.")
                backups, checked = None, 0.0
                while not stopping and frontend.poll() is None and api_thread.is_alive():
                    if time.monotonic() - checked > 600 and not (backups and backups.is_alive()):
                        checked = time.monotonic()
                        backups = Thread(target=backup_quietly, args=(home, config), daemon=True)
                        backups.start()
                    time.sleep(0.5)
        finally:
            # Every step runs even if an earlier one fails: a half-stopped app left the brain
            # service, voice worker and web server running and blocked the next start.
            stop_tree(voice_process)
            if worker:
                quietly(worker.stop)
            state["ready"] = False
            quietly(atomic_json, home / "service.json", state)
            stop_tree(frontend)
            api.should_exit = True
            api_thread.join(timeout=15)
            quietly(control.shutdown)
            stop_tree(brain_process)
            if not remote(config):
                # PostgreSQL is durable and owned here. A fast stop flushes WAL safely.
                tool(
                    pg_binary(config, "pg_ctl"),
                    ["-D", home / "postgres", "-m", "fast", "-w", "stop"],
                    capture=False,
                )


def status(home):
    try:
        state = json.loads((home / "service.json").read_text(encoding="utf-8"))
        request = Request(
            f"http://127.0.0.1:{state['control_port']}/health",
            headers={"Authorization": "Bearer " + state["token"]},
        )
        with urlopen(request, timeout=2) as response:
            return json.load(response)
    except (OSError, ValueError, KeyError):
        return {"ready": False}


def ensure(home):
    if (home / "maintenance.json").exists():
        raise RuntimeError("A verified local application update is in progress. Retry shortly.")
    current = status(home)
    if current.get("ready"):
        return current
    if not (home / "runtime.json").is_file():
        raise RuntimeError(
            "Local data is not provisioned. Run the verified application import first."
        )
    with (home / "service.log").open("a", encoding="utf-8") as log:
        subprocess.Popen(
            [sys.executable, "-m", "yggdress_app.local_runtime", "--home", str(home), "serve"],
            env={**clean_environment(), "PYTHONPATH": str(Path(__file__).resolve().parents[1])},
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=log,
            creationflags=(
                subprocess.DETACHED_PROCESS
                | subprocess.CREATE_NEW_PROCESS_GROUP
                | subprocess.CREATE_NO_WINDOW
            )
            if os.name == "nt"
            else 0,
            start_new_session=os.name != "nt",
        )
    for _ in range(240):
        result = status(home)
        if result.get("ready"):
            return result
        time.sleep(0.25)
    raise RuntimeError("Local services did not become ready. Inspect the private service log.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--home", type=Path, default=default_home())
    parser.add_argument("action", choices=("ensure", "serve", "status", "stop"))
    args = parser.parse_args()
    try:
        if args.action == "serve":
            serve(args.home)
        elif args.action == "ensure":
            print(json.dumps(ensure(args.home)))
        elif args.action == "status":
            print(json.dumps(status(args.home)))
        else:
            state = json.loads((args.home / "service.json").read_text())
            request = Request(
                f"http://127.0.0.1:{state['control_port']}/stop",
                data=b"",
                headers={"Authorization": "Bearer " + state["token"]},
            )
            with urlopen(request, timeout=3):
                pass
    except Exception:  # noqa: BLE001 -- private connection details must never reach host UI
        # A child/tool exception can contain a connection URL. Never echo it.
        print(
            "Local application service could not complete the request. Check the private logs.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
