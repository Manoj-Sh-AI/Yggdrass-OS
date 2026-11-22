"""Narrow authority for one answered, time-bounded pre-task call."""

import hashlib
import hmac
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException
from pydantic import Field

from .planning_models import Model
from .security import token_hash

# ASSUMPTION: four minutes of conversation fits within the requested three-to-five minute cap.
CALL_LIMIT = timedelta(minutes=4)


def dispatch_metadata(database, row, fingerprint):
    if row.get("reason") != "Important task reminder":
        return None
    expiry = row["answered_at"] + CALL_LIMIT
    if expiry <= datetime.now(UTC):
        raise HTTPException(410, "This reminder call has ended.")
    material = f"daily-routine-voice:{row['id']}:{expiry.timestamp()}"
    token = hmac.new(fingerprint.encode(), material.encode(), hashlib.sha256).hexdigest()
    with database.connect() as db:
        found = db.execute(
            """UPDATE app.routine_voice_bindings SET capability_digest=%s, expires_at=%s
            WHERE call_id=%s RETURNING escalation_id""",
            (token_hash(token), expiry, row["id"]),
        ).fetchone()
        if not found:
            raise HTTPException(409, "This reminder is no longer available.")
    return {"purpose": "daily-routine", "call_id": str(row["id"]), "capability": token}


class Response(Model):
    action: Literal["confirm", "snooze"]
    minutes: int = Field(default=5, ge=1, le=30)
    read_back: Literal[True]


class Lookup(Model):
    question: str = Field(min_length=1, max_length=300)


def internal_router(database, calls, fingerprint):
    router = APIRouter(prefix="/voice")

    def bound(db, call_id, authorization):
        if not authorization or not authorization.startswith("Bearer ") or len(authorization) != 71:
            raise HTTPException(403, "This voice session is unavailable.")
        row = db.execute(
            """SELECT b.*,c.answer_session,c.answered_by FROM app.routine_voice_bindings b
            JOIN app.calls c ON c.id=b.call_id WHERE b.call_id=%s AND b.capability_digest=%s
            AND b.expires_at>now() AND c.state='answered' FOR UPDATE OF b""",
            (call_id, token_hash(authorization[7:])),
        ).fetchone()
        if row:
            valid = db.execute(
                """SELECT csrf FROM app.sessions
                   WHERE expires_at>now() AND password_fingerprint=%s""",
                (fingerprint,),
            ).fetchall()
            if any(
                hmac.compare_digest(token_hash(s["csrf"]), row["answer_session"]) for s in valid
            ):
                return row
        raise HTTPException(410, "This voice session has ended.")

    @router.get("/{call_id}")
    def brief(call_id: UUID, authorization: str = Header(default="")):
        with database.connect() as db:
            row = bound(db, call_id, authorization)
            participant = "client-" + token_hash(row["answer_session"] + row["answered_by"])[:24]
            return {
                "summary": row["summary"],
                "context": row["context"],
                "participant": participant,
                "remaining": max(0, (row["expires_at"] - datetime.now(UTC)).total_seconds()),
            }

    @router.post("/{call_id}/respond")
    def respond(call_id: UUID, body: Response, authorization: str = Header(default="")):
        from .routine_jobs import acknowledge_voice

        with database.connect() as db:
            row = bound(db, call_id, authorization)
            action_key = body.action if body.action == "confirm" else f"snooze:{body.minutes}"
            if row["applied_action"] == action_key:
                return {"recorded": True}
            if row["applied_action"]:
                raise HTTPException(409, "This reminder already has a response.")
            acknowledge_voice(db, row["escalation_id"], body.action, body.minutes)
            db.execute(
                "UPDATE app.routine_voice_bindings SET applied_action=%s WHERE call_id=%s",
                (action_key, call_id),
            )
        return {"recorded": True}

    @router.post("/{call_id}/lookup")
    def lookup(call_id: UUID, body: Lookup, authorization: str = Header(default="")):
        from .call_briefs import ask_lia

        with database.connect() as db:
            row = bound(db, call_id, authorization)
            if row["lookup_used"]:
                raise HTTPException(409, "The backup lookup has already been used.")
            db.execute(
                "UPDATE app.routine_voice_bindings SET lookup_used=true WHERE call_id=%s",
                (call_id,),
            )
        result = ask_lia(
            getattr(calls.briefs, "lia", None), None, "this task reminder", body.question
        )
        return {"answer": (result.get("answer") or result.get("note") or "Unavailable.")[:1500]}

    @router.post("/{call_id}/end")
    def end(call_id: UUID, authorization: str = Header(default="")):
        # A natural hangup or the hard cap can end only its own answered call.
        with database.connect() as db:
            digest = token_hash(authorization[7:]) if authorization.startswith("Bearer ") else ""
            row = db.execute(
                """UPDATE app.calls c SET state='ended',ended_at=now(),media_state='ended',
                version=version+1 FROM app.routine_voice_bindings b WHERE b.call_id=%s AND c.id=b.call_id
                AND b.capability_digest=%s AND c.state='answered'
                AND b.expires_at>=now()-interval '20 seconds' RETURNING c.*""",
                (call_id, digest),
            ).fetchone()
            if row:
                calls.event(db, row)
            return {"ended": bool(row)}

    return router
