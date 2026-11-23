"""Connected data step 4: every approve and reject in one table, copied from where they are
recorded today (with the source table on each row), and written there from now on in the
same transaction. Synthetic data only."""

import json
import uuid
from pathlib import Path

from test_conductor_safety import run_with_approval, until  # noqa: F401 - fixture reuse

from yggdress_app.database import Database

MIGRATION = Path(__file__).parents[1] / "migrations" / "045_judgements.sql"


def admin(postgres):
    return Database(postgres["admin"]).connect()


def tool(tid, state, decided_by=None, approved=None):
    card = {"id": tid, "name": "invented_tool", "state": state, "decided_by": decided_by}
    if approved is not None:
        card["approval"] = {"approved": approved, "reason": "Invented reason"}
    return card


def plant_pre_045_rows(db):
    """Rows as they existed before 045: written with triggers and foreign keys off."""
    db.execute("SET session_replication_role = replica")
    for decision in ("approved", "rejected", "undone"):
        db.execute(
            "INSERT INTO app.yggdras_feedback(card_id,tool,decision,correction) VALUES (%s,'t',%s,'')",
            (f"card-{decision}", decision),
        )
    for state in ("pending", "accepted", "dismissed", "superseded"):
        db.execute(
            "INSERT INTO app.workflow_reviews(change_id,source_id,source_sequence,commitment_identity,"
            "reason,proposal,state) VALUES (%s,%s,1,%s,'Invented','{}',%s)",
            (uuid.uuid4(), uuid.uuid4(), f"c-{state}", state),
        )
    for state in ("waiting", "accepted", "dismissed"):
        db.execute(
            "INSERT INTO app.call_reviews(id,call_id,payload,state) VALUES (%s,%s,'{}',%s)",
            (uuid.uuid4(), uuid.uuid4(), state),
        )
    for n, state in enumerate(("pending", "accepted", "dismissed", "superseded")):
        db.execute(
            "INSERT INTO app.agent_proposals(run_id,ordinal,agent_id,payload,state) "
            "VALUES (%s,%s,'invented','{}',%s)",
            (uuid.uuid4(), n, state),
        )
    tools = [tool("a", "approval-responded", "user", True),
             tool("b", "approval-responded", "user", False),
             tool("c", "output-denied", None, False),      # timed out: not his verdict
             tool("d", "approval-requested")]  # fmt: skip
    db.execute(
        "INSERT INTO app.conductor_runs(id,request,status,mode,state,owner) "
        "VALUES (%s,'Invented','completed','executing',%s,'test')",
        (uuid.uuid4(), json.dumps({"tools": tools})),
    )
    db.execute("SET session_replication_role = origin")


EXPECTED = {  # eligible rows per source, by the rules in 045
    "yggdras_feedback": 3, "workflow_reviews": 2, "call_reviews": 2,
    "agent_proposals": 2, "conductor_runs": 2,
}  # fmt: skip


def counts(db):
    return {
        r["source_table"]: r["n"]
        for r in db.execute(
            "SELECT source_table, count(*) AS n FROM app.judgements GROUP BY 1"
        ).fetchall()
    }


def test_backfill_counts_match_every_source_and_a_rerun_changes_nothing(setup, postgres):
    with admin(postgres) as db:
        plant_pre_045_rows(db)
        assert counts(db) == {}  # nothing mirrored: these rows predate 045
        sql_text = MIGRATION.read_text(encoding="utf-8")
        db.execute(sql_text)
        assert counts(db) == EXPECTED
        db.execute(sql_text)  # the whole migration again
        assert counts(db) == EXPECTED and sum(counts(db).values()) == 11
        verdicts = {
            (r["source_table"], r["verdict"])
            for r in db.execute("SELECT source_table, verdict FROM app.judgements").fetchall()
        }
        assert ("yggdras_feedback", "undone") in verdicts
        assert ("agent_proposals", "approved") in verdicts and (
            "call_reviews",
            "rejected",
        ) in verdicts
        # the originals are kept
        assert db.execute("SELECT count(*) AS n FROM app.workflow_reviews").fetchone()["n"] == 4


def test_new_decisions_are_mirrored_in_the_same_transaction_and_only_once(setup, postgres):
    with admin(postgres) as db:
        db.execute("SET session_replication_role = replica")  # skip the agent_runs foreign key
        run = db.execute(
            "INSERT INTO app.agent_runs(chat_request_id,agent_id,model_id) "
            "VALUES (%s,'yggdras','invented') RETURNING id",
            (uuid.uuid4(),),
        ).fetchone()["id"]
        proposal = db.execute(
            "INSERT INTO app.agent_proposals(run_id,ordinal,agent_id,payload) "
            "VALUES (%s,0,'invented','{}') RETURNING id",
            (run,),
        ).fetchone()["id"]
        db.execute("SET session_replication_role = origin")
        assert counts(db) == {}  # pending is not a verdict
    with admin(postgres) as db:  # a later transaction decides it, as in real use
        db.execute(
            "UPDATE app.agent_proposals SET state='accepted', resolved_at=now() WHERE id=%s",
            (proposal,),
        )
        row = db.execute("SELECT * FROM app.judgements").fetchone()
        assert (row["source_table"], row["source_id"], row["verdict"]) == (
            "agent_proposals", str(proposal), "approved")  # fmt: skip
        db.execute("UPDATE app.agent_proposals SET state='superseded' WHERE id=%s", (proposal,))
        db.execute(
            "INSERT INTO app.yggdras_feedback(card_id,tool,decision,correction) "
            "VALUES ('card-live','t','rejected','Invented correction')"
        )
        assert counts(db) == {"agent_proposals": 1, "yggdras_feedback": 1}  # a verdict once
        assert (
            db.execute(
                "SELECT reason FROM app.judgements WHERE source_table='yggdras_feedback'"
            ).fetchone()["reason"]
            == "Invented correction"
        )


def test_answering_a_conductor_card_is_recorded(run_with_approval, postgres):  # noqa: F811
    conductor, _ = run_with_approval
    run = conductor.start("Invented: add a task")
    card = until(conductor, run.run_id, lambda s: s.status == "waiting").tools[0]
    assert conductor.answer_approval({"runId": run.run_id, "toolCallId": card.id, "approved": True})
    until(conductor, run.run_id, lambda s: s.status == "completed")
    with admin(postgres) as db:
        rows = db.execute("SELECT * FROM app.judgements").fetchall()
    assert [(r["source_table"], r["subject_key"], r["verdict"]) for r in rows] == [
        ("conductor_runs", f"{run.run_id}:{card.id}", "approved")
    ]


def test_the_agent_view_has_no_free_text(setup, postgres):
    with admin(postgres) as db:
        columns = {r["column_name"] for r in db.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='api' AND table_name='judgements'").fetchall()}  # fmt: skip
    assert "reason" not in columns and {"verdict", "source_table"} <= columns
