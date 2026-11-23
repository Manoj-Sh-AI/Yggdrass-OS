"""No invented dev ports (planning/agentic-engineering.md item 55).

Every `localhost:NNNN` / `127.0.0.1:NNNN` in tracked app/ and tools/ files must be listed
in dev-ports.json, so two agents never pick the same new port on separate branches.

Usage: python tools/ci/check_ports.py
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATTERN = re.compile(r"(?:localhost|127\.0\.0\.1):(\d{4,5})\b")
SKIP = (".lock", "package-lock.json", ".png", ".jpg", ".apk", ".svg")


def allowed(config: dict) -> set[str]:
    return set(config.get("ports", {})) | set(config.get("test_only", {}))


def unknown_ports(files: dict[str, str], known: set[str]) -> list[str]:
    found = []
    for path, text in sorted(files.items()):
        for number, line in ((m.group(1), text.count("\n", 0, m.start()) + 1) for m in PATTERN.finditer(text)):
            if number not in known:
                found.append(f"{path}:{line}: port {number} is not in dev-ports.json")
    return found


def main() -> int:
    known = allowed(json.loads((ROOT / "dev-ports.json").read_text(encoding="utf-8")))
    listed = subprocess.run(["git", "ls-files", "app", "tools"], cwd=ROOT, capture_output=True,
                            text=True, check=True).stdout.split()  # fmt: skip
    files = {}
    for path in listed:
        if path.endswith(SKIP) or not (ROOT / path).is_file():
            continue
        try:
            files[path] = (ROOT / path).read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
    found = unknown_ports(files, known)
    for line in found:
        print(f"::error::{line}")
    print(f"ports: {len(files)} files scanned, {len(found)} unknown ports")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
