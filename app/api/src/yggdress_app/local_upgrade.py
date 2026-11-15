"""Explicit app-only upgrade: verify a migrated restore before changing live data."""

import argparse
import hashlib
import json
import re
import tempfile
import time
from pathlib import Path
from urllib.request import Request, urlopen

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict

from .backup import client_environment, database_backup, fresh_cluster, tool
from .database import Database
from .local_runtime import atomic_json, default_home, ensure, pg_start, status
from .runtime_grants import grant_runtime


def columns(db):
    return {
        row[0]: [
            value[0]
            for value in db.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_schema=%s AND table_name=%s ORDER BY ordinal_position",
                ("app", row[0]),
            )
        ]
        for row in db.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname='app' AND tablename<>'schema_migrations' ORDER BY tablename"
        ).fetchall()
    }


def projection(db, specification):
    """Compare original columns so adding defaulted routing metadata loses no data."""
    result = {}
    db.execute("SET TIME ZONE 'UTC'")
    for table, fields in specification.items():
        digest = hashlib.sha256()
        query = sql.SQL(
            'COPY (SELECT to_jsonb(t)::text FROM (SELECT {} FROM app.{}) t ORDER BY (to_jsonb(t)::text) COLLATE "C") TO STDOUT'
        ).format(sql.SQL(",").join(map(sql.Identifier, fields)), sql.Identifier(table))
        with db.cursor().copy(query) as copy:
            for block in copy:
                digest.update(block)
        result[table] = {
            "rows": db.execute(
                sql.SQL("SELECT count(*) FROM app.{}").format(sql.Identifier(table))
            ).fetchone()[0],
            "sha256": digest.hexdigest(),
        }
    return result


def upgrade(home, build):
    config = json.loads((home / "runtime.json").read_text(encoding="utf-8"))
    if (
        not re.fullmatch(r"\.next-[a-z0-9-]+", build)
        or build == config["build_dir"]
        or not (Path(config["web"]) / build / "BUILD_ID").is_file()
    ):
        raise RuntimeError("Build a separate verified production candidate first.")
    if not status(home).get("ready"):
        raise RuntimeError("Start the owned application before preparing its upgrade.")
    guard = psycopg.connect(config["admin_url"])
    marker = home / "maintenance.json"
    if marker.exists():
        raise RuntimeError("A local upgrade is already marked in progress.")
    stopped = False
    try:
        actual = Path(guard.execute("SHOW data_directory").fetchone()[0]).resolve()
        if actual != (home / "postgres").resolve():
            raise RuntimeError("The upgrade target is not the owned application cluster.")
        namespaces = {row[0] for row in guard.execute("SELECT nspname FROM pg_namespace")}
        if "brain" in namespaces or "app" not in namespaces:
            raise RuntimeError("Only an application database may be upgraded.")
        guard.execute("SET lock_timeout='5s'")
        guard.execute("SET idle_in_transaction_session_timeout='300s'")
        tables = [
            row[0]
            for row in guard.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname='app' ORDER BY tablename"
            )
        ]
        guard.execute(
            sql.SQL("LOCK TABLE {} IN SHARE MODE").format(
                sql.SQL(",").join(sql.Identifier("app", name) for name in tables)
            )
        )
        spec = columns(guard)
        before = projection(guard, spec)
        dump = (
            home
            / "backups"
            / ("application-before-connected-" + time.strftime("%Y%m%d-%H%M%S") + ".dump")
        )
        binary = Path(config["postgres_bin"])
        with tempfile.TemporaryDirectory(prefix="yggdress-app-upgrade-") as temporary:
            work = Path(temporary)
            verify = work / "verify"
            verify.mkdir()
            report = database_backup(config["admin_url"], dump, binary, verify)
            staged = work / "staged"
            staged.mkdir()
            with fresh_cluster(binary, staged) as destination:
                tool(
                    binary / "pg_restore.exe",
                    [
                        "--no-owner",
                        "--no-privileges",
                        "--single-transaction",
                        "--exit-on-error",
                        "--dbname",
                        "postgres",
                        dump,
                    ],
                    client_environment(destination),
                )
                Database(destination).migrate()
                with psycopg.connect(destination) as db:
                    if projection(db, spec) != before:
                        raise RuntimeError(
                            "Staged migration changed an existing application value."
                        )
                    if db.execute("SELECT to_regnamespace('brain')").fetchone()[0] is not None:
                        raise RuntimeError("Unexpected Brain schema in the app upgrade.")
        atomic_json(
            home / "backups/connected-upgrade-verification.json",
            {
                "backup_verified": True,
                "staged_migration_preserves_original_columns": True,
                "snapshot": report["snapshot"],
            },
        )
        # Keep the source freeze until the exact owned services stop accepting writes.
        atomic_json(marker, {"build": build, "started": time.time()})
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
        stopped = True
        guard.close()
        for _ in range(240):
            if not (home / "postgres/postmaster.pid").exists():
                break
            time.sleep(0.25)
        if (home / "postgres/postmaster.pid").exists():
            raise RuntimeError("The owned application database did not stop cleanly.")
        pg_start(home, config)
        Database(config["admin_url"]).migrate()
        with psycopg.connect(config["admin_url"]) as db:
            if projection(db, spec) != before:
                raise RuntimeError("Existing application values changed during the upgrade.")
            grant_runtime(db, conninfo_to_dict(config["database_url"])["user"])
            versions = [
                row[0]
                for row in db.execute("SELECT version FROM app.schema_migrations ORDER BY version")
            ]
        config["build_dir"] = build
        atomic_json(home / "runtime.json", config)
        marker.unlink()
        if not ensure(home)["ready"]:
            raise RuntimeError("The upgraded services did not become ready.")
        return {
            "backup_verified": True,
            "staged_migration_verified": True,
            "original_values_preserved": True,
            "serving": True,
            "schema": versions,
            "build": build,
        }
    finally:
        guard.close()
        if marker.exists() and not stopped:
            marker.unlink()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--home", type=Path, default=default_home())
    parser.add_argument("--build", required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(upgrade(args.home, args.build)))
    except Exception:  # noqa: BLE001 -- administrative DSNs must never enter console output
        print(
            "Application upgrade stopped safely. Inspect the private upgrade state; existing data and the verified backup remain available."
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
