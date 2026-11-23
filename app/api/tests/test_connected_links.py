"""Connected data step 1 (planning/connected-data-proposal.md): app.links mirrors the four
old link tables exactly, typed with the fixed verbs, sourced, approved; backfill is a copy
and safe to run twice. Synthetic data only."""

from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from test_connections import event, link, task, wire

from yggdress_app.database import Database

MIGRATION = Path(__file__).parents[1] / "migrations" / "042_links.sql"
OLD = ("task_note_links", "event_note_links", "availability_note_links", "date_item_note_links")
VERBS = {"about", "source_of", "result_of", "blocks", "part_of", "evidence_for",
         "scheduled_for", "follows_up"}  # fmt: skip


def old_view(db) -> set[tuple]:
    """Every old row, as the typed link it means."""
    rows = set()
    for table in OLD:
        for r in db.execute(
            f"SELECT o.id, l.*, o.source_revision FROM app.{table} o, "
            f"LATERAL app.legacy_link('{table}', to_jsonb(o)) l"
        ).fetchall():
            rows.add((table, str(r["id"]), r["from_kind"], str(r["from_id"]), r["verb"],
                      r["to_kind"], str(r["to_id"]), r["source_revision"]))  # fmt: skip
    return rows


def new_view(db) -> set[tuple]:
    """Every active link in app.links that mirrors an old row."""
    return {
        (
            r["legacy_table"],
            str(r["legacy_id"]),
            r["from_kind"],
            str(r["from_id"]),
            r["verb"],
            r["to_kind"],
            str(r["to_id"]),
            r["source_revision"],
        )
        for r in db.execute(
            "SELECT * FROM app.links WHERE status='active' AND legacy_table IS NOT NULL"
        ).fetchall()
    }


def admin(postgres):
    return Database(postgres["admin"]).connect()


def test_the_verb_list_is_exactly_the_decided_one(setup, postgres):
    with admin(postgres) as db:
        rows = db.execute("SELECT verb, inverse FROM app.link_verbs").fetchall()
    assert {r["verb"] for r in rows} == VERBS
    assert len({r["inverse"] for r in rows}) == len(VERBS)  # every inverse distinct


def test_links_made_and_removed_through_the_api_are_mirrored_and_agree(signed_in, postgres):
    client, app, _ = signed_in
    wire(app)
    work, meeting = task(client), event(client)
    first, _ = link(client, "task.link_note", work, note_slug="sample", relation="source")
    work["version"] = first["version"]
    link(client, "event.link_note", meeting, note_slug="sample", relation="context")
    with admin(postgres) as db:
        assert old_view(db) == new_view(db) and len(new_view(db)) == 2
        rows = {r["verb"]: r for r in db.execute("SELECT * FROM app.links").fetchall()}
        # source: the note is the source OF the task; context: the event is ABOUT the note
        assert (rows["source_of"]["from_kind"], rows["source_of"]["to_kind"]) == ("note", "task")
        assert (rows["about"]["from_kind"], rows["about"]["to_kind"]) == ("event", "note")
        assert all(r["origin"] == "import" and r["approved"] for r in rows.values())
    link(client, "task.unlink_note", work, note_slug="sample", relation="source")
    with admin(postgres) as db:
        assert old_view(db) == new_view(db) and len(new_view(db)) == 1
        retired = db.execute(
            "SELECT status, retired_at FROM app.links WHERE verb='source_of'"
        ).fetchone()
        assert (
            retired["status"] == "retired" and retired["retired_at"] is not None
        )  # kept, not deleted


def test_every_old_table_insert_update_delete_is_mirrored(setup, postgres):
    with admin(postgres) as db:
        note = db.execute(
            "INSERT INTO app.note_refs(external_id,observed_title,observed_revision) "
            "VALUES ('invented-note','Invented note','r1') RETURNING id"
        ).fetchone()["id"]
        day = db.execute(
            "INSERT INTO app.calendar_date_items(title,kind,starts_on,ends_before) "
            "VALUES ('Invented day','event','2030-01-02','2030-01-03') RETURNING id"
        ).fetchone()["id"]
        window = db.execute(
            "INSERT INTO app.availability_windows(title,starts_at,ends_at,timezone) "
            "VALUES ('Invented window','2030-01-02T10:00Z','2030-01-02T12:00Z','UTC') RETURNING id"
        ).fetchone()["id"]
        db.execute(
            "INSERT INTO app.date_item_note_links(date_item_id,note_ref_id,kind) VALUES (%s,%s,'result')",
            (day, note),
        )
        db.execute(
            "INSERT INTO app.availability_note_links(availability_id,note_ref_id,kind) VALUES (%s,%s,'context')",
            (window, note),
        )
        assert old_view(db) == new_view(db) and len(new_view(db)) == 2
        db.execute("UPDATE app.date_item_note_links SET source_revision='r2'")
        assert old_view(db) == new_view(db)
        db.execute("DELETE FROM app.availability_note_links")
        assert old_view(db) == new_view(db) and len(new_view(db)) == 1


def test_backfill_copies_every_old_row_and_a_second_run_changes_nothing(setup, postgres):
    with admin(postgres) as db:
        note = db.execute(
            "INSERT INTO app.note_refs(external_id,observed_title,observed_revision) "
            "VALUES ('invented-backfill','Invented','r1') RETURNING id"
        ).fetchone()["id"]
        day = db.execute(
            "INSERT INTO app.calendar_date_items(title,kind,starts_on,ends_before) "
            "VALUES ('Invented','review','2030-02-01','2030-02-02') RETURNING id"
        ).fetchone()["id"]
        # rows that existed before 042: written with the mirror switched off
        db.execute("ALTER TABLE app.date_item_note_links DISABLE TRIGGER links_mirror")
        for kind in ("source", "context", "result"):
            db.execute(
                "INSERT INTO app.date_item_note_links(date_item_id,note_ref_id,kind) VALUES (%s,%s,%s)",
                (day, note, kind),
            )
        db.execute("ALTER TABLE app.date_item_note_links ENABLE TRIGGER links_mirror")
        assert new_view(db) == set()
        sql_text = MIGRATION.read_text(encoding="utf-8")
        db.execute(sql_text)
        first = new_view(db)
        db.execute(sql_text)  # idempotent: the whole migration again
        counts = {t: db.execute(f"SELECT count(*) AS n FROM app.{t}").fetchone()["n"] for t in OLD}
        assert new_view(db) == first == old_view(db)
        assert len(first) == sum(counts.values()) == 3
        assert db.execute("SELECT count(*) AS n FROM app.link_verbs").fetchone()["n"] == len(VERBS)


def test_a_link_end_must_exist(setup, postgres):
    with admin(postgres) as db, pytest.raises(psycopg.errors.ForeignKeyViolation):
        db.execute(
            "INSERT INTO app.links(from_kind,from_id,verb,to_kind,to_id,origin) "
            "VALUES ('task',%s,'about','note',%s,'manual')",
            (uuid4(), uuid4()),
        )


def test_the_app_role_reads_links_but_cannot_write_them_directly(setup, postgres):
    with Database(postgres["runtime"]).connect() as db:
        assert db.execute("SELECT count(*) AS n FROM app.links").fetchone()["n"] == 0
    with (
        Database(postgres["runtime"]).connect() as db,
        pytest.raises(psycopg.errors.InsufficientPrivilege),
    ):
        db.execute(
            "INSERT INTO app.links(from_kind,from_id,verb,to_kind,to_id,origin) "
            "VALUES ('task',%s,'about','note',%s,'manual')",
            (uuid4(), uuid4()),
        )
