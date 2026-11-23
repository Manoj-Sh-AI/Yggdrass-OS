import hashlib
from pathlib import Path

import psycopg
from psycopg.rows import dict_row


class Database:
    def __init__(self, url: str):
        self.url = url

    def connect(self):
        return psycopg.connect(
            self.url,
            row_factory=dict_row,
            connect_timeout=5,
            options="-c search_path=app,pg_catalog -c statement_timeout=10000 -c timezone=UTC",
        )

    def migrate(self):
        """Explicit CLI/test operation, never an automatic application startup migration."""
        packaged = Path(__file__).resolve().parent / "migrations"
        folder = (
            packaged if packaged.is_dir() else Path(__file__).resolve().parents[2] / "migrations"
        )
        with self.connect() as db:
            db.execute("SELECT pg_advisory_xact_lock(719218401)")
            # Even IF NOT EXISTS requires database-wide CREATE. A shared-database
            # migrator owns the existing app schema without that broader grant.
            if (
                db.execute("SELECT to_regnamespace('app') AS namespace").fetchone()["namespace"]
                is None
            ):
                db.execute("CREATE SCHEMA app")
            db.execute(
                "CREATE TABLE IF NOT EXISTS app.schema_migrations (version text PRIMARY KEY, checksum text NOT NULL, applied_at timestamptz NOT NULL DEFAULT now())"
            )
            for path in sorted(folder.glob("*.sql")):
                text = path.read_text(encoding="utf-8")
                checksum = hashlib.sha256(text.encode()).hexdigest()
                row = db.execute(
                    "SELECT checksum FROM app.schema_migrations WHERE version=%s", (path.name,)
                ).fetchone()
                if row:
                    if row["checksum"] != checksum:
                        raise ValueError(
                            "An applied application migration changed; add a new migration."
                        )
                    continue
                db.execute(text)
                db.execute(
                    "INSERT INTO app.schema_migrations(version,checksum) VALUES (%s,%s)",
                    (path.name, checksum),
                )
