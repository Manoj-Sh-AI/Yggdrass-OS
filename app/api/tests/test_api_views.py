"""Connected data step 2: note_refs carries sensitivity (never null), and the api.* views
apply the rule once. A sensitive or not-yet-checked note never leaves through any view,
a link, a search or a join; agent-facing code reads only the views. Synthetic data only."""

import json
import re
from pathlib import Path

import psycopg
import pytest
from test_connections import link, task, wire

from yggdress_app import migrate_hosted
from yggdress_app.call_briefs import linked_slugs
from yggdress_app.database import Database

SECRETS = ("zebra", "okapi")  # words only the restricted and the unknown note carry
SOURCE = Path(__file__).parents[1] / "src" / "yggdress_app"


def admin(postgres):
    return Database(postgres["admin"]).connect()


def runtime(postgres):
    return Database(postgres["runtime"]).connect()


@pytest.fixture
def planted(setup, postgres):
    """A normal, a restricted and an unknown note, each linked to a task and an event."""
    with admin(postgres) as db:
        refs = {}
        for slug, title, sensitivity, revision in (
            ("invented-public", "Invented public plan", "normal", "rev-public"),
            ("invented-zebra-secret", "Invented zebra diagnosis", "restricted", "rev-zebra"),
            ("invented-okapi-pending", "Invented okapi letter", "unknown", "rev-okapi"),
        ):
            refs[sensitivity] = db.execute(
                "INSERT INTO app.note_refs(external_id,observed_title,observed_revision,sensitivity) "
                "VALUES (%s,%s,%s,%s) RETURNING id",
                (slug, title, revision, sensitivity),
            ).fetchone()["id"]
        work = db.execute(
            "INSERT INTO app.tasks(id,title,objective,area,due_date) VALUES "
            "(gen_random_uuid(),'Invented errand','Invented','work','2030-01-02') RETURNING id"
        ).fetchone()["id"]
        meeting = db.execute(
            "INSERT INTO app.calendar_events(id,title,starts_at,ends_at,timezone) VALUES "
            "(gen_random_uuid(),'Invented meeting','2030-01-02T10:00Z','2030-01-02T11:00Z','UTC') RETURNING id"
        ).fetchone()["id"]
        for ref, kind in ((refs["normal"], "context"), (refs["restricted"], "source"),
                          (refs["unknown"], "result")):  # fmt: skip
            db.execute(
                "INSERT INTO app.task_note_links(task_id,note_ref_id,kind) VALUES (%s,%s,%s)",
                (work, ref, kind),
            )
            db.execute(
                "INSERT INTO app.event_note_links(event_id,note_ref_id,kind) VALUES (%s,%s,%s)",
                (meeting, ref, kind),
            )
    return {"refs": refs, "task": work, "event": meeting}


def leaks(rows) -> list[str]:
    text = json.dumps([dict(r) for r in rows], default=str).lower()
    return [word for word in SECRETS if word in text]


def test_sensitivity_is_never_null_and_only_three_values(setup, postgres):
    with admin(postgres) as db:
        row = db.execute(
            "INSERT INTO app.note_refs(external_id,observed_title,observed_revision) "
            "VALUES ('invented-default','Invented','r1') RETURNING sensitivity"
        ).fetchone()
        assert row["sensitivity"] == "unknown"  # unchecked starts hidden
    with admin(postgres) as db, pytest.raises(psycopg.errors.NotNullViolation):
        db.execute("UPDATE app.note_refs SET sensitivity=NULL")
    with admin(postgres) as db, pytest.raises(psycopg.errors.CheckViolation):
        db.execute("UPDATE app.note_refs SET sensitivity='secret'")


def test_every_api_view_link_search_and_join_keeps_sensitive_notes_in(planted, postgres):
    with runtime(postgres) as db:
        views = [r["viewname"] for r in db.execute(
            "SELECT viewname FROM pg_views WHERE schemaname='api' ORDER BY 1").fetchall()]  # fmt: skip
        assert set(views) >= {"note_refs", "links", "note_links", "note_search"}
        for view in views:  # every view, so a future one cannot skip the rule
            rows = db.execute(f"SELECT * FROM api.{view}").fetchall()
            if view in ("note_refs", "links", "note_links", "note_search"):
                assert rows, view  # the planted notes are really there to leak
            assert leaks(rows) == [], view
        # the restricted and unknown notes exist (by id) but say nothing about themselves
        masked = db.execute(
            "SELECT title, slug, revision FROM api.note_refs WHERE sensitivity<>'normal'"
        ).fetchall()
        assert len(masked) == 2 and all(
            r["title"] == "Sensitive note" and r["slug"] is None and r["revision"] is None
            for r in masked
        )
        # search: a hidden note cannot be found by any word of its title or slug
        for word in (*SECRETS, "diagnosis", "letter", "invented"):
            found = db.execute(
                "SELECT * FROM api.note_search WHERE title ILIKE %s OR slug ILIKE %s",
                (f"%{word}%", f"%{word}%"),
            ).fetchall()
            assert leaks(found) == [] and all(r["slug"] == "invented-public" for r in found)
        # links and joins across the views
        joined = db.execute(
            "SELECT l.*, n.*, nl.* FROM api.links l "
            "JOIN api.note_refs n ON n.id IN (l.from_id, l.to_id) "
            "JOIN api.note_links nl ON nl.link_id = l.id"
        ).fetchall()
        assert len(joined) == 6 and leaks(joined) == []
        labels = {
            r["from_label"] for r in db.execute("SELECT from_label FROM api.links").fetchall()
        }
        assert "Sensitive note" in labels


def test_the_call_briefing_only_ever_names_normal_notes(planted, postgres):
    with runtime(postgres) as db:
        item = {"kind": "event", "id": planted["event"], "task_id": planted["task"]}
        assert linked_slugs(db, item) == ["invented-public"]


def test_observing_a_note_records_its_sensitivity(signed_in, postgres):
    client, app, _ = signed_in
    wire(app)
    link(client, "task.link_note", task(client), note_slug="sample", relation="context")
    with runtime(postgres) as db:
        row = db.execute("SELECT * FROM api.note_refs").fetchone()
    assert row["sensitivity"] == "normal" and row["slug"] == "sample"


def test_backfill_copies_sensitivity_from_the_brain_and_a_rerun_changes_nothing(setup, postgres):
    with admin(postgres) as db:
        db.execute("CREATE SCHEMA IF NOT EXISTS brain_fixture")
        db.execute("DROP TABLE IF EXISTS brain_fixture.notes")
        db.execute("CREATE TABLE brain_fixture.notes(slug text PRIMARY KEY, sensitivity text)")
        db.execute(
            "INSERT INTO brain_fixture.notes VALUES ('invented-high','high'),('invented-plain',NULL)"
        )
        for slug in ("invented-high", "invented-plain", "invented-gone"):
            db.execute(
                "INSERT INTO app.note_refs(external_id,observed_title,observed_revision) "
                "VALUES (%s,'Invented','r1')",
                (slug,),
            )
    try:
        first = migrate_hosted.backfill_sensitivity(postgres["admin"], "brain_fixture.notes")
        assert first["set_now"] == {"normal": 1, "restricted": 1}
        assert first["totals"] == {
            "normal": 1,
            "restricted": 1,
            "unknown": 1,
        }  # gone note stays hidden
        again = migrate_hosted.backfill_sensitivity(postgres["admin"], "brain_fixture.notes")
        assert again["set_now"] == {"normal": 0, "restricted": 0}
    finally:
        with admin(postgres) as db:
            db.execute("DROP SCHEMA brain_fixture CASCADE")


AGENT_MODULES = [
    "call_briefs.py", "agent_lia.py", "agent_specialists.py", "agent_tools.py",
    "agent_orchestrator.py", "subagents.py", "routine_voice_agent.py",
    "temporal_agent_activities.py", "tool_gate.py", "chat_catalog.py", "connector_mcp.py",
    *[f"conductor/{p.name}" for p in (SOURCE / "conductor").glob("*.py")],
]  # fmt: skip
NOTE_TABLES = re.compile(r"\bapp\.(note_refs|links|[a-z_]*note_links|operational_edges)\b")


def test_agent_and_mcp_code_reads_note_data_only_through_the_api_views():
    offenders = [
        m for m in AGENT_MODULES if NOTE_TABLES.search((SOURCE / m).read_text(encoding="utf-8"))
    ]
    assert offenders == []
