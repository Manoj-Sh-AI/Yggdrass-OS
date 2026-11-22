"""Explicit nightly filing through Lia. The app owns evidence, decisions and private receipts."""

from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import HTTPException
from psycopg.types.json import Jsonb
from pydantic import Field

from .daily_content import _day_lock, _entry, digest
from .planning_models import Model

Slug = Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{1,200}$")]


class Evidence(Model):
    entry_id: UUID
    quote: str = Field(min_length=1, max_length=500)


class Action(Model):
    target: Slug
    fact: str = Field(min_length=1, max_length=800, pattern=r"^[^\r\n]+$")
    evidence: list[Evidence] = Field(min_length=1, max_length=5)


class Proposal(Model):
    actions: list[Action] = Field(max_length=8)


def _public(row):
    return {
        k: row[k] for k in ("id", "for_date", "state", "target", "fact", "evidence", "applied_at")
    } | {
        "can_undo": bool(row["undo_ref"])
        and row["state"] == "applied"
        and row["applied_at"] > datetime.now(UTC) - timedelta(days=1)
    }


def list_actions(db, day=None):
    rows = db.execute(
        "SELECT a.*,r.for_date FROM app.daily_filing_actions a JOIN app.daily_filing_runs r "
        "ON r.id=a.run_id WHERE (%s::date IS NULL OR r.for_date=%s) ORDER BY a.created_at DESC,a.ordinal LIMIT 100",
        (day, day),
    ).fetchall()
    return [_public(r) for r in rows]


def _action(db, identifier, lock=False):
    row = db.execute(
        "SELECT a.*,r.for_date FROM app.daily_filing_actions a JOIN app.daily_filing_runs r ON r.id=a.run_id "
        "WHERE a.id=%s" + (" FOR UPDATE OF a" if lock else ""),
        (identifier,),
    ).fetchone()
    if not row:
        raise HTTPException(404, "Filing proposal not found.")
    return row


def consolidate(database, lia, day):
    """Only entries unclaimed by a successful run go through the model. Empty days cost nothing."""
    lease = uuid4()
    with database.connect() as db:
        _day_lock(db, day)
        if db.execute(
            "SELECT 1 FROM app.daily_filing_runs WHERE for_date=%s AND state='running' "
            "AND locked_until>now()",
            (day,),
        ).fetchone():
            raise HTTPException(409, "Lia is already preparing this day.")
        entries = db.execute(
            "SELECT id,text FROM app.journal_entries j WHERE local_date=%s AND kind IN ('review','journal') "
            "AND text<>'' AND NOT EXISTS(SELECT 1 FROM app.journal_entries c WHERE c.supersedes_id=j.id) "
            "AND NOT EXISTS(SELECT 1 FROM app.daily_filing_runs r WHERE state='proposed' AND j.id=ANY(r.entry_ids)) "
            "ORDER BY created_at,id LIMIT 10",
            (day,),
        ).fetchall()
        if not entries:
            return {"run_id": None, "actions": list_actions(db, day)}
        if lia is None or not hasattr(lia, "propose_daily"):
            raise HTTPException(503, "Lia is unavailable for filing. Journal entries remain saved.")
        evidence = {str(row["id"]): row["text"] for row in entries}
        corrections = db.execute(
            "SELECT text FROM app.journal_entries WHERE kind='filing_decision' "
            "ORDER BY created_at DESC LIMIT 5"
        ).fetchall()
        fingerprint = digest([day, entries])
        run = db.execute(
            "INSERT INTO app.daily_filing_runs(for_date,input_hash,entry_ids,state,lease,locked_until) "
            "VALUES(%s,%s,%s,'running',%s,now()+interval '4 minutes') ON CONFLICT(input_hash) DO UPDATE SET "
            "state='running',lease=excluded.lease,locked_until=excluded.locked_until "
            "WHERE daily_filing_runs.state='failed' OR "
            "(daily_filing_runs.state='running' AND daily_filing_runs.locked_until <= now()) RETURNING id",
            (day, fingerprint, [r["id"] for r in entries], lease),
        ).fetchone()
        if not run:
            return {"run_id": None, "actions": list_actions(db, day)}
    try:
        answer = lia.propose_daily(
            [{"id": k, "text": v} for k, v in evidence.items()], [r["text"] for r in corrections]
        )
        proposal = Proposal.model_validate(answer["proposal"])
        for action in proposal.actions:
            if any(e.quote not in evidence.get(str(e.entry_id), "") for e in action.evidence):
                raise ValueError("Invalid evidence span.")
    except Exception:  # noqa: BLE001 -- provider exceptions can contain private context.
        with database.connect() as db:
            db.execute(
                "UPDATE app.daily_filing_runs SET state='failed' WHERE id=%s AND lease=%s",
                (run["id"], lease),
            )
        raise HTTPException(
            503, "Filing proposals could not be prepared. Your journal is saved."
        ) from None
    with database.connect() as db:
        _day_lock(db, day)
        saved = db.execute(
            "UPDATE app.daily_filing_runs SET state='proposed',proposal=%s WHERE id=%s AND lease=%s "
            "AND state='running' RETURNING id",
            (
                Jsonb(
                    {
                        "actions": proposal.model_dump(mode="json")["actions"],
                        "model": answer.get("model"),
                        "usage": answer.get("usage"),
                        "prompt_version": 1,
                    }
                ),
                run["id"],
                lease,
            ),
        ).fetchone()
        if not saved:
            raise HTTPException(409, "A newer filing run has taken over.")
        for n, a in enumerate(proposal.actions):
            ids = [e.entry_id for e in a.evidence]
            if db.execute(
                "SELECT 1 FROM app.journal_entries WHERE supersedes_id=ANY(%s)", (ids,)
            ).fetchone():
                continue
            if db.execute(
                "SELECT 1 FROM app.daily_filing_actions WHERE target=%s AND lower(fact)=lower(%s) "
                "AND state IN ('proposed','applying','applied')",
                (a.target, a.fact),
            ).fetchone():
                continue
            db.execute(
                "INSERT INTO app.daily_filing_actions(run_id,ordinal,target,fact,evidence,state) "
                "VALUES(%s,%s,%s,%s,%s,'proposed')",
                (run["id"], n, a.target, a.fact, Jsonb(a.model_dump(mode="json")["evidence"])),
            )
        return {"run_id": run["id"], "actions": list_actions(db, day)}


def decide(database, lia, identifier, decision, target=None):
    """Only an authenticated, explicit owner decision crosses Lia's write boundary."""
    with database.connect() as db:
        row = _action(db, identifier, lock=True)
        if (
            decision == "reject"
            and row["state"] == "rejected"
            or decision == "accept"
            and row["state"] == "applied"
            or decision == "undo"
            and row["state"] == "reverted"
        ):
            return _public(row)
        if decision in ("move", "reject") and row["state"] == "proposed":
            if decision == "move":
                from pydantic import TypeAdapter, ValidationError

                try:
                    target = TypeAdapter(Slug).validate_python(target)
                except ValidationError:
                    raise HTTPException(422, "Choose a valid destination note.") from None
                db.execute(
                    "UPDATE app.daily_filing_actions SET target=%s,updated_at=now() WHERE id=%s",
                    (target, identifier),
                )
            else:
                db.execute(
                    "UPDATE app.daily_filing_actions SET state='rejected',updated_at=now() WHERE id=%s",
                    (identifier,),
                )
            _entry(
                db,
                uuid4(),
                row["for_date"],
                "text",
                "filing_decision",
                f"{decision}: {row['fact']} ({row['target']}"
                + (f" to {target}" if decision == "move" else "")
                + ")",
                {"action_id": str(identifier), "decision": decision},
            )
            return _public(_action(db, identifier))
        if decision == "accept" and row["state"] == "proposed":
            cited = [UUID(e["entry_id"]) for e in row["evidence"]]
            if db.execute(
                "SELECT 1 FROM app.journal_entries WHERE supersedes_id=ANY(%s)", (cited,)
            ).fetchone():
                raise HTTPException(
                    409,
                    "This entry was corrected. Reject the old proposal and file the correction.",
                )
            operation = "file_daily_fact"
            progress = "applying"
        elif decision == "undo" and _public(row)["can_undo"]:
            operation = "undo_daily_fact"
            progress = "undoing"
        else:
            raise HTTPException(409, "Review the current filing state before deciding again.")
        if not callable(getattr(lia, operation, None)):
            raise HTTPException(503, "Lia's approved filing service is unavailable.")
        db.execute(
            "UPDATE app.daily_filing_actions SET state=%s,updated_at=now() WHERE id=%s",
            (progress, identifier),
        )
    # This is an external, potentially committed write. An ambiguous receipt must not auto-retry.
    try:
        result = (
            lia.file_daily_fact(row["target"], row["fact"], identifier)
            if decision == "accept"
            else lia.undo_daily_fact(row["undo_ref"])
        )
        if not isinstance(result.get("done"), bool):
            raise TypeError("Missing write receipt.")
        if result["done"] and decision == "accept" and not result.get("receipt"):
            raise ValueError("Missing undo receipt.")
    except Exception:  # noqa: BLE001 -- any missing write receipt is an ambiguous commit.
        with database.connect() as db:
            db.execute(
                "UPDATE app.daily_filing_actions SET state='uncertain',updated_at=now() WHERE id=%s",
                (identifier,),
            )
        raise HTTPException(
            409, "Lia's receipt is unavailable. Check the destination before retrying this change."
        ) from None
    with database.connect() as db:
        if result["done"]:
            state = "applied" if decision == "accept" else "reverted"
            db.execute(
                "UPDATE app.daily_filing_actions SET state=%s,updated_at=now(),"
                "applied_at=coalesce(applied_at,now()),undo_ref=%s WHERE id=%s",
                (state, Jsonb(result["receipt"]) if decision == "accept" else None, identifier),
            )
            _entry(
                db,
                uuid4(),
                row["for_date"],
                "text",
                "filing_receipt",
                f"Filing {decision} recorded.",
                {"action_id": str(identifier), "decision": decision},
            )
        else:
            db.execute(
                "UPDATE app.daily_filing_actions SET state=%s,updated_at=now() WHERE id=%s",
                (row["state"], identifier),
            )
        state = _public(_action(db, identifier))
    if not result["done"]:
        raise HTTPException(
            409, result.get("reason") or "Lia could not apply this change. Review the destination."
        )
    return state
