"""Physical-device test service. Invented notes, disposable SQL, no provider calls.

The frontend is loopback-only. Stop by creating the project-cache stop marker.
Never loads the installed runtime, a private environment file or a Brain database.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from threading import Thread
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[3]
API = ROOT / "app/api"
CACHE = ROOT / "app/mobile/.cache"
sys.path[:0] = [str(API / "src"), str(API / "tests")]

import uvicorn
from notes_fixture import SyntheticBrain
from postgres_fixture import free_port, isolated_database

from yggdress_app.application import create_app
from yggdress_app.config import Settings
from yggdress_app.mobile_policy import sensitive
from yggdress_app.notes_proxy import NotesProxy
from yggdress_app.security import password_hash

ORIGIN = "http://127.0.0.1:3300"
# Public fixture value: protects invented disposable records only, never personal data.
FIXTURE_PASSWORD = "mobile-fixture-password-123"


class Graph:
    def __init__(self, notes):
        self.notes = notes
        self.owner = ROOT.parent / "Yggdrass-OS-main"
        self.graph = self.owner / "app/src/yggdras/data/graph"

    def asset(self, name):
        if name == "graph.html":
            text = (self.graph / "viewer_template.html").read_text(encoding="utf-8")
            nodes = [
                {
                    "id": slug,
                    "slug": slug,
                    "name": note["title"],
                    "type": "concept",
                    "area": note.get("area", "cross"),
                    "shelf": note.get("area", "cross"),
                    "path": slug + ".md",
                    "href": "/notes?note=" + slug,
                    "description": "Invented device-test note",
                    "aliases": [],
                    "summary": "Invented device-test content",
                    "facts": ["An invented fact"],
                    "sensitive": sensitive(note),
                    "degree": 0,
                }
                for slug, note in self.notes.notes.items()
            ]
            return text.replace(
                "/*__YGGDRAS_DATA__*/null",
                json.dumps({"schema": "fixture", "nodes": nodes, "edges": []}),
            ).encode()
        produced = self.owner / "local-data/brain-view" / name
        if produced.is_file() and name != "graph.html":
            return produced.read_bytes()  # Vendored JS/fonts only; never real graph data.
        mapping = {
            "vis-network.min.js": "vis-network-9.1.6.min.js",
            "three.js": "three-0.185.1.cjs",
            "3d-force-graph.min.js": "3d-force-graph-1.80.1.min.js",
        }
        raw = (self.graph / "vendor" / mapping.get(name, name)).read_bytes()
        if name == "three.js":
            raw = (
                b"(function(){var exports={},module={exports:exports};"
                + raw
                + b";window.THREE=module.exports;})();"
            )
        return raw

    def status(self):
        return {"nodes": len(self.notes.notes), "links": 0, "source": "brain-viewer"}


def main():
    import argparse
    import re

    parser = argparse.ArgumentParser()
    parser.add_argument("--calls", action="store_true")
    parser.add_argument("--owner-notes", action="store_true")
    parser.add_argument("--build", default=".next-phone-ready")
    args = parser.parse_args()
    if (
        not re.fullmatch(r"\.next-[a-z0-9-]+", args.build)
        or not (ROOT / "app/web" / args.build / "BUILD_ID").is_file()
    ):
        raise RuntimeError(
            "Build a dedicated frontend candidate before starting the device fixture."
        )
    os.environ.pop("ANTHROPIC_API_KEY", None)
    CACHE.mkdir(exist_ok=True)
    stop = CACHE / "device-fixture-stop"
    if stop.exists():
        stop.unlink()
    notes = SyntheticBrain()
    notes.notes["fixture-private"] = {
        "slug": "fixture-private",
        "title": "Private invented fixture",
        "body": "---\nslug: fixture-private\nsensitivity: high\n---\n## Facts\n- Private invented fixture text\n## Links\n",
        "version": 1,
    }
    with isolated_database() as database:
        port = free_port()
        settings = Settings(
            database["runtime"],
            password_hash(FIXTURE_PASSWORD),
            ORIGIN,
            True,
            mobile_sensitive_access=args.owner_notes,
        )
        from yggdress_app.call_service import CallService
        from yggdress_app.database import Database

        proxy = NotesProxy(notes)
        application = create_app(
            settings,
            notes=proxy,
            graph=Graph(notes),
            calls=CallService(
                Database(database["runtime"]),
                mode="simulated" if args.calls else "disabled",
                notes=proxy,
            ),
        )
        server = uvicorn.Server(
            uvicorn.Config(
                application, host="127.0.0.1", port=port, log_level="warning", access_log=False
            )
        )
        thread = Thread(target=server.run, daemon=True)
        thread.start()
        for _ in range(100):
            if server.started:
                break
            time.sleep(0.1)
        if not server.started:
            raise RuntimeError("Fixture API did not start.")
        env = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith(("YGGDRESS_", "BRAIN_", "ANTHROPIC_", "PG"))
        }
        env.update(
            YGGDRESS_ORIGIN=ORIGIN,
            YGGDRESS_API_URL=f"http://127.0.0.1:{port}",
            YGGDRESS_BUILD_DIR=args.build,
            NEXT_TELEMETRY_DISABLED="1",
        )
        with (CACHE / "device-fixture-web.log").open("w") as log:
            web = subprocess.Popen(
                [
                    "node",
                    str(ROOT / "app/web/node_modules/next/dist/bin/next"),
                    "start",
                    "--hostname",
                    "127.0.0.1",
                    "--port",
                    "3300",
                ],
                cwd=ROOT / "app/web",
                env=env,
                stdout=log,
                stderr=log,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            try:
                for _ in range(100):
                    try:
                        with urlopen(ORIGIN + "/login", timeout=2) as response:
                            if response.status == 200:
                                break
                    except OSError:
                        time.sleep(0.2)
                else:
                    raise RuntimeError("Fixture frontend did not start.")
                (CACHE / "device-fixture-state.json").write_text(
                    json.dumps(
                        {"ready": True, "origin": ORIGIN, "data": "invented only", "model_calls": 0}
                    )
                )
                print("Invented-data device fixture is ready.", flush=True)
                while not stop.exists():
                    time.sleep(1)
            finally:
                web.terminate()
                web.wait(timeout=20)
                server.should_exit = True
                thread.join(timeout=10)
                (CACHE / "device-fixture-state.json").write_text(json.dumps({"ready": False}))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:  # noqa: BLE001 -- never echo transport credentials
        print("Device fixture stopped: " + type(error).__name__)
        raise SystemExit(1) from None
