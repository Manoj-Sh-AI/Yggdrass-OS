"""Reading the change stream app.events (migration 044) by cursor.

Every write to an app table appends an event in its own transaction. A reader keeps a
named cursor and reads forward. Order and completeness: a plain `seq > last` cursor would
skip an event whose transaction commits after a later one, so the reader only takes
events from transactions that have certainly finished (tx below the oldest transaction
still running) and orders them by (tx, seq). Anything not yet returned then has a larger
(tx, seq) than the cursor, so nothing is skipped and nothing is read twice.

Call `read` inside the caller's transaction: the cursor moves only if that commits.
"""

from __future__ import annotations

CONSUMER_PATTERN = r"^[a-z0-9_.:-]{1,80}$"


def read(db, consumer: str, limit: int = 100) -> list[dict]:
    """The next events for `consumer` (at most `limit`), advancing its cursor."""
    if not 1 <= limit <= 1000:
        raise ValueError("limit must be between 1 and 1000")
    db.execute(
        "INSERT INTO app.event_cursors(consumer) VALUES (%s) ON CONFLICT (consumer) DO NOTHING",
        (consumer,),
    )
    position = db.execute(
        "SELECT last_tx, last_seq FROM app.event_cursors WHERE consumer=%s FOR UPDATE",
        (consumer,),
    ).fetchone()
    rows = db.execute(
        "SELECT seq, tx, at, kind, subject_kind, subject_key, actor, sensitivity FROM app.events "
        "WHERE (tx, seq) > (%s::xid8, %s) AND tx < pg_snapshot_xmin(pg_current_snapshot()) "
        "ORDER BY tx, seq LIMIT %s",
        (str(position["last_tx"]), position["last_seq"], limit),
    ).fetchall()
    if rows:
        db.execute(
            "UPDATE app.event_cursors SET last_tx=%s::xid8, last_seq=%s, updated_at=now() "
            "WHERE consumer=%s",
            (str(rows[-1]["tx"]), rows[-1]["seq"], consumer),
        )
    return [dict(r) for r in rows]
