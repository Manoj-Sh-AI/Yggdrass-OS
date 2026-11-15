"""Run the authenticated production frontend against disposable PostgreSQL."""

import json
import os
import secrets
import shutil
import subprocess
import sys
import time
from pathlib import Path
from threading import Thread
from urllib.error import URLError
from urllib.request import urlopen

import uvicorn

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tests")]
from notes_fixture import SyntheticBrain
from postgres_fixture import free_port, isolated_database

from yggdress_app.application import create_app
from yggdress_app.config import Settings
from yggdress_app.notes_proxy import NotesProxy
from yggdress_app.security import password_hash


def main():
    web = ROOT.parent / "web"
    runtime = ROOT / "runtime"
    runtime.mkdir(exist_ok=True)
    credentials = runtime / "browser-session.json"
    node = shutil.which("node")
    with isolated_database() as database:
        password = secrets.token_urlsafe(32)
        api_port = free_port()
        origin = "http://127.0.0.1:3100"
        settings = Settings(database["runtime"], password_hash(password), origin, True)
        receiver_tokens = {
            scope: secrets.token_urlsafe(32)
            for scope in ("note_signals", "workflow_dispatch", "workflow", "background")
        }
        receiver_file = runtime / "browser-receivers.json"
        receiver_file.write_text(
            json.dumps({"url": f"http://127.0.0.1:{api_port}", "tokens": receiver_tokens}),
            encoding="utf-8",
        )
        receiver_file.chmod(0o600)
        catalog = {
            "agents": [
                {
                    "id": "yggdras",
                    "name": "Yggdras",
                    "enabled": False,
                    "models": ["default", "synthetic-alpha", "synthetic-beta"],
                },
                {
                    "id": "lia",
                    "name": "Lia",
                    "enabled": False,
                    "models": ["default", "synthetic-alpha", "synthetic-beta"],
                },
            ],
            "models": [
                {"id": "default", "name": "Provider default"},
                {"id": "synthetic-alpha", "name": "Synthetic Alpha"},
                {"id": "synthetic-beta", "name": "Synthetic Beta"},
            ],
        }
        agent_worker = None
        synthetic_agents = os.environ.get("YGGDRESS_SYNTHETIC_AGENTS") == "1"
        if synthetic_agents:
            receiver_tokens["chat"] = secrets.token_urlsafe(32)
            receiver_file.write_text(
                json.dumps({"url": f"http://127.0.0.1:{api_port}", "tokens": receiver_tokens}),
                encoding="utf-8",
            )
            catalog = {
                "agents": [
                    {"id": identifier, "name": name, "enabled": True}
                    for identifier, name in (
                        ("yggdras", "Yggdras"),
                        ("lia", "Lia"),
                        ("tasks", "Task Manager"),
                        ("calendar", "Calendar"),
                    )
                ],
                "models": [{"id": "default", "name": "Synthetic model", "enabled": True}],
            }
        application = create_app(
            settings,
            notes=NotesProxy(SyntheticBrain()),
            receiver_tokens=receiver_tokens,
            chat_catalog=catalog,
        )
        if synthetic_agents:
            from synthetic_agents import SyntheticLia, SyntheticModel

            from yggdress_app.agent_receivers import Receivers
            from yggdress_app.agent_worker import AgentWorker

            agent_worker = AgentWorker(
                application.state.agent_store,
                Receivers(f"http://127.0.0.1:{api_port}", receiver_tokens),
                application.state.notes_proxy,
                SyntheticLia(),
                lambda _model: SyntheticModel(),
                "synthetic-model",
            )
        server = uvicorn.Server(
            uvicorn.Config(
                application,
                host="127.0.0.1",
                port=api_port,
                log_level="error",
            )
        )
        worker = Thread(target=server.run, daemon=True)
        worker.start()
        environment = {
            **{
                key: value
                for key, value in os.environ.items()
                if not key.startswith(("BRAIN_", "ANTHROPIC_", "OPENAI_"))
            },
            "YGGDRESS_API_URL": f"http://127.0.0.1:{api_port}",
            "YGGDRESS_ORIGIN": origin,
        }
        credentials.write_text(json.dumps({"password": password}), encoding="utf-8")
        credentials.chmod(0o600)
        try:
            with (runtime / "browser-next.log").open("w", encoding="utf-8") as log:
                frontend = subprocess.Popen(
                    [
                        node,
                        str(web / "node_modules/next/dist/bin/next"),
                        "start",
                        "--hostname",
                        "127.0.0.1",
                        "--port",
                        "3100",
                    ],
                    cwd=web,
                    env=environment,
                    stdout=log,
                    stderr=log,
                )
                try:
                    for _ in range(120):
                        if frontend.poll() is not None:
                            raise RuntimeError(
                                "Test frontend could not start; inspect ignored runtime/browser-next.log."
                            )
                        try:
                            with urlopen(origin + "/login", timeout=2) as response:
                                if response.status == 200 and server.started:
                                    break
                        except (URLError, TimeoutError):
                            pass
                        time.sleep(0.5)
                    else:
                        raise RuntimeError("Test services did not become ready.")
                    if agent_worker:
                        agent_worker.start()
                    result = subprocess.run(
                        [
                            node,
                            str(web / "node_modules/@playwright/test/cli.js"),
                            "test",
                            *sys.argv[1:],
                        ],
                        cwd=web,
                        env=environment,
                        check=False,
                    )
                    return result.returncode
                finally:
                    frontend.terminate()
                    try:
                        frontend.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        frontend.kill()
                        frontend.wait()
        finally:
            if agent_worker:
                agent_worker.stop()
            credentials.unlink(missing_ok=True)
            receiver_file.unlink(missing_ok=True)
            server.should_exit = True
            worker.join(timeout=10)


if __name__ == "__main__":
    sys.exit(main())
