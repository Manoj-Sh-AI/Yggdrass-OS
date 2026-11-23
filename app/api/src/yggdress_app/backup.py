"""Read-only Brain backup; restore checks run only in a newly initialized local cluster."""

import argparse
import hashlib
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import tempfile
import zipfile
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

import psycopg
from psycopg import IsolationLevel, sql
from psycopg.conninfo import conninfo_to_dict

EXCLUDED = {
    ".git",
    "node_modules",
    ".venv",
    ".next",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    "test-results",
    "playwright-report",
}


class BackupError(RuntimeError):
    pass


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def markdown_archive(sources, target):
    """All selected Markdown, byte for byte; never follow links or overwrite an archive."""
    sources = [Path(p).resolve(strict=True) for p in sources]
    names = [p.name.casefold() for p in sources]
    if len(set(names)) != len(names):
        raise BackupError("Source folder names must be distinct in the archive.")
    records = []
    with zipfile.ZipFile(target, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for root in sources:
            if not root.is_dir():
                raise BackupError("Each Markdown source must be a directory.")

            def unreadable(error):
                raise error

            for folder, directories, files in os.walk(root, followlinks=False, onerror=unreadable):
                directories[:] = sorted(d for d in directories if d not in EXCLUDED)
                for name in directories:
                    path = Path(folder) / name
                    if path.is_symlink() or path.is_junction():
                        raise BackupError(
                            "Linked directories are refused; select their targets explicitly."
                        )
                for name in sorted(files):
                    if not name.lower().endswith(".md"):
                        continue
                    path = Path(folder) / name
                    if path.is_symlink() or not path.resolve().is_relative_to(root):
                        raise BackupError("A Markdown path escapes the selected source.")
                    before = path.stat()
                    data = path.read_bytes()
                    after = path.stat()
                    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                        raise BackupError(
                            "A Markdown file changed during backup; retry the snapshot."
                        )
                    member = (Path(root.name) / path.relative_to(root)).as_posix()
                    archive.writestr(member, data)
                    records.append(
                        {
                            "path": member,
                            "bytes": len(data),
                            "sha256": hashlib.sha256(data).hexdigest(),
                        }
                    )
    verify_markdown(target, records)
    return records


def verify_markdown(path, records):
    with zipfile.ZipFile(path) as archive:
        if archive.testzip() or sorted(archive.namelist()) != sorted(r["path"] for r in records):
            raise BackupError("Markdown archive contents failed verification.")
        for record in records:
            data = archive.read(record["path"])
            if len(data) != record["bytes"] or hashlib.sha256(data).hexdigest() != record["sha256"]:
                raise BackupError("Markdown archive checksum mismatch.")


def tool(binary, args, env=None, capture=True, explain=None):
    """Run a PostgreSQL tool. `explain` maps private paths to placeholders and opts in to
    showing the tool's own error lines; use it only for tools that never see credentials."""
    output = (
        {"capture_output": True}
        if capture
        else {"stdout": subprocess.DEVNULL, "stderr": subprocess.STDOUT}
    )
    result = subprocess.run(
        [str(binary), *map(str, args)],
        env=env,
        check=False,
        timeout=300,
        **output,
    )
    if result.returncode:
        # Tool errors can contain private SQL/object names; never print raw stderr or URLs.
        message = f"{Path(binary).stem} failed with exit code {result.returncode}."
        if explain is not None:
            message += error_excerpt(result.stderr, explain)
        raise BackupError(message)
    return result.stdout or b""


def error_excerpt(stderr, placeholders, limit=3):
    """The tool's own error/detail/hint lines, with private paths replaced, never raw output."""
    text = (stderr or b"").decode("utf8", "replace")
    for private, label in sorted(placeholders.items(), key=lambda item: -len(item[0])):
        for spelling in {private, private.replace("\\", "/"), private.replace("/", "\\")}:
            text = text.replace(spelling, label)
    keep = [
        line.strip()[:300]
        for line in text.splitlines()
        if any(tag in line for tag in (": error:", ": detail:", ": hint:", "FATAL:"))
    ]
    return (" " + " | ".join(keep[-limit:])) if keep else ""


def client_environment(url=None):
    allowed = {
        "PATH",
        "PATHEXT",
        "SYSTEMROOT",
        "WINDIR",
        "TEMP",
        "TMP",
        "HOME",
        "USERPROFILE",
        "APPDATA",
        "LOCALAPPDATA",
        "LANG",
        "LC_ALL",
    }
    env = {k: v for k, v in os.environ.items() if k.upper() in allowed}
    if url:
        params = conninfo_to_dict(url)
        for key, value in params.items():
            name = {"dbname": "PGDATABASE", "client_encoding": "PGCLIENTENCODING"}.get(
                key, "PG" + key.upper()
            )
            env[name] = value
    env["PGCONNECT_TIMEOUT"] = "10"
    env["PGOPTIONS"] = env.get("PGOPTIONS", "") + " -c timezone=UTC"
    return env


def fingerprints(conn, schemas=None):
    """Row, sequence and large-object fingerprints. `schemas` limits them to those
    schemas (a hosted database such as Supabase also holds the host's own schemas)."""
    # Timestamp JSON must compare independently of each server/session timezone.
    conn.execute("SET TIME ZONE 'UTC'")
    tables, sequences, objects = {}, {}, []
    names = conn.execute(
        "SELECT n.nspname,c.relname,c.relkind FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE c.relkind IN ('r','p','m','f','S') AND n.nspname NOT IN ('pg_catalog','information_schema') "
        "AND n.nspname NOT LIKE 'pg_toast%%' AND n.nspname NOT LIKE 'pg_temp%%' "
        "AND (%s::text[] IS NULL OR n.nspname = ANY(%s::text[])) ORDER BY 1,2",
        (schemas, schemas),
    ).fetchall()
    for namespace, name, kind in names:
        identifier = sql.Identifier(namespace, name)
        key = f"{namespace}.{name}"
        if kind == "f":
            raise BackupError("Foreign-table contents require a separate backup strategy.")
        if kind == "S":
            sequences[key] = list(
                conn.execute(
                    sql.SQL("SELECT last_value,is_called FROM {}").format(identifier)
                ).fetchone()
            )
            continue
        count = conn.execute(sql.SQL("SELECT count(*) FROM {}").format(identifier)).fetchone()[0]
        digest = hashlib.sha256()
        query = sql.SQL(
            'COPY (SELECT to_jsonb(t)::text FROM {} t ORDER BY (to_jsonb(t)::text) COLLATE "C") TO STDOUT'
        ).format(identifier)
        with conn.cursor().copy(query) as copy:
            for block in copy:
                digest.update(block)
        tables[key] = {"rows": count, "sha256": digest.hexdigest()}
    for (oid,) in conn.execute("SELECT oid FROM pg_largeobject_metadata ORDER BY oid"):
        data = conn.execute("SELECT lo_get(%s)", (oid,)).fetchone()[0]
        objects.append({"oid": oid, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
    return {"tables": tables, "sequences": sequences, "large_objects": objects}


# Supabase stores its own per-column setting (pg_attver) that standard PostgreSQL
# rejects; it is host bookkeeping, not data. Dumps keep it; restores and schema
# comparisons drop exactly these lines.
HOST_ONLY = re.compile(
    rb"^ALTER TABLE ONLY [^\n]*ALTER COLUMN [^\n]*SET \(pg_attver=\d+\);\r?\n", re.MULTILINE
)


def portable(text: bytes) -> bytes:
    return HOST_ONLY.sub(b"", text)


def restore_portable(binary_dir, dump, env, dbname, args=()):
    """pg_restore -> SQL -> drop host-only lines -> psql in one transaction that stops at
    the first error. Returns (exit code, stderr)."""
    suffix = ".exe" if os.name == "nt" else ""
    script = subprocess.run(
        [str(Path(binary_dir) / ("pg_restore" + suffix)), "--file=-", *map(str, args), str(dump)],
        capture_output=True, check=False, timeout=600,
    )  # fmt: skip
    if script.returncode:
        return script.returncode, script.stderr
    applied = subprocess.run(
        [str(Path(binary_dir) / ("psql" + suffix)), "-X", "-q", "--no-password",
         "-v", "ON_ERROR_STOP=1", "--single-transaction", "-d", dbname, "-f", "-"],
        input=portable(script.stdout), env=env, capture_output=True, check=False, timeout=600,
    )  # fmt: skip
    return applied.returncode, applied.stderr


def schema_fingerprint(binary, env, snapshot=None, schemas=None):
    args = ["--schema-only", "--no-owner", "--no-privileges", "--no-password"]
    if snapshot:
        args.append("--snapshot=" + snapshot)
    args += [f"--schema={name}" for name in schemas or ()]
    text = portable(tool(binary, args, env)).decode("utf-8")
    lines = [
        line.rstrip()
        for line in text.splitlines()
        if line.strip() and not line.startswith(("--", "\\restrict", "\\unrestrict"))
    ]
    return hashlib.sha256("\n".join(lines).encode()).hexdigest()


def server_options(port: int) -> str:
    """TCP on localhost only. On POSIX the local socket is turned off: Debian/Ubuntu builds
    put it in /var/run/postgresql, which an ordinary user (a CI runner, WSL2) cannot
    write, so the scratch server would fail to start; every connection here is TCP."""
    options = f"-h 127.0.0.1 -p {port}"
    return options if os.name == "nt" else options + " -c unix_socket_directories=''"


@contextmanager
def fresh_cluster(binary_dir, parent):
    """No source connection can be a restore destination: create and own a new cluster."""
    data = (parent / "restore-cluster").resolve()
    if not data.is_relative_to(parent.resolve()) or data.exists():
        raise BackupError("Unsafe restore workspace.")
    suffix = ".exe" if os.name == "nt" else ""
    binary = lambda name: binary_dir / (name + suffix)
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    tool(
        binary("initdb"),
        ["-D", data, "-A", "trust", "-U", "backup_verify", "--no-locale", "--encoding=UTF8"],
        # initdb gets no connection or password, so its own error lines are safe to show.
        explain={str(data): "<restore-cluster>", str(parent.resolve()): "<restore-workspace>"},
    )
    tool(
        binary("pg_ctl"),
        ["-D", data, "-l", parent / "restore.log", "-o", server_options(port), "-w", "start"],
        capture=False,
    )
    target = f"host=127.0.0.1 port={port} user=backup_verify dbname=postgres"
    try:
        yield target
    finally:
        # This data path was created by this invocation and checked against its private temp root.
        if data.is_relative_to(parent.resolve()):
            tool(binary("pg_ctl"), ["-D", data, "-m", "fast", "-w", "stop"], capture=False)


def database_backup(url, target, binary_dir, workspace, schemas=None):
    """Dump and verify by a complete isolated restore. `schemas` limits the dump to the
    app's own schemas on a hosted database (Supabase keeps its own beside them)."""
    suffix = ".exe" if os.name == "nt" else ""
    # A schema filter would leave out large objects (they belong to no schema): keep them.
    scope = [f"--schema={name}" for name in schemas or ()] + (
        ["--large-objects"] if schemas else []
    )
    pg_dump = binary_dir / ("pg_dump" + suffix)
    env = client_environment(url)
    with psycopg.connect(url, connect_timeout=10) as source:
        source.read_only = True
        source.isolation_level = IsolationLevel.REPEATABLE_READ
        source.execute("SET TIME ZONE 'UTC'")
        snapshot = source.execute("SELECT pg_export_snapshot()").fetchone()[0]
        expected = fingerprints(source, schemas)
        roles = [
            r[0]
            for r in source.execute("SELECT rolname FROM pg_roles WHERE rolname NOT LIKE 'pg_%'")
        ]
        schema_hash = schema_fingerprint(pg_dump, env, snapshot, schemas)
        tool(
            pg_dump,
            ["--format=custom", "--no-password", "--snapshot=" + snapshot, *scope,
             "--file", target],
            env,
        )  # fmt: skip
        source.rollback()
    # List is an extra format check; the actual verification is the complete isolated restore.
    tool(binary_dir / ("pg_restore" + suffix), ["--list", target])
    with fresh_cluster(binary_dir, workspace) as target_url:
        with psycopg.connect(target_url, autocommit=True) as restored:
            for role in roles:
                if role != "backup_verify":
                    restored.execute(sql.SQL("CREATE ROLE {} NOLOGIN").format(sql.Identifier(role)))
        restore_env = client_environment(target_url)
        code, _ = restore_portable(
            binary_dir, target, restore_env, "postgres",
            ["--clean", "--if-exists", "--no-owner", "--no-privileges"],
        )  # fmt: skip
        if code:
            raise BackupError(f"The verification restore failed with exit code {code}.")
        with psycopg.connect(target_url) as restored:
            restored.read_only = True
            restored.execute("SET TIME ZONE 'UTC'")
            actual = fingerprints(restored, schemas)
        restored_schema = schema_fingerprint(pg_dump, restore_env, schemas=schemas)
        if actual != expected:
            raise BackupError("Restored database data differs from the exported snapshot.")
        if restored_schema != schema_hash:
            raise BackupError("Restored schema differs from the exported snapshot.")
    return {
        "status": "restore_verified",
        "snapshot": expected,
        "schema_sha256": schema_hash,
        "scope": (
            "schemas " + ", ".join(schemas)
            if schemas
            else "full logical database; server roles/passwords and server configuration excluded"
        ),
        "verification_ownership": "isolated verification role; production ownership/ACLs not replayed",
    }


def publish(stage, destination, name):
    destination = Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    partial, final = destination / (name + ".incomplete"), destination / name
    if partial.exists() or final.exists():
        raise BackupError("This backup name already exists; nothing was overwritten.")
    shutil.copytree(stage, partial)
    for path in stage.iterdir():
        if path.is_file() and sha256(path) != sha256(partial / path.name):
            raise BackupError("The copied OneDrive backup failed its checksum check.")
    partial.rename(final)
    return final


def private_database_url(env_file):
    value = os.environ.get("BRAIN_DATABASE_URL", "")
    if env_file and not value:
        for line in Path(env_file).read_text(encoding="utf-8").splitlines():
            key, sep, raw = line.partition("=")
            if sep and key.strip() == "BRAIN_DATABASE_URL":
                value = raw.strip().strip('"').strip("'")
    if not value:
        raise BackupError("Configure the database privately; its connection is never printed.")
    return value


def main():
    parser = argparse.ArgumentParser(
        description="Non-destructive Markdown archive and full database restore verification"
    )
    parser.add_argument("--source", type=Path, action="append", required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--pg-bin", type=Path, default=Path("C:/Program Files/PostgreSQL/18/bin"))
    args = parser.parse_args()
    destination = args.destination.resolve()
    for root in args.source:
        if destination.is_relative_to(root.resolve()):
            raise BackupError("The backup destination must be outside every selected source.")
    name = datetime.now(UTC).strftime("%Y-%m-%d_%H-%M-%SZ") + "_" + secrets.token_hex(3)
    with tempfile.TemporaryDirectory(prefix="yggdras-backup-") as temporary:
        workspace = Path(temporary).resolve()
        if not workspace.is_relative_to(Path(tempfile.gettempdir()).resolve()):
            raise BackupError("Unexpected temporary workspace.")
        stage = workspace / "verified-backup"
        stage.mkdir()
        records = markdown_archive(args.source, stage / "markdown.zip")
        print(
            f"Archived and verified {len(records)} Markdown files; source files unchanged.",
            flush=True,
        )
        database = database_backup(
            private_database_url(args.env_file),
            stage / "brain-postgresql.dump",
            args.pg_bin,
            workspace,
        )
        print("Full database restored and matched in an isolated PostgreSQL cluster.", flush=True)
        artifacts = {
            p.name: {"bytes": p.stat().st_size, "sha256": sha256(p)} for p in stage.iterdir()
        }
        manifest = {
            "status": "verified",
            "created_utc": datetime.now(UTC).isoformat(),
            "markdown_files": records,
            "database": database,
            "artifacts": artifacts,
            "cloud_sync": "not verified by copying into the OneDrive folder",
        }
        (stage / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        final = publish(stage, destination, name)
        print(
            json.dumps(
                {
                    "status": "verified_local_backup",
                    "destination": str(final),
                    "markdown_files": len(records),
                    "database_tables": len(database["snapshot"]["tables"]),
                    "source_unchanged": True,
                }
            ),
            flush=True,
        )


if __name__ == "__main__":
    try:
        main()
    except BackupError as error:
        raise SystemExit(f"Backup verification stopped: {error} Originals are unchanged.") from None
    except (psycopg.Error, OSError, ValueError):
        raise SystemExit(
            "Backup did not complete verification. Originals are unchanged; no verified backup was published."
        ) from None
