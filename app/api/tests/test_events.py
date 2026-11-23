"""Connected data step 3: one ordered, append-only change stream. No write can commit
without its event; readers use cursors that never skip. Synthetic data only."""

import psycopg
import pytest
from psycopg.rows import dict_row

from yggdress_app import events
from yggdress_app.database import Database


def admin(postgres):
    return Database(postgres["admin"]).connect()


def note_ref(db, slug):
    return db.execute(
        "INSERT INTO app.note_refs(external_id,observed_title,observed_revision) "
        "VALUES (%s,'Invented','r1') RETURNING id",
        (slug,),
    ).fetchone()["id"]


def test_every_app_table_is_captured_or_excluded_with_a_reason(setup, postgres):
    with admin(postgres) as db:
        tables = {r["tablename"] for r in db.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname='app'").fetchall()}  # fmt: skip
        captured = {r["t"] for r in db.execute(
            "SELECT c.relname AS t FROM pg_trigger g JOIN pg_class c ON c.oid=g.tgrelid "
            "JOIN pg_namespace n ON n.oid=c.relnamespace "
            "WHERE n.nspname='app' AND g.tgname='events_capture' AND NOT g.tgisinternal").fetchall()}  # fmt: skip
        excluded = {r["table_name"]: r["reason"] for r in db.execute(
            "SELECT * FROM app.event_exclusions").fetchall()}  # fmt: skip
    assert tables - captured - set(excluded) == set(), "a table is neither captured nor excluded"
    assert captured & set(excluded) == set()
    assert all(reason.strip() for reason in excluded.values())
    assert len(captured) >= 70  # nearly everything is captured


def test_the_event_is_written_in_the_same_transaction_and_rolls_back_with_it(setup, postgres):
    with psycopg.connect(postgres["admin"], row_factory=dict_row) as db:
        ref = note_ref(db, "invented-same-tx")
        mine = db.execute(
            "SELECT kind, subject_key, sensitivity FROM app.events "
            "WHERE tx = pg_current_xact_id() AND subject_kind = 'note_refs'"
        ).fetchall()
        assert mine == [
            {"kind": "note_refs.insert", "subject_key": str(ref), "sensitivity": "unknown"}
        ]
        db.rollback()
        assert db.execute("SELECT count(*) AS n FROM app.events").fetchone()["n"] == 0


def test_no_write_can_commit_without_its_event(setup, postgres):
    with admin(postgres) as db:  # make the event impossible to write
        db.execute("ALTER TABLE app.events ADD CONSTRAINT refuse_all CHECK (false) NOT VALID")
    try:
        with admin(postgres) as db, pytest.raises(psycopg.errors.CheckViolation):
            note_ref(db, "invented-no-event")
        with admin(postgres) as db:
            assert (
                db.execute(
                    "SELECT count(*) AS n FROM app.note_refs WHERE external_id='invented-no-event'"
                ).fetchone()["n"]
                == 0
            )
    finally:
        with admin(postgres) as db:
            db.execute("ALTER TABLE app.events DROP CONSTRAINT refuse_all")


def test_events_are_append_only_even_for_the_owner(setup, postgres):
    with admin(postgres) as db:
        note_ref(db, "invented-append")
    for statement in ("UPDATE app.events SET actor='someone'", "DELETE FROM app.events"):
        with admin(postgres) as db, pytest.raises(psycopg.errors.InsufficientPrivilege):
            db.execute(statement)


def test_the_app_role_writes_events_only_through_its_writes_and_reads_the_view(setup, postgres):
    with Database(postgres["runtime"]).connect() as db:
        note_ref(db, "invented-runtime")
        row = db.execute("SELECT actor, kind FROM api.events").fetchone()
        assert row["kind"] == "note_refs.insert" and row["actor"] == postgres["role"]
    with (
        Database(postgres["runtime"]).connect() as db,
        pytest.raises(psycopg.errors.InsufficientPrivilege),
    ):
        db.execute(
            "INSERT INTO app.events(kind,subject_kind,actor) VALUES ('tasks.insert','tasks','forged')"
        )


def test_the_actor_can_be_named_for_the_transaction(setup, postgres):
    with admin(postgres) as db:
        db.execute("SELECT set_config('yggdras.actor', 'lia', true)")
        note_ref(db, "invented-actor")
    with admin(postgres) as db:
        assert db.execute("SELECT actor FROM app.events").fetchone()["actor"] == "lia"


def test_cursors_are_independent_and_never_skip_an_out_of_order_commit(setup, postgres):
    reader = Database(postgres["runtime"])
    first = psycopg.connect(postgres["admin"], row_factory=dict_row)
    second = psycopg.connect(postgres["admin"], row_factory=dict_row)
    try:
        early = note_ref(first, "invented-early")  # transaction A writes first, stays open
        late = note_ref(second, "invented-late")  # transaction B writes later
        second.commit()  # ... and commits first
        with reader.connect() as db:
            assert events.read(db, "test-a") == []  # A may still commit: wait, don't skip it
        first.commit()
        with reader.connect() as db:
            got = [
                e["subject_key"]
                for e in events.read(db, "test-a")
                if e["subject_kind"] == "note_refs"
            ]
        assert got == [str(early), str(late)]  # both, in order, A's first
        with reader.connect() as db:
            assert events.read(db, "test-a") == []  # nothing read twice
            assert [
                e["subject_key"]
                for e in events.read(db, "test-b")
                if e["subject_kind"] == "note_refs"
            ] == got  # own cursor
    finally:
        first.close()
        second.close()
