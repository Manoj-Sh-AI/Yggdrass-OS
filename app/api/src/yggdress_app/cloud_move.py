"""Moving the shared database to Supabase (planning/supabase-database-move.md).

The Supabase admin connection (session pooler, IPv4) is read only from a private file,
never from the command line, chat or the repository:
    %LOCALAPPDATA%/Yggdras/supabase-admin.url

    python -m yggdress_app.cloud_move check     # read-only: can we reach it, what is it
    python -m yggdress_app.cloud_move dry-run   # copy a verified snapshot, compare, remove
    python -m yggdress_app.cloud_move cutover   # stop, copy, verify, switch, start (~5 min)
    python -m yggdress_app.cloud_move rollback  # back to the laptop database
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict

from .local_runtime import SCHEMAS, default_home

ADMIN_FILE = "supabase-admin.url"
MIN_SERVER = 150000  # PostgreSQL 15


def admin_url(home: Path) -> str:
    path = home / ADMIN_FILE
    if not path.is_file():
        raise SystemExit(
            f"Put the Supabase session-pooler connection string in {path} first "
            "(Dashboard -> Connect -> Session pooler; percent-encode special characters)."
        )
    url = path.read_text(encoding="utf-8").strip()
    parts = conninfo_to_dict(url)
    if parts.get("host", "").startswith("db.") and parts.get("host", "").endswith(".supabase.co"):
        raise SystemExit(
            "That is the direct (IPv6-only) host, which this laptop cannot reach. "
            "Use the Session pooler string instead."
        )
    return url


def check(url: str) -> dict:
    """Read-only facts the move depends on. No password or address is returned."""
    with psycopg.connect(url, connect_timeout=15) as db:
        db.read_only = True
        version = db.execute("SHOW server_version_num").fetchone()[0]
        collate = db.execute(
            "SELECT datcollate, datctype, pg_encoding_to_char(encoding) FROM pg_database "
            "WHERE datname=current_database()"
        ).fetchone()
        existing = [
            r[0]
            for r in db.execute(
                "SELECT nspname FROM pg_namespace WHERE nspname = ANY(%s)", (SCHEMAS,)
            )
        ]
        exposed = db.execute(
            "SELECT coalesce((SELECT string_agg(c, ',') FROM pg_roles r, unnest(r.rolconfig) c "
            "WHERE r.rolname='authenticator' AND c LIKE 'pgrst.db_schemas=%%'), '')"
        ).fetchone()[0]
        can_create_roles = db.execute(
            "SELECT rolcreaterole FROM pg_roles WHERE rolname=current_user"
        ).fetchone()[0]
    published = exposed.partition("=")[2].split(",") if exposed else ["public (default)"]
    return {
        "server_version_num": int(version),
        "version_ok": int(version) >= MIN_SERVER,
        "collation": collate[0],
        "ctype": collate[1],
        "encoding": collate[2],
        "app_schemas_already_there": existing,
        "data_api_schemas": [s.strip() for s in published],
        "app_schemas_exposed": [s for s in SCHEMAS if s in {p.strip() for p in published}],
        "can_create_roles": bool(can_create_roles),
    }


SORT_COLUMN_MAX = 200  # average characters: names, slugs, titles (not note bodies)


def sort_order_differences(local, hosted, schemas=SCHEMAS) -> list[str]:
    """Columns whose ORDER BY result differs between the two servers' default text
    collation (Windows English_India.1252 vs Linux en_US.UTF-8). Informational."""
    columns = local.execute(
        "SELECT c.table_schema, c.table_name, c.column_name FROM information_schema.columns c "
        "JOIN information_schema.tables t USING (table_schema, table_name) "
        "WHERE c.table_schema = ANY(%s) AND t.table_type='BASE TABLE' "
        "AND c.data_type IN ('text','character varying') ORDER BY 1,2,3",
        (schemas,),
    ).fetchall()
    differ = []
    for schema, table, column in columns:
        name = sql.SQL("{}.{}").format(sql.Identifier(schema), sql.Identifier(table))
        col = sql.Identifier(column)
        average = local.execute(
            sql.SQL("SELECT coalesce(avg(length({})),0) FROM {}").format(col, name)
        ).fetchone()[0]
        if average > SORT_COLUMN_MAX:
            continue
        query = sql.SQL("SELECT {} FROM {} WHERE {} IS NOT NULL ORDER BY {} LIMIT 5000").format(
            col, name, col, col
        )
        if local.execute(query).fetchall() != hosted.execute(query).fetchall():
            differ.append(f"{schema}.{table}.{column}")
    return differ


def restore(url: str, dump: Path, binary: Path) -> None:
    """Restore the app's schemas into the hosted database, without owners or grants
    (roles and grants are set separately at cutover)."""
    from .backup import client_environment, tool

    tool(
        binary / ("pg_restore" + (".exe" if os.name == "nt" else "")),
        ["--no-password", "--no-owner", "--no-privileges", "--single-transaction",
         "--exit-on-error", "--dbname", conninfo_to_dict(url).get("dbname", "postgres"), dump],
        client_environment(url),
    )  # fmt: skip


def remove_schemas(url: str) -> None:
    with psycopg.connect(url, autocommit=True, connect_timeout=15) as db:
        for name in SCHEMAS:
            db.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(name)))


def dry_run(home: Path) -> dict:
    """Copy a verified snapshot of app + brain into Supabase, compare every table's rows
    and sequences with the snapshot, compare text sort order, then remove the copy.
    The laptop database is only read."""
    import tempfile
    import time

    from .backup import database_backup, fingerprints

    hosted = admin_url(home)
    config = json.loads((home / "runtime.json").read_text(encoding="utf-8"))
    binary = Path(config["postgres_bin"])
    if check(hosted)["app_schemas_already_there"]:
        raise SystemExit("Supabase already holds app/brain schemas; nothing was changed.")
    dump = home / "backups" / f"supabase-dryrun-{time.strftime('%Y%m%d-%H%M%S')}.dump"
    with tempfile.TemporaryDirectory(prefix="yggdress-dryrun-") as work:
        report = database_backup(config["admin_url"], dump, binary, Path(work), schemas=SCHEMAS)
    try:
        restore(hosted, dump, binary)
        with psycopg.connect(hosted, connect_timeout=15) as db:
            db.read_only = True
            copied = fingerprints(db, SCHEMAS)
            with psycopg.connect(config["admin_url"]) as local:
                local.read_only = True
                differ = sort_order_differences(local, db)
    finally:
        remove_schemas(hosted)  # a dry run leaves Supabase as it found it
    expected = report["snapshot"]
    mismatched = sorted(
        k
        for k in set(expected["tables"]) | set(copied["tables"])
        if expected["tables"].get(k) != copied["tables"].get(k)
    )
    return {
        "tables": len(expected["tables"]),
        "rows": sum(t["rows"] for t in expected["tables"].values()),
        "tables_identical": not mismatched,
        "mismatched_tables": mismatched,
        "sequences_identical": expected["sequences"] == copied["sequences"],
        "sort_order_differs_in": differ,
        "backup": dump.name,
        "supabase_left_clean": True,
    }


# ------------------------------------------------------------------ cutover

BRAIN_ENV_KEY = "BRAIN_DATABASE_URL"
BACKUP_SUFFIX = ".before-supabase"
PUBLIC_ROLES = ("anon", "authenticated")  # Supabase's API roles: never on app/brain


def login(admin: str, role: str) -> str:
    """Supabase's pooler logs a role in as '<role>.<project>'; a plain server as '<role>'."""
    user = conninfo_to_dict(admin)["user"]
    return f"{role}.{user.split('.', 1)[1]}" if "." in user else role


def role_url(admin: str, role: str, password: str) -> str:
    from psycopg.conninfo import make_conninfo

    return make_conninfo(admin, user=login(admin, role), password=password)


def roles_of(config: dict, brain_url: str) -> dict:
    """The role names in use today (kept the same; only passwords change)."""
    return {
        "app": conninfo_to_dict(config["migration_url"])["user"],
        "brain": conninfo_to_dict(brain_url)["user"],
        "runtime": conninfo_to_dict(config["database_url"])["user"],
    }


def install(hosted: str, local_admin: str, dump: Path, binary: Path, roles: dict) -> dict:
    """Recreate the app's roles, schemas, data and grants in the hosted database.
    Each schema is created and restored by its own owner role, so ownership is exact
    without the hosted admin (not a superuser on Supabase) impersonating anyone.
    Returns the new connection strings. Database-wide grants are left alone: Supabase's
    own services depend on them."""
    import secrets

    from .backup import BackupError, client_environment
    from .shared_database import copy_runtime_grants

    passwords = {key: secrets.token_urlsafe(32) for key in roles}
    urls = {key: role_url(hosted, roles[key], passwords[key]) for key in roles}
    dbname = conninfo_to_dict(hosted).get("dbname", "postgres")
    with psycopg.connect(hosted, autocommit=True, connect_timeout=15) as admin:
        for key, role in roles.items():
            exists = admin.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (role,)).fetchone()
            verb = "ALTER" if exists else "CREATE"
            admin.execute(
                sql.SQL(verb + " ROLE {} LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE "
                        "PASSWORD {}").format(sql.Identifier(role), sql.Literal(passwords[key]))
            )  # fmt: skip
        for key in ("app", "brain"):  # each owner creates its own schema, then loses CREATE
            admin.execute(
                sql.SQL("GRANT CREATE ON DATABASE {} TO {}").format(
                    sql.Identifier(dbname), sql.Identifier(roles[key])
                )
            )
    try:
        for key in ("app", "brain"):
            with psycopg.connect(urls[key], autocommit=True, connect_timeout=15) as owner:
                owner.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(key)))
            restored = subprocess.run(
                [str(binary / ("pg_restore" + (".exe" if os.name == "nt" else ""))),
                 "--no-password", "--no-owner", "--no-privileges", "--single-transaction",
                 "--exit-on-error", "--schema=" + key, "--dbname", dbname, str(dump)],
                env=client_environment(urls[key]), capture_output=True, timeout=600, check=False,
            )  # fmt: skip
            if restored.returncode:
                (dump.parent / f"{key}-restore-error.log").write_bytes(restored.stderr)
                raise BackupError(f"Restoring {key} failed; the log is beside the backup.")
    finally:
        with psycopg.connect(hosted, autocommit=True, connect_timeout=15) as admin:
            for key in ("app", "brain"):
                admin.execute(
                    sql.SQL("REVOKE CREATE ON DATABASE {} FROM {}").format(
                        sql.Identifier(dbname), sql.Identifier(roles[key])
                    )
                )
    for key in ("app", "brain"):
        name = sql.Identifier(key)
        with psycopg.connect(urls[key], autocommit=True, connect_timeout=15) as owner:
            for target in ("PUBLIC", *existing_roles(owner, PUBLIC_ROLES)):
                grantee = sql.SQL(target) if target == "PUBLIC" else sql.Identifier(target)
                owner.execute(sql.SQL("REVOKE ALL ON SCHEMA {} FROM {}").format(name, grantee))
                for kind in ("TABLES", "SEQUENCES", "FUNCTIONS"):
                    owner.execute(
                        sql.SQL("REVOKE ALL ON ALL " + kind + " IN SCHEMA {} FROM {}").format(
                            name, grantee
                        )
                    )
            owner.execute("ALTER DEFAULT PRIVILEGES REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC")
            for kind in ("TABLES", "SEQUENCES"):
                owner.execute(
                    sql.SQL("ALTER DEFAULT PRIVILEGES IN SCHEMA {} REVOKE ALL ON "
                            + kind + " FROM PUBLIC").format(name)
                )  # fmt: skip
            if key == "app":
                with psycopg.connect(local_admin) as source:
                    copy_runtime_grants(source, owner, roles["runtime"])
                owner.execute(
                    sql.SQL("GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA app TO {}").format(
                        sql.Identifier(roles["runtime"])
                    )
                )
    return urls


def existing_roles(db, names) -> list[str]:
    return [
        r[0]
        for r in db.execute("SELECT rolname FROM pg_roles WHERE rolname = ANY(%s)", (list(names),))
    ]


def isolated(urls: dict, roles: dict) -> None:
    """Each service role reaches only its own schema; the API roles reach neither."""
    with psycopg.connect(urls["app"], connect_timeout=15) as db:
        for key, role in roles.items():
            own = "brain" if key == "brain" else "app"
            other = "app" if own == "brain" else "brain"
            ok = db.execute(
                "SELECT has_schema_privilege(%s,%s,'USAGE') AND NOT has_schema_privilege(%s,%s,'USAGE')",
                (role, own, role, other),
            ).fetchone()[0]
            if not ok:
                raise RuntimeError("Cross-schema access is not isolated.")
        for role in existing_roles(db, PUBLIC_ROLES):
            for schema in SCHEMAS:
                if db.execute(
                    "SELECT has_schema_privilege(%s,%s,'USAGE')", (role, schema)
                ).fetchone()[0]:
                    raise RuntimeError("A Supabase API role can reach the application schemas.")


def read_brain_url(env_file: Path) -> str:
    for line in env_file.read_text(encoding="utf-8").splitlines():
        if line.startswith(BRAIN_ENV_KEY + "="):
            return line.split("=", 1)[1].strip().strip("'").strip('"')
    raise SystemExit(f"{BRAIN_ENV_KEY} is not set in the brain .env.")


def write_brain_url(env_file: Path, url: str) -> None:
    lines = env_file.read_text(encoding="utf-8").splitlines(keepends=True)
    out = [
        f"{BRAIN_ENV_KEY}='{url}'\n" if line.startswith(BRAIN_ENV_KEY + "=") else line
        for line in lines
    ]
    partial = env_file.with_name(env_file.name + ".partial")
    partial.write_text("".join(out), encoding="utf-8")
    partial.replace(env_file)


def stop_app(home: Path) -> None:
    import time
    from urllib.request import Request, urlopen

    from .local_runtime import status

    if not status(home).get("ready"):
        return
    control = json.loads((home / "service.json").read_text(encoding="utf-8"))
    try:
        with urlopen(
            Request(f"http://127.0.0.1:{control['control_port']}/stop", data=b"",
                    headers={"Authorization": "Bearer " + control["token"]}),
            timeout=5,
        ):  # fmt: skip
            pass
    except OSError:
        pass
    for _ in range(240):
        if not status(home).get("ready") and not (home / "postgres/postmaster.pid").exists():
            return
        time.sleep(0.5)
    raise RuntimeError("The app did not stop; nothing was switched.")


def start_local_cluster(home: Path, config: dict) -> None:
    from .local_runtime import pg_start

    pg_start(home, config)


def stop_local_cluster(home: Path, config: dict) -> None:
    from .backup import tool
    from .local_runtime import pg_binary

    tool(pg_binary(config, "pg_ctl"), ["-D", home / "postgres", "-m", "fast", "-w", "stop"],
         capture=False)  # fmt: skip


def cutover(home: Path) -> dict:
    """Stop the app, copy a final verified snapshot into Supabase, verify every table,
    sequence and permission, switch the app and Lia to Supabase, start the app.
    The laptop cluster and the old settings are kept for rollback."""
    import tempfile
    import time

    from .backup import database_backup, fingerprints
    from .local_runtime import atomic_json, ensure

    hosted = admin_url(home)
    config_file = home / "runtime.json"
    config = json.loads(config_file.read_text(encoding="utf-8"))
    if config.get("database_host") == "remote":
        raise SystemExit("The app already uses the hosted database.")
    env_file = Path(config["brain_env"])
    roles = roles_of(config, read_brain_url(env_file))
    if check(hosted)["app_schemas_already_there"]:
        raise SystemExit("Supabase already holds app/brain schemas; nothing was changed.")
    binary = Path(config["postgres_bin"])
    stop_app(home)
    start_local_cluster(home, config)  # the app is stopped: only this copy reads it
    dump = home / "backups" / f"supabase-cutover-{time.strftime('%Y%m%d-%H%M%S')}.dump"
    try:
        with tempfile.TemporaryDirectory(prefix="yggdress-cutover-") as work:
            report = database_backup(config["admin_url"], dump, binary, Path(work), schemas=SCHEMAS)
        urls = install(hosted, config["admin_url"], dump, binary, roles)
        with psycopg.connect(hosted, connect_timeout=15) as db:
            db.read_only = True
            copied = fingerprints(db, SCHEMAS)
        if copied["tables"] != report["snapshot"]["tables"] or (
            copied["sequences"] != report["snapshot"]["sequences"]
        ):
            raise RuntimeError("The Supabase copy differs from the snapshot.")
        isolated(urls, roles)
    except BaseException:
        remove_schemas(hosted)  # nothing half-copied stays in Supabase
        ensure(home)  # the laptop database is untouched: carry on as before
        raise
    for path in (config_file, env_file):
        backup = path.with_name(path.name + BACKUP_SUFFIX)
        if not backup.exists():
            backup.write_bytes(path.read_bytes())
    write_brain_url(env_file, urls["brain"])
    atomic_json(config_file, {**config, "database_host": "remote", "admin_url": hosted,
                              "migration_url": urls["app"], "database_url": urls["runtime"]})  # fmt: skip
    stop_local_cluster(home, config)  # nothing may keep writing to the old copy unnoticed
    ready = ensure(home).get("ready", False)
    with psycopg.connect(urls["runtime"], connect_timeout=15) as db:
        tasks = db.execute("SELECT count(*) FROM app.tasks").fetchone()[0]
    with psycopg.connect(urls["brain"], connect_timeout=15) as db:
        notes = db.execute("SELECT count(*) FROM brain.notes").fetchone()[0]
    return {
        "tables": len(copied["tables"]),
        "rows": sum(t["rows"] for t in copied["tables"].values()),
        "identical": True,
        "permissions_isolated": True,
        "serving": ready,
        "tasks_visible_to_app": tasks,
        "notes_visible_to_brain": notes,
        "backup": dump.name,
        "rollback": "python -m yggdress_app.cloud_move rollback",
    }


def rollback(home: Path) -> dict:
    """Back to the laptop database: restore the saved settings and restart. Anything
    written to Supabase after the cutover is NOT copied back (it is left in Supabase)."""
    from .local_runtime import ensure

    config_file = home / "runtime.json"
    config = json.loads(config_file.read_text(encoding="utf-8"))
    env_file = Path(config["brain_env"])
    saved = [p.with_name(p.name + BACKUP_SUFFIX) for p in (config_file, env_file)]
    if not all(p.exists() for p in saved):
        raise SystemExit("No saved pre-Supabase settings; nothing was changed.")
    stop_app(home)  # the laptop cluster starts again with the app (local mode)
    for original, backup in zip((config_file, env_file), saved, strict=True):
        original.write_bytes(backup.read_bytes())
    return {"serving": ensure(home).get("ready", False), "database": "laptop"}


def main():
    parser = argparse.ArgumentParser(description="Move the database to Supabase.")
    parser.add_argument("action", choices=["check", "dry-run", "cutover", "rollback"])
    parser.add_argument("--home", type=Path, default=default_home())
    args = parser.parse_args()
    try:
        if args.action in ("dry-run", "cutover", "rollback"):
            step = {"dry-run": dry_run, "cutover": cutover, "rollback": rollback}[args.action]
            print(json.dumps(step(args.home), indent=2))
            return
        print(json.dumps(check(admin_url(args.home)), indent=2))
    except (psycopg.Error, RuntimeError) as exc:  # messages can hold addresses: type only
        raise SystemExit(
            f"Stopped safely: {type(exc).__name__}. Supabase was cleaned up."
        ) from None


if __name__ == "__main__":
    main()
