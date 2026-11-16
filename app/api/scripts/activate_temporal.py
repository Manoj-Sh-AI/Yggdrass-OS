"""Explicit owner-authorized local upgrade. Uses verified backup/restore safeguards."""

import argparse
import hashlib
import json
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from yggdress_app.database import Database
from yggdress_app.local_runtime import atomic_json, default_home
from yggdress_app.local_upgrade import upgrade


def activate(home, build, binary, digest):
    config_path = home / "runtime.json"
    previous = json.loads(config_path.read_text(encoding="utf-8"))
    if not previous.get("agents", {}).get("enabled"):
        raise RuntimeError("Configure and verify the existing agents before switching execution.")
    if hashlib.sha256(binary.read_bytes()).hexdigest() != digest:
        raise RuntimeError("The verified Temporal binary digest does not match.")
    with Database(previous["database_url"]).connect() as db:
        active = db.execute(
            "SELECT count(*) AS n FROM app.agent_runs WHERE state='running'"
        ).fetchone()["n"]
        queued = db.execute(
            "SELECT count(*) AS n FROM app.chat_requests WHERE state IN ('queued','streaming')"
        ).fetchone()["n"]
        if active or queued:
            raise RuntimeError(
                "Wait for existing submitted requests to finish before switching execution."
            )
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    atomic_json(home / "backups" / ("runtime-before-temporal-" + stamp + ".json"), previous)
    tools = home / "tools" / ("temporal-" + digest[:12])
    tools.mkdir(parents=True, exist_ok=True)
    target = tools / binary.name
    if target.is_symlink():
        raise RuntimeError("The private execution binary must not be a link.")
    shutil.copyfile(binary, target)
    target.chmod(0o700)
    configured = {
        **previous,
        "agents": {
            **previous["agents"],
            "execution_backend": "temporal",
            "temporal": {"binary": str(target), "sha256": digest},
        },
    }
    atomic_json(config_path, configured)
    # This verifies/restores a fresh app-only backup and compares every original
    # column before applying additive migrations to the exact owned cluster.
    result = upgrade(home, build)
    return {**result, "execution_backend": "temporal", "provider_inference_tested": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--home", type=Path, default=default_home())
    parser.add_argument("--build", required=True)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(activate(args.home, args.build, args.binary, args.sha256)))
    except Exception as error:  # noqa: BLE001 -- never print configuration or transport errors
        print(
            "Temporal activation stopped safely: "
            + type(error).__name__
            + ". The verified backup and upgrade state are retained."
        )
        raise SystemExit(1) from None
