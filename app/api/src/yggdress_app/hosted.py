"""Run the whole backend in one hosted Linux container (Railway): API + call scheduler,
agent worker + Temporal, brain service + Lia, voice worker. Same wiring as the laptop
runtime (local_runtime.serve), minus the web server and the laptop's PostgreSQL.

Settings come only from the host's environment variables. At start they are written
into two private files the existing code already reads: `$YGGDRAS_HOME/runtime.json` and
the brain project's `.env`. Nothing is written into the repository or logged.

    python -m yggdress_app.hosted

Firebase: paste the service-account file's contents into the Railway variable
FIREBASE_SERVICE_ACCOUNT_JSON (with FIREBASE_PROJECT_ID). It is written to
`$YGGDRAS_HOME/secrets/` on every start, so it survives redeploys without a volume.

Test beside the laptop first: leave YGGDRAS_CALLS_MODE unset (calls disabled) and set
YGGDRAS_BACKGROUND=off (no agent worker), so nothing runs twice. Switch both on at cutover.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]  # app/api/src/yggdress_app/hosted.py -> repo
REQUIRED = (
    "YGGDRESS_DATABASE_URL",  # runtime role (app schema)
    "YGGDRESS_MIGRATION_URL",  # app schema owner
    "YGGDRESS_ADMIN_URL",  # database admin
    "BRAIN_DATABASE_URL",  # brain schema owner (Lia)
    "YGGDRESS_PASSWORD_HASH",  # sign-in password hash
    "YGGDRESS_ORIGIN",  # the web app's exact origin
    "ANTHROPIC_API_KEY",
)
# Copied into the brain project's .env when set (the voice and brain code read them there).
PASSED = (
    "ANTHROPIC_API_KEY",
    "BRAIN_DATABASE_URL",
    "LIVEKIT_URL",
    "LIVEKIT_API_KEY",
    "LIVEKIT_API_SECRET",
    "FIREBASE_PROJECT_ID",
    "FIREBASE_SERVICE_ACCOUNT_FILE",
    "YGGDRAS_CALLS_MODE",
    "YGGDRAS_VOICE_STT",
    "YGGDRAS_VOICE_TTS",
    "YGGDRAS_VOICE_ID",
    "YGGDRAS_LIA_MODEL",
    "YGGDRESS_AGENT_MODEL",
    "YGGDRAS_OWNER_NAMES",
)


def home() -> Path:
    return Path(os.environ.get("YGGDRAS_HOME", "/data"))


def missing(env=os.environ) -> list[str]:
    return [name for name in REQUIRED if not env.get(name, "").strip()]


def quoted(value: str) -> str:
    if "'" in value or "\n" in value:
        raise ValueError("A setting contains a quote or a line break.")
    return "'" + value + "'"


def brain_env(env=os.environ, folder: Path | None = None) -> str:
    """The brain project's .env, built from the host's variables. The brain service gets a
    fresh random password on every start; only processes in this container use it."""
    folder = folder or home()
    lines = {name: env[name] for name in PASSED if env.get(name, "").strip()}
    lines |= {
        "YGGDRAS_BRAIN_SOURCE": "rows",  # D44: the database is the brain
        "BRAIN_SERVER_URL": "http://127.0.0.1:8100",
        "BRAIN_API_USER": "yggdras",
        "BRAIN_API_PASSWORD": secrets.token_urlsafe(32),
        "YGGDRAS_LOCAL_DATA": str(folder / "local-data"),
    }
    return "".join(f"{name}={quoted(value)}\n" for name, value in lines.items())


def temporal(binary: str | None) -> dict:
    """The Temporal CLI installed in the image, fingerprinted the way the laptop's is."""
    path = Path(binary or "/opt/temporal/temporal")
    return {"binary": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def runtime(env=os.environ, folder: Path | None = None) -> dict:
    folder = folder or home()
    return {
        "version": 1,
        "database_host": "remote",
        "storage_layout": "shared-schemas-v1",
        "origin": env["YGGDRESS_ORIGIN"].rstrip("/"),
        "password_hash": env["YGGDRESS_PASSWORD_HASH"],
        "database_url": env["YGGDRESS_DATABASE_URL"],
        "migration_url": env["YGGDRESS_MIGRATION_URL"],
        "admin_url": env["YGGDRESS_ADMIN_URL"],
        "brain_env": str(REPO / ".env"),
        "postgres_bin": "/usr/lib/postgresql/17/bin",
        "mobile_sensitive_access": env.get("YGGDRESS_MOBILE_SENSITIVE_ACCESS", "1") == "1",
        "agents": {
            "enabled": True,
            "lia_skills": str(REPO / "app" / "skills" / "lia"),
            **execution(env),
        },
    }


def execution(env=os.environ) -> dict:
    """Lean by default (fits a 1 GB container): agents run in threads and a plain thread
    sweeps the calls every 15 s, with no Temporal server. YGGDRAS_EXECUTION_BACKEND=temporal
    brings the laptop's Temporal set-up back when the host has the memory for it."""
    if env.get("YGGDRAS_EXECUTION_BACKEND", "threads") == "temporal":
        return {"execution_backend": "temporal", "temporal": temporal(env.get("TEMPORAL_BINARY"))}
    return {"execution_backend": "threads"}


FIREBASE_JSON = "FIREBASE_SERVICE_ACCOUNT_JSON"


def firebase_account(env=os.environ, folder: Path | None = None) -> Path | None:
    """Railway variables hold text, not files, but Firebase wants a service-account file.
    When FIREBASE_SERVICE_ACCOUNT_JSON holds the file's contents, write it to a private file
    in the runtime home on every start, and point FIREBASE_SERVICE_ACCOUNT_FILE at it. Its
    contents are never printed: a bad value is named, not echoed."""
    raw = env.get(FIREBASE_JSON, "").strip()
    if not raw:
        return None
    try:
        account = json.loads(raw)
    except json.JSONDecodeError:
        raise SystemExit(f"{FIREBASE_JSON} is not valid JSON (paste the whole file).") from None
    if not (
        isinstance(account, dict)
        and account.get("type") == "service_account"
        and account.get("private_key")
        and account.get("client_email")
    ):
        raise SystemExit(f"{FIREBASE_JSON} is not a Firebase service-account file.")
    secrets_dir = (folder or home()) / "secrets"
    secrets_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(secrets_dir, 0o700)
    target = secrets_dir / "firebase-service-account.json"
    partial = target.with_name(target.name + ".partial")
    partial.write_text(raw, encoding="utf-8")
    os.chmod(partial, 0o600)
    partial.replace(target)
    env["FIREBASE_SERVICE_ACCOUNT_FILE"] = str(target)
    return target


def bootstrap(env=os.environ, folder: Path | None = None) -> Path:
    """Write the private settings files. Returns the runtime home."""
    from .local_runtime import atomic_json

    folder = folder or home()
    gaps = missing(env)
    if gaps:
        raise SystemExit("Set these Railway variables first: " + ", ".join(gaps))
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "local-data").mkdir(exist_ok=True)
    firebase_account(env, folder)  # before the brain .env, which passes the file's path on
    target = REPO / ".env"
    partial = target.with_name(".env.partial")
    partial.write_text(brain_env(env, folder), encoding="utf-8")
    os.chmod(partial, 0o600)
    partial.replace(target)
    atomic_json(folder / "runtime.json", runtime(env, folder))
    os.chmod(folder / "runtime.json", 0o600)
    return folder


def main():
    from .local_runtime import serve

    folder = bootstrap()
    os.environ["YGGDRAS_LOG_STDOUT"] = "1"  # child services log to Railway's log stream
    # The voice worker starts a call's process when a call comes in, instead of keeping a
    # spare one in memory (a few seconds more at answer, a few hundred MB less).
    os.environ.setdefault("YGGDRAS_VOICE_IDLE_PROCESSES", "0")
    print(json.dumps({"hosted": True, "home": str(folder)}), flush=True)
    serve(folder, hosted=True)


if __name__ == "__main__":
    main()
