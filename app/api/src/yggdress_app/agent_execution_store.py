"""Private Temporal outbox, replay receipts and public body-free execution traces."""

import hashlib
import json
from uuid import UUID, uuid5

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from psycopg.types.json import Jsonb

from .agent_models import AgentError
from .chat import CHAT_LOCK


class ExecutionStore:
    def __init__(self, agents):
        self.agents, self.database = agents, agents.database

    def reconcile(self, model, activated_at=None):
        self.agents.enqueue(model, activated_at)
        with self.database.connect() as db:
            db.execute("SELECT pg_advisory_xact_lock(%s)", (CHAT_LOCK,))
            db.execute(
                "INSERT INTO app.agent_executions(run_id,workflow_id) SELECT id,'yggdras-agent-'||id::text FROM app.agent_runs WHERE state='queued' ON CONFLICT DO NOTHING"
            )
            return db.execute(
                "SELECT e.run_id,e.workflow_id,e.state,e.cancellation_requested,a.chat_request_id FROM app.agent_executions e JOIN app.agent_runs a ON a.id=e.run_id WHERE e.state IN ('pending','running','waiting') ORDER BY e.cancellation_requested DESC,(e.state='pending') DESC,e.updated_at,e.run_id LIMIT 100"
            ).fetchall()

    def run(self, identifier):
        with self.database.connect() as db:
            row = db.execute("SELECT * FROM app.agent_runs WHERE id=%s", (identifier,)).fetchone()
        if not row:
            raise AgentError("This execution no longer exists.")
        return row

    def begin(self, identifier):
        with self.database.connect() as db:
            db.execute("SELECT pg_advisory_xact_lock(%s)", (CHAT_LOCK,))
            row = db.execute(
                "SELECT * FROM app.agent_runs WHERE id=%s FOR UPDATE", (identifier,)
            ).fetchone()
            if not row:
                raise AgentError("This execution no longer exists.")
            if row["state"] == "queued":
                db.execute(
                    "UPDATE app.agent_runs SET state='running',lease=%s,lease_until=now()+interval '1 day' WHERE id=%s",
                    (uuid5(UUID(str(identifier)), "temporal-lease"), identifier),
                )
            db.execute(
                "UPDATE app.agent_executions SET state='running',updated_at=now() WHERE run_id=%s AND state='pending'",
                (identifier,),
            )
        return self.run(identifier)

    def context(self, identifier, slot, produce):
        with self.database.connect() as db:
            row = db.execute(
                "SELECT context FROM app.agent_executions WHERE run_id=%s", (identifier,)
            ).fetchone()
        if not row:
            raise AgentError("This execution no longer exists.")
        existing = row["context"] or {}
        if slot in existing:
            return existing[slot]
        value = jsonable_encoder(produce())
        with self.database.connect() as db:
            # Merge slots atomically. Duplicate preparation keeps the first snapshot.
            saved = db.execute(
                "UPDATE app.agent_executions SET context=coalesce(context,'{}'::jsonb)||jsonb_build_object(%s::text,%s::jsonb) WHERE run_id=%s AND NOT(coalesce(context,'{}'::jsonb)?%s) RETURNING context",
                (slot, Jsonb(value), identifier, slot),
            ).fetchone()
            if not saved:
                saved = db.execute(
                    "SELECT context FROM app.agent_executions WHERE run_id=%s", (identifier,)
                ).fetchone()
        return saved["context"][slot]

    def effect(self, identifier, ordinal, kind, agent, data, perform):
        fingerprint = hashlib.sha256(
            json.dumps([kind, agent, data], sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        with self.database.connect() as db:
            db.execute("SELECT pg_advisory_xact_lock(%s)", (CHAT_LOCK,))
            prior = db.execute(
                "SELECT * FROM app.agent_effects WHERE run_id=%s AND ordinal=%s FOR UPDATE",
                (identifier, ordinal),
            ).fetchone()
            if prior:
                if prior["fingerprint"] != fingerprint:
                    raise AgentError("The execution step changed. Resend explicitly to retry.")
                if prior["result"] is not None:
                    return prior["result"]
                if kind in ("model", "lia"):
                    raise AgentError(
                        "A previous model call was interrupted. It was not repeated; resend explicitly to retry."
                    )
            else:
                db.execute(
                    "INSERT INTO app.agent_effects(run_id,ordinal,agent_id,kind,fingerprint,state) VALUES (%s,%s,%s,%s,%s,'started')",
                    (identifier, ordinal, agent, kind, fingerprint),
                )
        # No model/network operation holds a database lock.
        value = jsonable_encoder(perform())
        with self.database.connect() as db:
            db.execute(
                "UPDATE app.agent_effects SET state=%s,result=%s,error=%s,completed_at=now() WHERE run_id=%s AND ordinal=%s",
                (
                    "completed" if value.get("ok", True) else "failed",
                    Jsonb(value),
                    "" if value.get("ok", True) else value.get("error", "Step failed."),
                    identifier,
                    ordinal,
                ),
            )
        return value

    def state(self, identifier, state):
        with self.database.connect() as db:
            db.execute(
                "UPDATE app.agent_executions SET state=%s,version=version+1,updated_at=now() WHERE run_id=%s AND state<>%s",
                (state, identifier, state),
            )

    def pending(self, identifier):
        with self.database.connect() as db:
            return db.execute(
                "SELECT id FROM app.agent_proposals WHERE run_id=%s AND state='pending' ORDER BY ordinal",
                (identifier,),
            ).fetchall()

    def fail_closed(self, identifier):
        with self.database.connect() as db:
            db.execute("SELECT pg_advisory_xact_lock(%s)", (CHAT_LOCK,))
            db.execute(
                "UPDATE app.agent_proposals SET state='superseded',version=version+1,resolved_at=now() WHERE run_id=%s AND state='pending'",
                (identifier,),
            )
            db.execute(
                "UPDATE app.agent_executions SET state='failed',version=version+1,updated_at=now() WHERE run_id=%s",
                (identifier,),
            )
            db.execute(
                "UPDATE app.agent_runs SET error='The execution was interrupted. Resend explicitly to retry.' WHERE id=%s AND error=''",
                (identifier,),
            )

    def trace(self, identifier):
        with self.database.connect() as db:
            run = db.execute(
                "SELECT a.id,a.agent_id,a.model_id,a.state AS result_state,a.created_at,a.finished_at,a.error,e.workflow_id,e.state,e.version,e.cancellation_requested,e.updated_at FROM app.agent_runs a JOIN app.agent_executions e ON e.run_id=a.id WHERE a.id=%s",
                (identifier,),
            ).fetchone()
            if not run:
                raise HTTPException(404, "Execution not found.")
            run["steps"] = db.execute(
                "SELECT ordinal,agent_id,kind,state,started_at,completed_at,error,extract(epoch FROM (completed_at-started_at))*1000 AS duration_ms FROM app.agent_effects WHERE run_id=%s ORDER BY ordinal LIMIT 100",
                (identifier,),
            ).fetchall()
            run["reviews"] = db.execute(
                "SELECT id,agent_id,state,version,created_at,resolved_at FROM app.agent_proposals WHERE run_id=%s ORDER BY ordinal LIMIT 8",
                (identifier,),
            ).fetchall()
            run["timings"] = db.execute(
                "SELECT coalesce(r.created_at,n.created_at,a.created_at) AS submitted_at,(SELECT min(started_at) FROM app.agent_effects f WHERE f.run_id=a.id) AS first_step_at,extract(epoch FROM ((SELECT min(started_at) FROM app.agent_effects f WHERE f.run_id=a.id)-coalesce(r.created_at,n.created_at,a.created_at)))*1000 AS pickup_ms,extract(epoch FROM (a.finished_at-coalesce(r.created_at,n.created_at,a.created_at)))*1000 AS result_ms FROM app.agent_runs a LEFT JOIN app.chat_requests r ON r.id=a.chat_request_id LEFT JOIN app.agent_note_events n ON n.id=a.note_event_id WHERE a.id=%s",
                (identifier,),
            ).fetchone()
        return run

    def cancel(self, identifier, version):
        with self.database.connect() as db:
            db.execute("SELECT pg_advisory_xact_lock(%s)", (CHAT_LOCK,))
            found = db.execute(
                "SELECT state,version,cancellation_requested FROM app.agent_executions WHERE run_id=%s FOR UPDATE",
                (identifier,),
            ).fetchone()
            if not found:
                raise HTTPException(404, "Execution not found.")
            if found["cancellation_requested"]:
                return {"state": "cancellation_requested"}
            if found["version"] != version:
                raise HTTPException(409, "This execution changed. Refresh before cancelling.")
            if found["state"] not in ("pending", "running", "waiting"):
                raise HTTPException(409, "This execution has already finished.")
            db.execute(
                "UPDATE app.agent_executions SET cancellation_requested=true,version=version+1,updated_at=now() WHERE run_id=%s",
                (identifier,),
            )
            # Cancel waiting proposals too; already applied decisions stay applied.
            db.execute(
                "UPDATE app.agent_proposals SET state='superseded',version=version+1,resolved_at=now() WHERE run_id=%s AND state='pending'",
                (identifier,),
            )
        return {"state": "cancellation_requested"}
