"""Bring the hosted database up to the migrations this code ships (Railway, 2026-11-23).

A hosted backend never migrates at start-up (local_runtime.serve only checks the schemas
exist), so a deploy whose code needs new tables must be preceded by this, run from the
laptop. The admin connection is read only from the private file cloud_move uses
(%LOCALAPPDATA%/Yggdras/railway-admin.url); no connection string is ever printed.

    python -m yggdress_app.migrate_hosted plan     # read-only: what is missing, which roles
    python -m yggdress_app.migrate_hosted apply    # backup, migrate, grant, verify
    python -m yggdress_app.migrate_hosted counts   # read-only: backfill counts vs sources

`apply`, in order, stopping at the first problem:
  1. refuse if a pending migration is destructive (expand-contract, AGENTS.md)
  2. a full backup of the app schemas, verified by restoring it into a scratch cluster
  3. the pending migrations, run as the app schema's OWNER (SET ROLE), so new tables
     belong to the same role as the existing ones
  4. the runtime role's grants (runtime_grants.py), so the app can use the new tables
  5. no existing table lost a row
Every step is safe to run again: applied migrations are skipped, grants are idempotent.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import tempfile
import time
from pathlib import Path

import psycopg
from psycopg import sql

from .database import Database

DESTRUCTIVE = re.compile(
    r"\bDROP\s+(TABLE|COLUMN|SCHEMA|TYPE|VIEW)\b|\bRENAME\b|\bSET\s+NOT\s+NULL\b|\bTRUNCATE\b",
    re.IGNORECASE,
)


def migration_files() -> list[Path]:
    return sorted(Database.migration_folder().glob("*.sql"))


def without_comments(text: str) -> str:
    return re.sub(r"--[^\n]*", " ", re.sub(r"/\*.*?\*/", " ", text, flags=re.DOTALL))


def pending(db, files: list[Path]) -> list[Path]:
    """Migrations not yet applied. An applied one whose file changed stops everything."""
    exists = db.execute("SELECT to_regclass('app.schema_migrations')").fetchone()[0]
    applied = (
        dict(db.execute("SELECT version, checksum FROM app.schema_migrations").fetchall())
        if exists
        else {}
    )
    missing = []
    for path in files:
        checksum = hashlib.sha256(path.read_text(encoding="utf-8").encode()).hexdigest()
        if path.name not in applied:
            missing.append(path)
        elif applied[path.name] != checksum:
            raise SystemExit(f"Applied migration {path.name} differs from this code; stopping.")
    return missing


def roles(db, runtime: str | None = None) -> dict:
    """The app schema's owner, and the one login role the app runs as."""
    owner = db.execute(
        "SELECT pg_get_userbyid(nspowner) FROM pg_namespace WHERE nspname='app'"
    ).fetchone()
    if not owner:
        raise SystemExit("This database has no app schema; it is not the application's database.")
    owner = owner[0]
    if runtime:
        return {"owner": owner, "runtime": runtime}
    candidates = [
        r[0]
        for r in db.execute(
            """SELECT rolname FROM pg_roles
               WHERE rolcanlogin AND NOT rolsuper AND rolname NOT IN (%s, current_user)
                 AND rolname NOT LIKE 'pg\\_%%'
                 AND has_schema_privilege(oid, 'app', 'USAGE')
                 AND has_table_privilege(oid, 'app.login_guard', 'SELECT')""",
            (owner,),
        ).fetchall()
    ]
    if len(candidates) != 1:
        raise SystemExit(
            f"Found {len(candidates)} candidate app roles; name it with --runtime-role."
        )
    return {"owner": owner, "runtime": candidates[0]}


def row_counts(db) -> dict[str, int]:
    tables = db.execute(
        "SELECT format('%I.%I', schemaname, tablename) FROM pg_tables "
        "WHERE schemaname IN ('app','brain') ORDER BY 1"
    ).fetchall()
    return {t[0]: db.execute(f"SELECT count(*) FROM {t[0]}").fetchone()[0] for t in tables}


def plan(url: str, runtime: str | None = None) -> dict:
    with psycopg.connect(url, connect_timeout=15) as db:
        db.read_only = True
        missing = pending(db, migration_files())
        found = roles(db, runtime)
        server = int(db.execute("SHOW server_version_num").fetchone()[0])
    return {
        "server_version_num": server,
        "owner_role": found["owner"],
        "runtime_role": found["runtime"],
        "pending": [p.name for p in missing],
        "destructive": [p.name for p in missing if DESTRUCTIVE.search(without_comments(p.read_text(encoding="utf-8")))],
    }  # fmt: skip


def grant(url: str, owner: str, runtime: str) -> None:
    from .runtime_grants import grant_runtime

    with psycopg.connect(url, connect_timeout=15) as db:
        grant_runtime(db, runtime)
        for statement in (
            "GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA app TO {}",
            "GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA app TO {}",
        ):
            db.execute(sql.SQL(statement).format(sql.Identifier(runtime)))


def ensure_api_schema(url: str, owner: str) -> None:
    """The api schema (043), owned by the app owner. The owner has no database-wide CREATE
    on a hosted database, so the admin connection creates it, as cloud_move did for app."""
    with psycopg.connect(url, autocommit=True, connect_timeout=15) as db:
        db.execute(
            sql.SQL("CREATE SCHEMA IF NOT EXISTS api AUTHORIZATION {}").format(
                sql.Identifier(owner)
            )
        )


def backfill_sensitivity(url: str, notes_table: str = "brain.notes") -> dict:
    """Copy each referenced note's sensitivity from the brain (admin can read it; the app
    owner cannot). The brain marks a sensitive note 'high' (mobile_policy.sensitive).
    Only rows still 'unknown' change, so a rerun is a no-op; a ref whose note is gone
    stays 'unknown', which every view treats as restricted."""
    schema, _, table = notes_table.partition(".")
    with psycopg.connect(url, connect_timeout=15) as db:
        has_column = db.execute(
            "SELECT 1 FROM information_schema.columns WHERE table_schema='app' "
            "AND table_name='note_refs' AND column_name='sensitivity'"
        ).fetchone()
        if not has_column:
            return {"skipped": "note_refs has no sensitivity column yet"}
        if db.execute("SELECT to_regclass(%s)", (notes_table,)).fetchone()[0] is None:
            return {"skipped": f"{notes_table} not found"}
        changed = db.execute(
            sql.SQL(
                "UPDATE app.note_refs r SET sensitivity = CASE WHEN "
                "lower(coalesce(n.sensitivity,''))='high' THEN 'restricted' ELSE 'normal' END "
                "FROM {}.{} n WHERE n.slug = r.external_id AND r.sensitivity = 'unknown' "
                "RETURNING r.sensitivity"
            ).format(sql.Identifier(schema), sql.Identifier(table))
        ).fetchall()
        totals = dict(
            db.execute("SELECT sensitivity, count(*) FROM app.note_refs GROUP BY 1").fetchall()
        )
    return {
        "set_now": {k: sum(1 for (v,) in changed if v == k) for k in ("normal", "restricted")},
        "totals": {k: totals.get(k, 0) for k in ("normal", "restricted", "unknown")},
    }


LINK_TABLES = ("task_note_links", "event_note_links", "availability_note_links",
               "date_item_note_links")  # fmt: skip
JUDGEMENT_SOURCES = {
    "yggdras_feedback": "SELECT count(*) FROM app.yggdras_feedback",
    "workflow_reviews": "SELECT count(*) FROM app.workflow_reviews WHERE state IN ('accepted','dismissed')",
    "call_reviews": "SELECT count(*) FROM app.call_reviews WHERE state IN ('accepted','dismissed')",
    "agent_proposals": "SELECT count(*) FROM app.agent_proposals WHERE state IN ('accepted','dismissed')",
    "conductor_runs": "SELECT count(*) FROM app.conductor_runs r, "
    "jsonb_array_elements(coalesce(r.state->'tools','[]'::jsonb)) t "
    "WHERE t->>'state'='approval-responded' AND t->>'decided_by'='user' AND t->'approval' IS NOT NULL",
}  # fmt: skip


def counts(url: str) -> dict:
    """Read-only: the numbers that show each connected-data backfill matches its sources.
    Only counts and table names; no row content."""

    def exists(db, name):
        return db.execute("SELECT to_regclass(%s)", (name,)).fetchone()[0] is not None

    with psycopg.connect(url, connect_timeout=15) as db:
        db.read_only = True
        out: dict = {"links": None, "note_refs_by_sensitivity": None, "events": None,
                     "judgements": None}  # fmt: skip
        if exists(db, "app.links"):
            old = {
                t: db.execute(f"SELECT count(*) FROM app.{t}").fetchone()[0] for t in LINK_TABLES
            }
            mirrored = dict(db.execute(
                "SELECT legacy_table, count(*) FROM app.links WHERE status='active' "
                "AND legacy_table IS NOT NULL GROUP BY 1").fetchall())  # fmt: skip
            out["links"] = {t: {"old": old[t], "links": mirrored.get(t, 0)} for t in LINK_TABLES}
        has_sensitivity = db.execute(
            "SELECT 1 FROM information_schema.columns WHERE table_schema='app' "
            "AND table_name='note_refs' AND column_name='sensitivity'"
        ).fetchone()
        if has_sensitivity:
            out["note_refs_by_sensitivity"] = dict(db.execute(
                "SELECT sensitivity, count(*) FROM app.note_refs GROUP BY 1 ORDER BY 1").fetchall())  # fmt: skip
        if exists(db, "app.events"):
            out["events"] = db.execute("SELECT count(*) FROM app.events").fetchone()[0]
        if exists(db, "app.judgements"):
            copied = dict(db.execute(
                "SELECT source_table, count(*) FROM app.judgements GROUP BY 1").fetchall())  # fmt: skip
            out["judgements"] = {
                t: {"eligible": db.execute(q).fetchone()[0], "judgements": copied.get(t, 0)}
                for t, q in JUDGEMENT_SOURCES.items()
            }
    return out


def pg_binaries() -> Path:
    found = shutil.which("pg_dump")
    folder = Path(found).parent if found else Path("C:/Program Files/PostgreSQL/18/bin")
    if not (folder / ("pg_dump.exe" if (folder / "pg_dump.exe").exists() else "pg_dump")).exists():
        raise SystemExit("PostgreSQL client tools (pg_dump) were not found.")
    return folder


def apply(url: str, backups: Path, runtime: str | None = None, binaries: Path | None = None,
          allow_destructive: bool = False) -> dict:  # fmt: skip
    from .backup import database_backup
    from .local_runtime import SCHEMAS

    before_plan = plan(url, runtime)
    if before_plan["destructive"] and not allow_destructive:
        raise SystemExit("Destructive migrations pending: " + ", ".join(before_plan["destructive"]))
    result = {
        "applied": [],
        "backup": None,
        **{k: before_plan[k] for k in ("owner_role", "runtime_role")},
    }
    if before_plan["pending"]:
        backups.mkdir(parents=True, exist_ok=True)
        target = backups / f"pre-migrate-{time.strftime('%Y%m%d-%H%M%S')}.dump"
        with tempfile.TemporaryDirectory(prefix="yggdras-migrate-") as workspace:
            database_backup(
                url, target, binaries or pg_binaries(), Path(workspace), schemas=SCHEMAS
            )
        result["backup"] = target.name
        with psycopg.connect(url, connect_timeout=15) as db:
            before = row_counts(db)
        ensure_api_schema(url, before_plan["owner_role"])
        Database(url).migrate(role=before_plan["owner_role"])
        with psycopg.connect(url, connect_timeout=15) as db:
            after = row_counts(db)
        lost = [t for t, n in before.items() if after.get(t, 0) < n]
        if lost:
            raise SystemExit(f"Rows were lost in {', '.join(lost)}; restore {target.name}.")
        result["applied"] = before_plan["pending"]
    grant(url, before_plan["owner_role"], before_plan["runtime_role"])  # also repairs a rerun
    result["sensitivity_backfill"] = backfill_sensitivity(url)
    result["still_pending"] = plan(url, before_plan["runtime_role"])["pending"]
    return result  # fmt: skip


def main(argv=None) -> int:
    from .cloud_move import TARGETS, admin_url
    from .local_runtime import default_home

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("action", choices=["plan", "apply", "counts"])
    parser.add_argument("--target", choices=sorted(TARGETS), default="railway")
    parser.add_argument("--home", type=Path, default=default_home())
    parser.add_argument("--runtime-role")
    parser.add_argument("--allow-destructive", action="store_true")
    args = parser.parse_args(argv)
    url = admin_url(args.home, args.target)
    try:
        if args.action == "plan":
            out = plan(url, args.runtime_role)
        elif args.action == "counts":
            out = counts(url)
        else:
            out = apply(url, args.home / "backups", args.runtime_role,
                        allow_destructive=args.allow_destructive)  # fmt: skip
    except SystemExit:
        raise
    except Exception as error:  # noqa: BLE001 -- a DSN must never reach the console
        print(f"Stopped safely ({type(error).__name__}). Nothing after the failing step ran; "
              "any backup taken is in the backups folder.")  # fmt: skip
        return 1
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
