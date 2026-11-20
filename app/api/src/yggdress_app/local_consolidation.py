"""Owner-authorized local copy/cutover. No cloud deployment or memory engine edits."""

import argparse
import hashlib
import json
import os
import signal
import subprocess
import time
from contextlib import ExitStack
from datetime import UTC, datetime
from pathlib import Path
from urllib.request import Request, urlopen

import psycopg

from .backup import fingerprints, private_database_url
from .local_runtime import atomic_json, brain_http, default_home, ensure, pg_start, status
from .notes_proxy import NotesError
from .shared_database import (
    LAYOUT,
    ConsolidationError,
    _source_guard,
    prepare,
    schema_digest,
    text_settings,
    verify_boundaries,
)


def replace_brain_connection(raw, connection):
    """Change exactly one existing private setting, preserving all other lines."""
    if any(character in connection for character in ("\r", "\n", "'")):
        raise ConsolidationError(
            "The generated connection cannot be written as an environment value."
        )
    bom = raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8-sig")
    updated, matches = [], 0
    for line in text.splitlines(keepends=True):
        if line.partition("=")[0].strip() == "BRAIN_DATABASE_URL":
            ending = "\r\n" if line.endswith("\r\n") else "\n" if line.endswith("\n") else ""
            updated.append("BRAIN_DATABASE_URL='" + connection + "'" + ending)
            matches += 1
        else:
            updated.append(line)
    if matches != 1:
        raise ConsolidationError("Configure exactly one existing Brain database connection.")
    return (b"\xef\xbb\xbf" if bom else b"") + "".join(updated).encode("utf-8")


def _write_bytes(path, value):
    pending = path.with_suffix(path.suffix + ".consolidation-pending")
    with pending.open("xb") as stream:
        stream.write(value)
    pending.replace(path)


def _stop_application(home):
    current = status(home)
    if "origin" not in current:
        return False
    control = json.loads((home / "service.json").read_text())
    with urlopen(
        Request(
            f"http://127.0.0.1:{control['control_port']}/stop",
            data=b"",
            headers={"Authorization": "Bearer " + control["token"]},
        ),
        timeout=5,
    ):
        pass
    for _ in range(240):
        if not (home / "postgres/postmaster.pid").exists():
            return True
        time.sleep(0.25)
    raise ConsolidationError("The owned application services did not stop cleanly.")


def _stop_brain_launcher(config):
    """Stop only the known existing loopback launcher; refuse unrelated listeners."""
    if os.name != "nt":
        raise ConsolidationError(
            "Local activation currently supports the existing Windows runtime."
        )
    script = (
        "$listeners=@(Get-NetTCPConnection -State Listen -LocalPort 8100 "
        "-ErrorAction SilentlyContinue); "
        "$result=@($listeners | Select-Object -ExpandProperty OwningProcess -Unique | "
        "ForEach-Object { Get-CimInstance Win32_Process -Filter ('ProcessId='+$_) | "
        "Select-Object ProcessId,CommandLine }); ConvertTo-Json -InputObject $result -Compress"
    )
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", script],
        capture_output=True,
        check=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    processes = json.loads(result.stdout.decode("utf-8-sig") or "[]")
    project = str(Path(config["brain_env"]).parent).casefold()
    launcher = str(Path(__file__).resolve().parents[2] / "scripts/brain_api_service.py").casefold()
    for process in processes:
        command = (process.get("CommandLine") or "").replace("/", "\\").casefold()
        if launcher.replace("/", "\\") not in command or project.replace("/", "\\") not in command:
            raise ConsolidationError(
                "An unrelated Brain-port listener must be stopped by its owner."
            )
        os.kill(int(process["ProcessId"]), signal.SIGTERM)


def prepare_local(home, destination_text_settings=None):
    home = Path(home).resolve(strict=True)
    config_raw = (home / "runtime.json").read_bytes()
    config = json.loads(config_raw)
    shared = config.get("storage_layout") == LAYOUT
    if shared and destination_text_settings is None:
        raise ConsolidationError("This local runtime is already configured for shared storage.")
    marker = home / "maintenance.json"
    if marker.exists():
        raise ConsolidationError(
            "Finish or resolve the existing local maintenance operation first."
        )
    stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    archive = home / "backups" / ("unified_" + stamp)
    atomic_json(marker, {"operation": "shared-database", "archive": str(archive)})
    was_ready = status(home).get("ready", False)
    try:
        _stop_application(home)
        _stop_brain_launcher(config)
        pg_start(home, config)
        brain_raw = Path(config["brain_env"]).read_bytes()
        copied = prepare(
            config["admin_url"],
            config["database_url"],
            config["admin_url"] if shared else private_database_url(config["brain_env"]),
            Path(config["postgres_bin"]),
            archive,
            "yggdras_unified_" + stamp,
            shared_source=shared,
            destination_text_settings=destination_text_settings,
        )
        # These files contain credentials and remain inside the existing private
        # runtime directory. They are never copied to the checkout or console.
        (archive / "runtime-before.json").write_bytes(config_raw)
        (archive / "brain-before.env").write_bytes(brain_raw)
        copied["runtime_sha256"] = hashlib.sha256(config_raw).hexdigest()
        copied["brain_environment_sha256"] = hashlib.sha256(brain_raw).hexdigest()
        atomic_json(archive / "prepared.json", copied)
        atomic_json(home / "consolidation.json", {"archive": str(archive), "state": "prepared"})
        return copied["report"]
    except Exception as error:
        import traceback

        if archive.is_dir():
            atomic_json(
                archive / "prepare-error.json",
                {
                    "type": type(error).__name__,
                    "frames": [
                        {"file": Path(frame.filename).name, "line": frame.lineno}
                        for frame in traceback.extract_tb(error.__traceback__)
                    ],
                },
            )
        marker.unlink(missing_ok=True)
        if was_ready:
            ensure(home)
        raise


def activate_local(home):
    home = Path(home).resolve(strict=True)
    pointer = json.loads((home / "consolidation.json").read_text())
    if pointer["state"] != "prepared":
        raise ConsolidationError("A verified, unactivated copy is required.")
    archive = Path(pointer["archive"]).resolve(strict=True)
    if not archive.is_relative_to((home / "backups").resolve()):
        raise ConsolidationError(
            "The prepared archive must remain in the private backup directory."
        )
    prepared = json.loads((archive / "prepared.json").read_text())
    original = (archive / "runtime-before.json").read_bytes()
    config = json.loads(original)
    brain_file = Path(config["brain_env"])
    brain_original = (archive / "brain-before.env").read_bytes()
    if (
        hashlib.sha256((home / "runtime.json").read_bytes()).hexdigest()
        != prepared["runtime_sha256"]
        or hashlib.sha256(brain_file.read_bytes()).hexdigest()
        != prepared["brain_environment_sha256"]
    ):
        raise ConsolidationError("Service configuration changed after the verified copy.")
    switched = False
    shared_source = config.get("storage_layout") == LAYOUT
    brain_source = (
        config["admin_url"] if shared_source else private_database_url(config["brain_env"])
    )
    try:
        with ExitStack() as stack:
            app = stack.enter_context(psycopg.connect(config["admin_url"]))
            brain = stack.enter_context(psycopg.connect(brain_source))
            app_now, brain_now = (
                _source_guard(app, "app", shared_source),
                _source_guard(brain, "brain", shared_source),
            )
            expected = prepared["report"]["snapshot"]
            if {**app_now["tables"], **brain_now["tables"]} != expected["tables"] or {
                **app_now["sequences"],
                **brain_now["sequences"],
            } != expected["sequences"]:
                raise ConsolidationError(
                    "Source data changed after preparation; create a fresh copy."
                )
            for namespace, source in (
                ("app", config["admin_url"]),
                ("brain", brain_source),
            ):
                if (
                    schema_digest(source, namespace, config["postgres_bin"])
                    != prepared["report"]["schema_hashes"][namespace]
                ):
                    raise ConsolidationError("A source schema changed after preparation.")
            with psycopg.connect(prepared["admin_url"]) as target:
                if fingerprints(target) != expected:
                    raise ConsolidationError("The prepared destination changed before activation.")
            verify_boundaries(
                prepared["admin_url"],
                prepared["database_url"],
                prepared["migration_url"],
                prepared["brain_url"],
            )
            updated = {
                **config,
                **{
                    key: prepared[key]
                    for key in (
                        "storage_layout",
                        "admin_url",
                        "database_url",
                        "migration_url",
                    )
                },
            }
            updated["consolidation_archive"] = str(archive)
            switched = True
            _write_bytes(
                brain_file, replace_brain_connection(brain_original, prepared["brain_url"])
            )
            atomic_json(home / "runtime.json", updated)
            (home / "maintenance.json").unlink()
            if not ensure(home).get("ready"):
                raise ConsolidationError("Combined local services did not become ready.")
            # Read the actual existing Brain API before accepting the cutover.
            # This never invokes a model or submits a Brain mutation.
            for attempt in range(10):
                try:
                    brain_http(config["brain_env"]).call("GET", "search?q=")
                    break
                except NotesError:
                    if attempt == 9:
                        raise ConsolidationError(
                            "The existing Brain API did not become readable."
                        ) from None
                    time.sleep(0.5)
        pointer["state"] = "active"
        atomic_json(home / "consolidation.json", pointer)
        atomic_json(
            archive / "activation.json", {"active": True, "original_databases_retained": True}
        )
        return {**prepared["report"], "activated": True, "services_ready": True}
    except Exception as error:
        import traceback

        atomic_json(
            archive / "activation-error.json",
            {
                "type": type(error).__name__,
                "frames": [
                    {"file": Path(frame.filename).name, "line": frame.lineno}
                    for frame in traceback.extract_tb(error.__traceback__)
                ],
            },
        )
        if switched:
            _stop_application(home)
            _stop_brain_launcher(config)
            _write_bytes(brain_file, brain_original)
            _write_bytes(home / "runtime.json", original)
            pg_start(home, config)
            (home / "maintenance.json").unlink(missing_ok=True)
            pointer["state"] = "rolled_back"
            atomic_json(home / "consolidation.json", pointer)
            ensure(home)
        raise


def main():
    parser = argparse.ArgumentParser(description="Verified local PostgreSQL consolidation")
    parser.add_argument("--home", type=Path, default=default_home())
    parser.add_argument("action", choices=("prepare", "activate", "retry", "preserve-brain-text"))
    args = parser.parse_args()
    try:
        if args.action == "preserve-brain-text":
            home = args.home.resolve(strict=True)
            config = json.loads((home / "runtime.json").read_text())
            pointer = json.loads((home / "consolidation.json").read_text())
            archive = Path(pointer["archive"])
            prior = json.loads((archive / "prepared.json").read_text())
            desired = prior["report"].get("text_settings")
            if desired is None:
                with psycopg.connect(private_database_url(archive / "brain-before.env")) as source:
                    desired = text_settings(source)
            with psycopg.connect(config["admin_url"]) as current:
                if text_settings(current) == desired:
                    raise ConsolidationError("The Brain text settings are already preserved.")
            prepare_local(home, desired)
            result = activate_local(home)
        elif args.action == "retry":
            home = args.home.resolve(strict=True)
            pointer = json.loads((home / "consolidation.json").read_text())
            if pointer["state"] != "rolled_back":
                raise ConsolidationError("Retry requires a previously rolled-back activation.")
            if (home / "maintenance.json").exists():
                raise ConsolidationError("Another maintenance operation is already in progress.")
            atomic_json(home / "maintenance.json", {"operation": "shared-database-retry"})
            config = json.loads((home / "runtime.json").read_text())
            try:
                _stop_application(home)
                _stop_brain_launcher(config)
                pg_start(home, config)
                pointer["state"] = "prepared"
                atomic_json(home / "consolidation.json", pointer)
                result = activate_local(home)
            except Exception:
                (home / "maintenance.json").unlink(missing_ok=True)
                ensure(home)
                raise
        else:
            result = (
                prepare_local(args.home) if args.action == "prepare" else activate_local(args.home)
            )
        print(
            json.dumps(
                {key: value for key, value in result.items() if key not in ("snapshot", "archive")}
            )
        )
    except Exception as error:  # noqa: BLE001 -- never echo transport errors or connection strings
        message = str(error) if isinstance(error, ConsolidationError) else type(error).__name__
        print("Consolidation stopped safely: " + message)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
