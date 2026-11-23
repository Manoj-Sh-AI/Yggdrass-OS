"""The connection to the brain database. The URL comes from BRAIN_DATABASE_URL (the .env file)
and is never printed, logged or put in an error message: the repo is public."""

from __future__ import annotations

import os

SCHEMA = "brain"
URL_VAR = "BRAIN_DATABASE_URL"


class DatabaseError(RuntimeError):
    """A connection problem, told without the connection string."""


def database_url() -> str:
    from yggdras import config

    config.load_env_file()
    url = os.environ.get(URL_VAR, "").strip()
    if not url:
        raise DatabaseError(f"{URL_VAR} is not set (put it in the .env file)")
    return url


def connect(url: str | None = None):
    """A connection in UTC. Every query names the `brain` schema itself."""
    import psycopg

    try:
        conn = psycopg.connect(url or database_url(), autocommit=False)
    except psycopg.Error as exc:
        # psycopg's message can echo the host and user; the class name is enough.
        raise DatabaseError(
            f"could not connect to the brain database ({exc.__class__.__name__}); check {URL_VAR}"
        ) from None
    with conn.cursor() as cur:
        cur.execute("SET TIME ZONE 'UTC'")
    conn.commit()
    return conn
