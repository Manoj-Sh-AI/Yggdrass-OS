"""A throwaway PostgreSQL per worker (planning/agentic-engineering.md items 17 and 61).

Each worktree (or any name) gets its own cluster in the temp folder on its own port, so two
parallel workers never run migrations or tests against the same database, and nothing here
can touch the real DATABASE_URL. Prints the URL to export as GATE_SCRATCH_DB_URL (the gate
passes it to the test fixture as YGGDRESS_TEST_ADMIN_URL).

    python tools/scratch_db.py up            # name = current worktree folder
    python tools/scratch_db.py up refactor-a
    python tools/scratch_db.py down refactor-a
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

BASE_PORT, SPAN = 55000, 4000


def slug(name: str) -> str:
    clean = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return clean[:40] or "worker"


def port_for(name: str) -> int:
    """Stable per name, so `up` twice reuses the same cluster and URL."""
    return BASE_PORT + int(hashlib.sha256(slug(name).encode()).hexdigest(), 16) % SPAN


def folder_for(name: str) -> Path:
    return Path(tempfile.gettempdir()) / f"yggdras-scratch-{slug(name)}"


def url_for(name: str) -> str:
    return f"postgresql://fixture@127.0.0.1:{port_for(name)}/yggdress_test_{slug(name).replace('-', '_')}"


def tool(name: str) -> str:
    found = shutil.which(name) or shutil.which(f"{name}.exe")
    if found:
        return found
    windows = Path("C:/Program Files/PostgreSQL/18/bin") / f"{name}.exe"
    if windows.is_file():
        return str(windows)
    raise SystemExit(f"{name} not found: install the PostgreSQL tools.")


def in_use(port: int) -> bool:
    with socket.socket() as sock:
        return sock.connect_ex(("127.0.0.1", port)) == 0


def up(name: str) -> str:
    folder, port = folder_for(name), port_for(name)
    data = folder / "cluster"
    if not data.exists():
        folder.mkdir(parents=True, exist_ok=True)
        subprocess.run([tool("initdb"), "-D", str(data), "-A", "trust", "-U", "fixture",
                        "--no-locale", "--encoding=UTF8"], check=True, stdout=subprocess.DEVNULL)  # fmt: skip
    if not in_use(port):
        subprocess.run([tool("pg_ctl"), "-D", str(data), "-l", str(folder / "log.txt"), "-w",
                        "-o", f"-h 127.0.0.1 -p {port}", "start"], check=True,
                       stdout=subprocess.DEVNULL)  # fmt: skip
    database = url_for(name).rsplit("/", 1)[1]
    exists = subprocess.run([tool("psql"), "-h", "127.0.0.1", "-p", str(port), "-U", "fixture",
                             "-d", "postgres", "-tAc", f"SELECT 1 FROM pg_database WHERE datname='{database}'"],
                            capture_output=True, text=True, check=True)  # fmt: skip
    if exists.stdout.strip() != "1":
        subprocess.run([tool("createdb"), "-h", "127.0.0.1", "-p", str(port), "-U", "fixture", database],
                       check=True)  # fmt: skip
    return url_for(name)


def down(name: str) -> None:
    folder = folder_for(name)
    data = folder / "cluster"
    if data.exists():
        subprocess.run([tool("pg_ctl"), "-D", str(data), "-m", "fast", "-w", "stop"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)  # fmt: skip
    shutil.rmtree(folder, ignore_errors=True)


def main(argv: list[str]) -> int:
    if not argv or argv[0] not in ("up", "down", "url"):
        print(__doc__)
        return 2
    name = argv[1] if len(argv) > 1 else Path(os.getcwd()).name
    if argv[0] == "up":
        print(up(name))
    elif argv[0] == "url":
        print(url_for(name))
    else:
        down(name)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
