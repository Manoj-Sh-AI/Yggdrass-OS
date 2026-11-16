"""Durable claims and exact-payload owner approval for application agents."""

from uuid import uuid4

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from psycopg.types.json import Jsonb

from .agent_tools import ApplicationTools, Proposal
from .chat import CHAT_LOCK
from .connections import observe_note
from .notes_proxy import NotesError
from .planning import LOCK
from .receivers import payload_fingerprint

AGENT_LOCK = 719218406


class AgentStore:
    def __init__(self, database):
        self.database = database
        self.tools = ApplicationTools(database)
        self.instance = uuid4()
        self.retry_intents = set()

    def prepare_write(self, slug, before_revision, operation):
        with self.database.connect() as db:
            return db.execute(
                "INSERT INTO app.agent_write_intents(owner_instance,slug,before_revision,operation) VALUES (%s,%s,%s,%s) RETURNING id",
                (
                    self.instance,
                    slug,
                    str(before_revision) if before_revision is not None else None,
                    operation,
                ),
            ).fetchone()["id"]

    def write_failed(self, intent, definitive=False):
        with self.database.connect() as db:
            db.execute(
                "UPDATE app.agent_write_intents SET owner_instance=NULL,state=%s WHERE id=%s AND state='prepared'",
                ("rejected" if definitive else "prepared", intent),
            )

    def recover_writes(self, notes):
        from .connections import verified_note

        with self.database.connect() as db:
            rows = db.execute(
                "SELECT * FROM app.agent_write_intents WHERE state='prepared' AND (owner_instance IS DISTINCT FROM %s OR id=ANY(%s::uuid[])) AND created_at<now()-interval '10 seconds' ORDER BY created_at,id LIMIT 20",
                (self.instance, list(self.retry_intents)),
            ).fetchall()
        for row in rows:
            try:
                note = verified_note(notes, row["slug"])
            except NotesError:
                continue  # Unavailable/missing is not invented deletion or a saved edit.
            if row["before_revision"] != note["version"]:
                self.note_saved(note, row["id"])
                self.retry_intents.discard(row["id"])

    def note_saved(self, note, intent=None):
        with self.database.connect() as db:
            db.execute("SELECT pg_advisory_xact_lock(%s)", (AGENT_LOCK,))
            # Undo can revisit a content version. A save intent, not the content
            # hash, identifies the new operation; retrying that intent is a replay.
            if intent:
                prior = db.execute(
                    "SELECT id FROM app.agent_note_events WHERE id=%s", (intent,)
                ).fetchone()
                if prior:
                    return prior["id"]
            else:
                prior = db.execute(
                    "SELECT e.id FROM app.agent_note_events e JOIN app.note_refs n ON n.id=e.note_ref_id WHERE n.source='brain' AND n.external_id=%s AND e.revision=%s ORDER BY e.created_at DESC,e.id DESC LIMIT 1",
                    (note["slug"], note["version"]),
                ).fetchone()
                if prior:
                    return prior["id"]
            reference = observe_note(db, note["slug"], note)
            event = db.execute(
                "INSERT INTO app.agent_note_events(id,note_ref_id,slug,revision) VALUES (%s,%s,%s,%s) RETURNING id",
                (intent or uuid4(), reference["id"], note["slug"], note["version"]),
            ).fetchone()["id"]
            if intent:
                db.execute(
                    "UPDATE app.agent_write_intents SET state='completed',observed_event_id=%s,finished_at=now() WHERE id=%s",
                    (event, intent),
                )
            return event

    def enqueue(self, model, activated_at=None):
        """Only explicitly queued messages; held history can never enter this query."""
        with self.database.connect() as db:
            db.execute("SELECT pg_advisory_xact_lock(%s)", (CHAT_LOCK,))
            db.execute("SELECT pg_advisory_xact_lock(%s)", (AGENT_LOCK,))
            db.execute(
                "UPDATE app.agent_proposals p SET state='superseded',version=p.version+1,resolved_at=now() FROM app.agent_runs a JOIN app.chat_requests r ON r.id=a.chat_request_id JOIN app.chat_messages m ON m.id=r.user_message_id JOIN app.chat_conversations c ON c.id=r.conversation_id WHERE p.run_id=a.id AND p.state='pending' AND (m.deleted_at IS NOT NULL OR m.version<>r.user_message_version OR c.archived OR r.state IN ('failed','cancelled') OR EXISTS(SELECT 1 FROM app.chat_requests newer WHERE newer.user_message_id=r.user_message_id AND (newer.created_at,newer.id)>(r.created_at,r.id)))"
            )
            db.execute(
                "INSERT INTO app.agent_runs(chat_request_id,agent_id,model_id) SELECT r.id,r.agent_id,r.model_id FROM app.chat_requests r JOIN app.chat_messages m ON m.id=r.user_message_id JOIN app.chat_conversations c ON c.id=r.conversation_id WHERE r.state='queued' AND m.deleted_at IS NULL AND m.version=r.user_message_version AND NOT c.archived AND r.agent_id IN ('yggdras','lia','tasks','calendar') AND (%s::timestamptz IS NULL OR r.created_at>=%s::timestamptz) ON CONFLICT DO NOTHING",
                (activated_at, activated_at),
            )
            db.execute(
                "INSERT INTO app.agent_runs(note_event_id,agent_id,model_id) SELECT id,'lia',%s FROM app.agent_note_events WHERE state='queued' ON CONFLICT DO NOTHING",
                ("default",),
            )
            db.execute(
                "INSERT INTO app.agent_runs(handoff_id,agent_id,model_id) SELECT id,'yggdras',%s FROM app.note_handoffs WHERE state='pending' AND (%s::timestamptz IS NULL OR received_at>=%s::timestamptz) ON CONFLICT DO NOTHING",
                (model, activated_at, activated_at),
            )

    def claim(self, lane=None):
        if lane not in (None, "chat", "background"):
            raise ValueError("Unknown execution lane.")
        with self.database.connect() as db:
            db.execute("SELECT pg_advisory_xact_lock(%s)", (CHAT_LOCK,))
            # A lost worker may already have paid for a request. Never replay it silently.
            expired = db.execute(
                "UPDATE app.agent_runs a SET state='failed',error='Execution was interrupted. Resend explicitly to try again.',finished_at=now() WHERE state='running' AND lease_until<now() AND NOT EXISTS(SELECT 1 FROM app.agent_executions e WHERE e.run_id=a.id) RETURNING id,chat_request_id,note_event_id"
            ).fetchall()
            for row in expired:
                db.execute(
                    "UPDATE app.background_runs SET state='failed',ended_at=coalesce(ended_at,now()),version=version+1 WHERE provider='yggdras-local' AND external_run_id=%s AND state IN ('queued','running')",
                    (str(row["id"]),),
                )
                if row["note_event_id"]:
                    db.execute(
                        "UPDATE app.agent_note_events SET state='failed' WHERE id=%s",
                        (row["note_event_id"],),
                    )
                if row["chat_request_id"]:
                    db.execute(
                        "UPDATE app.chat_requests SET state='failed',error='Execution was interrupted. Resend explicitly to try again.',version=version+1 WHERE id=%s AND state IN ('queued','streaming')",
                        (row["chat_request_id"],),
                    )
            chosen = db.execute(
                "SELECT * FROM app.agent_runs a WHERE state='queued' AND NOT EXISTS(SELECT 1 FROM app.agent_executions e WHERE e.run_id=a.id) AND (%s::text IS NULL OR (%s='chat' AND chat_request_id IS NOT NULL) OR (%s='background' AND chat_request_id IS NULL)) ORDER BY (chat_request_id IS NOT NULL) DESC,created_at,id LIMIT 1 FOR UPDATE SKIP LOCKED",
                (lane, lane, lane),
            ).fetchone()
            if not chosen:
                return None
            lease = uuid4()
            return db.execute(
                "UPDATE app.agent_runs SET state='running',lease=%s,lease_until=now()+interval '5 minutes' WHERE id=%s RETURNING *",
                (lease, chosen["id"]),
            ).fetchone()

    def current(self, run):
        with self.database.connect() as db:
            found = db.execute(
                "SELECT 1 FROM app.agent_runs a WHERE id=%s AND state='running' AND lease=%s AND (lease_until>now() OR EXISTS(SELECT 1 FROM app.agent_executions e WHERE e.run_id=a.id))",
                (run["id"], run["lease"]),
            ).fetchone()
            if not found:
                return False
            if run["chat_request_id"]:
                found = db.execute(
                    "SELECT 1 FROM app.chat_requests r JOIN app.chat_messages m ON m.id=r.user_message_id JOIN app.chat_conversations c ON c.id=r.conversation_id WHERE r.id=%s AND r.state IN ('queued','streaming') AND m.deleted_at IS NULL AND m.version=r.user_message_version AND NOT c.archived",
                    (run["chat_request_id"],),
                ).fetchone()
            return bool(found)

    def record(self, run, agent, reply=None):
        with self.database.connect() as db:
            db.execute(
                "SELECT id FROM app.agent_runs WHERE id=%s AND lease=%s FOR UPDATE",
                (run["id"], run["lease"]),
            )
            ordinal = db.execute(
                "SELECT coalesce(max(ordinal),-1)+1 AS n FROM app.agent_steps WHERE run_id=%s",
                (run["id"],),
            ).fetchone()["n"]
            row = db.execute(
                "INSERT INTO app.agent_steps(run_id,agent_id,ordinal,state,input_tokens,output_tokens,completed_at) VALUES (%s,%s,%s,%s,%s,%s,CASE WHEN %s THEN now() END) RETURNING id",
                (
                    run["id"],
                    agent,
                    ordinal,
                    "completed" if reply else "started",
                    reply.input_tokens if reply else 0,
                    reply.output_tokens if reply else 0,
                    reply is not None,
                ),
            ).fetchone()
            return row["id"]

    def finish(self, run, result=None, error=""):
        with self.database.connect() as db:
            db.execute("SELECT pg_advisory_xact_lock(%s)", (CHAT_LOCK,))
            db.execute("SELECT pg_advisory_xact_lock(%s)", (AGENT_LOCK,))
            owned = db.execute(
                "SELECT state FROM app.agent_runs WHERE id=%s AND lease=%s FOR UPDATE",
                (run["id"], run["lease"]),
            ).fetchone()
            if not owned or owned["state"] != "running":
                return False
            if result:
                # Recheck cancellation and source-message version before publishing proposals.
                if (
                    run["chat_request_id"]
                    and not db.execute(
                        "SELECT 1 FROM app.chat_requests r JOIN app.chat_messages m ON m.id=r.user_message_id WHERE r.id=%s AND r.state IN ('queued','streaming') AND m.deleted_at IS NULL AND m.version=r.user_message_version",
                        (run["chat_request_id"],),
                    ).fetchone()
                ):
                    db.execute(
                        "UPDATE app.agent_runs SET state='cancelled',finished_at=now() WHERE id=%s",
                        (run["id"],),
                    )
                    return False
                unique = {}
                for proposal in result.proposals:
                    unique.setdefault(
                        payload_fingerprint(
                            proposal.model_copy(update={"explanation": "deduplicate"})
                        ),
                        proposal,
                    )
                for index, proposal in enumerate(unique.values()):
                    agent = "tasks" if proposal.operation.startswith("task.") else "calendar"
                    db.execute(
                        "INSERT INTO app.agent_proposals(run_id,ordinal,agent_id,payload) VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                        (run["id"], index, agent, Jsonb(proposal.model_dump(mode="json"))),
                    )
            db.execute(
                "UPDATE app.agent_runs SET state=%s,error=%s,result=%s,finished_at=now() WHERE id=%s",
                (
                    "failed" if error else "completed",
                    error,
                    Jsonb({"answer": result.answer}) if result else None,
                    run["id"],
                ),
            )
            if run["note_event_id"]:
                db.execute(
                    "UPDATE app.agent_note_events SET state=%s WHERE id=%s",
                    ("failed" if error else "completed", run["note_event_id"]),
                )
            return True

    def resolve(self, command):
        fingerprint = payload_fingerprint(command)
        with self.database.connect() as db:
            db.execute("SELECT pg_advisory_xact_lock(%s)", (CHAT_LOCK,))
            # Match planning lock order before locking approval/target rows.
            db.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK,))
            prior = db.execute(
                "SELECT decision_fingerprint,result FROM app.agent_proposals WHERE decision_key=%s LIMIT 1",
                (command.key,),
            ).fetchone()
            if prior:
                if prior["decision_fingerprint"] != fingerprint:
                    raise HTTPException(409, "This retry key belongs to another decision.")
                return jsonable_encoder(prior["result"])
            row = db.execute(
                "SELECT p.*,r.chat_request_id FROM app.agent_proposals p JOIN app.agent_runs r ON r.id=p.run_id WHERE p.id=%s FOR UPDATE OF p",
                (command.id,),
            ).fetchone()
            if not row:
                raise HTTPException(404, "This proposal no longer exists.")
            if row["decision_key"] == command.key:
                if row["decision_fingerprint"] != fingerprint:
                    raise HTTPException(409, "This retry key belongs to another decision.")
                return row["result"]
            if row["state"] != "pending" or row["version"] != command.version:
                raise HTTPException(409, "This proposal changed. Refresh before deciding.")
            if db.execute(
                "SELECT 1 FROM app.agent_executions WHERE run_id=%s AND cancellation_requested",
                (row["run_id"],),
            ).fetchone():
                raise HTTPException(
                    409, "This execution was cancelled. The proposal cannot be applied."
                )
            result = {"state": "dismissed"}
            if command.decision == "accept":
                if row["chat_request_id"]:
                    # Serialize with message edits/resends, without holding an
                    # external HTTP/model call inside this transaction.
                    db.execute(
                        "SELECT m.id FROM app.chat_messages m JOIN app.chat_requests r ON r.user_message_id=m.id WHERE r.id=%s FOR SHARE OF m",
                        (row["chat_request_id"],),
                    )
                if (
                    row["chat_request_id"]
                    and not db.execute(
                        "SELECT 1 FROM app.chat_requests r JOIN app.chat_messages m ON m.id=r.user_message_id JOIN app.chat_conversations c ON c.id=r.conversation_id WHERE r.id=%s AND r.state='completed' AND m.deleted_at IS NULL AND m.version=r.user_message_version AND NOT c.archived AND NOT EXISTS(SELECT 1 FROM app.chat_requests newer WHERE newer.user_message_id=r.user_message_id AND (newer.created_at,newer.id)>(r.created_at,r.id))",
                        (row["chat_request_id"],),
                    ).fetchone()
                ):
                    raise HTTPException(
                        409,
                        "The source message changed or was cancelled. Ask again before applying this proposal.",
                    )
                result = {
                    "state": "accepted",
                    **self.tools.execute(Proposal.model_validate(row["payload"]), row["id"], db),
                }
            db.execute(
                "UPDATE app.agent_proposals SET state=%s,version=version+1,result=%s,decision_key=%s,decision_fingerprint=%s,resolved_at=now() WHERE id=%s",
                (result["state"], Jsonb(result), command.key, fingerprint, row["id"]),
            )
            return jsonable_encoder(result)
