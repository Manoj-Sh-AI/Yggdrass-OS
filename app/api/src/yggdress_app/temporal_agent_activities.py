"""Temporal activities adapt existing agents, Brain reads and checked app writes."""

from dataclasses import asdict
from uuid import uuid5

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from pydantic import ValidationError
from temporalio import activity

from . import agent_skills
from .agent_api import AgentDecision
from .agent_execution_store import ExecutionStore
from .agent_models import AgentError
from .agent_specialists import AgentResult
from .agent_tools import Proposal
from .connections import verified_note
from .handoffs import NoteHandoff
from .notes_proxy import NotesError


class AgentActivities:
    def __init__(self, runner):
        self.runner = runner
        self.store = ExecutionStore(runner.store)

    def check(self, run):
        if self.runner.cancelled(run):
            raise AgentError("This request was cancelled or its source changed.")

    @activity.defn(name="app_agent_prepare")
    def prepare(self, command: dict) -> dict:
        identifier = command["run_id"]
        run = self.store.begin(identifier)
        self.check(run)
        self.runner.background(run, 0, "running")
        if run["chat_request_id"]:
            context = self.store.context(identifier, "chat", lambda: self.runner.chat_input(run))
            return {
                "kind": "chat",
                "agent": run["agent_id"],
                "model": run["model_id"],
                "context": {k: v for k, v in context.items() if k != "files"},
                "has_files": bool(context["files"]),
            }
        if run["note_event_id"]:

            def note_input():
                with self.store.database.connect() as db:
                    event = db.execute(
                        "SELECT * FROM app.agent_note_events WHERE id=%s", (run["note_event_id"],)
                    ).fetchone()
                note = verified_note(self.runner.notes, event["slug"])
                return {"event": event, "superseded": note["version"] != event["revision"]}

            return {"kind": "note", "context": self.store.context(identifier, "note", note_input)}

        def handoff_input():
            with self.store.database.connect() as db:
                row = db.execute(
                    "SELECT payload FROM app.note_handoffs WHERE id=%s", (run["handoff_id"],)
                ).fetchone()
            event = row["payload"]
            note = (
                verified_note(self.runner.notes, event["slug"])
                if event["lifecycle"] == "active"
                else None
            )
            if note and note["version"] != event["revision"]:
                raise AgentError("A newer saved note superseded this handoff.")
            return {"event": event, "source_body": note["rawBody"] if note else ""}

        return {
            "kind": "handoff",
            "context": self.store.context(identifier, "handoff", handoff_input),
        }

    @activity.defn(name="app_agent_effect")
    def effect(self, command: dict) -> dict:
        identifier, kind, domain = command["run_id"], command["kind"], command["agent"]
        run = self.store.run(identifier)
        self.check(run)

        def perform():
            data = command["data"]
            try:
                if kind == "model":
                    selected = (
                        self.runner.default_model
                        if run["model_id"] == "default"
                        else run["model_id"]
                    )
                    model = self.runner.model_factory(selected)
                    with self.store.database.connect() as db:
                        context = (
                            db.execute(
                                "SELECT context FROM app.agent_executions WHERE run_id=%s",
                                (identifier,),
                            ).fetchone()["context"]
                            or {}
                        )
                    files = context.get("chat", {}).get("files", [])
                    if files and domain == run["agent_id"]:
                        data = {**data, "messages": list(data["messages"])}
                        first = dict(data["messages"][0])
                        first["content"] = [{"type": "text", "text": first["content"]}, *files]
                        data["messages"][0] = first
                    step = self.runner.store.record(run, domain)
                    reply = model.complete(**data)
                    with self.store.database.connect() as db:
                        db.execute(
                            "UPDATE app.agent_steps SET state='completed',input_tokens=%s,output_tokens=%s,completed_at=now() WHERE id=%s",
                            (reply.input_tokens, reply.output_tokens, step),
                        )
                    value = asdict(reply)
                elif kind == "lia":
                    value = self.runner.lia.ask(**data)
                elif kind == "read":
                    value = self.runner.store.tools.read(domain, data)
                elif kind == "inspect":
                    value = self.runner.store.tools.inspect(Proposal.model_validate(data))
                elif kind == "skill":
                    value = agent_skills.load(domain, data)
                elif kind == "cursor":
                    value = self.runner.receivers.call(
                        "workflow", "workflow/source?handoff_id=" + str(run["handoff_id"])
                    )
                elif kind == "publish_note":
                    value = self.publish_note(run, data["answer"])
                elif kind == "commit_handoff":
                    value = self.commit_handoff(run, domain, data)
                elif kind == "ack_handoff":
                    value = self.runner.receivers.call(
                        "workflow_dispatch", "handoffs/acknowledge", {"id": str(run["handoff_id"])}
                    )
                else:
                    raise AgentError("Unknown execution operation.")
                return {"ok": True, "value": jsonable_encoder(value)}
            except HTTPException as error:
                return {"ok": False, "error": str(error.detail)[:2000], "status": error.status_code}
            except (ValidationError, ValueError):
                return {
                    "ok": False,
                    "error": "Invalid tool arguments. Check the permitted fields and current record version.",
                    "status": 422,
                }
            except (AgentError, NotesError) as error:
                return {"ok": False, "error": str(error)[:2000]}
            except Exception:  # noqa: BLE001 -- never serialize private provider failures
                return {
                    "ok": False,
                    "error": "This agent step could not finish. No automatic paid retry was made.",
                }

        return self.store.effect(
            identifier, command["ordinal"], kind, domain, command["data"], perform
        )

    def publish_note(self, run, answer):
        with self.store.database.connect() as db:
            event = db.execute(
                "SELECT * FROM app.agent_note_events WHERE id=%s", (run["note_event_id"],)
            ).fetchone()
        if verified_note(self.runner.notes, event["slug"])["version"] != event["revision"]:
            raise AgentError(
                "The note changed during Lia's review. No stale context was handed off."
            )

        def command():
            with self.store.database.connect() as db:
                previous = db.execute(
                    "SELECT revision,sequence FROM app.note_handoffs WHERE producer='lia-application-adapter' AND namespace='brain-api' AND external_identity=%s ORDER BY sequence DESC LIMIT 1",
                    (str(event["note_ref_id"]),),
                ).fetchone()
            return NoteHandoff(
                id=event["id"],
                producer="lia-application-adapter",
                namespace="brain-api",
                external_identity=str(event["note_ref_id"]),
                sequence=previous["sequence"] + 1 if previous else 0,
                previous_revision=previous["revision"] if previous else None,
                revision=event["revision"],
                slug=event["slug"],
                context=answer[:4000],
            ).model_dump(mode="json")

        payload = self.store.context(run["id"], "note_commit", command)
        self.check(run)
        return self.runner.receivers.call("note_signals", "note-signals", payload)

    def commit_handoff(self, run, domain, data):
        with self.store.database.connect() as db:
            event = db.execute(
                "SELECT payload FROM app.note_handoffs WHERE id=%s", (run["handoff_id"],)
            ).fetchone()["payload"]
        cursor = data["cursor"]
        command = {
            "handoff_id": str(run["handoff_id"]),
            "change_id": str(uuid5(run["id"], domain)),
            "producer": domain + "-agent",
            "producer_version": "application-agents-v1",
            "namespace": event["namespace"],
            "external_identity": event["external_identity"],
            "sequence": cursor["next_sequence"],
            "previous_revision": cursor["previous_revision"],
            "revision": event["revision"],
            "slug": event["slug"],
            "lifecycle": event["lifecycle"],
            "causation_id": str(run["id"]),
            "interpretations": data["items"],
        }
        self.check(run)
        return self.runner.receivers.call("workflow", "workflow/changes", command)

    @activity.defn(name="app_agent_finish")
    def finish(self, command: dict) -> dict:
        run = self.store.run(command["run_id"])
        with self.store.database.connect() as db:
            db.execute(
                "UPDATE app.agent_effects SET state=CASE WHEN kind IN ('model','lia') THEN 'uncertain' ELSE 'failed' END,error='This step was interrupted; no automatic paid retry was made.',completed_at=now() WHERE run_id=%s AND state='started'",
                (run["id"],),
            )
        if run["state"] in ("queued", "running"):
            cancelled = self.runner.cancelled(run)
            error = (
                "This request was cancelled or its source changed."
                if cancelled
                else command.get("error", "")
            )
            result = (
                None
                if error
                else AgentResult(
                    command.get("answer", ""),
                    [Proposal.model_validate(p) for p in command.get("proposals", [])],
                )
            )
            self.runner.store.finish(run, result, error)
            if cancelled:
                with self.store.database.connect() as db:
                    db.execute(
                        "UPDATE app.agent_runs SET state='cancelled' WHERE id=%s", (run["id"],)
                    )
        run = self.store.run(command["run_id"])
        pending = self.store.pending(run["id"])
        state = "waiting" if pending else run["state"]
        self.store.state(run["id"], state)
        self.runner.background(run, 1, "succeeded" if run["state"] == "completed" else run["state"])
        self.runner.deliver(run["id"])
        return {"state": state, "pending": len(pending)}

    @activity.defn(name="app_agent_review")
    def review(self, command: dict) -> dict:
        identifier = command["run_id"]
        if command.get("cancel"):
            with self.store.database.connect() as db:
                db.execute(
                    "UPDATE app.agent_proposals SET state='superseded',version=version+1,resolved_at=now() WHERE run_id=%s AND state='pending'",
                    (identifier,),
                )
        if command.get("decision"):
            try:
                body = AgentDecision.model_validate(command["decision"])
                with self.store.database.connect() as db:
                    found = db.execute(
                        "SELECT 1 FROM app.agent_proposals WHERE run_id=%s AND id=%s",
                        (identifier, body.id),
                    ).fetchone()
                if not found:
                    raise HTTPException(404, "Review not found for this execution.")
                result = self.runner.store.resolve(body)
            except HTTPException as error:
                return {"ok": False, "status": error.status_code, "error": str(error.detail)}
        else:
            result = None
        pending = self.store.pending(identifier)
        with self.store.database.connect() as db:
            row = db.execute(
                "SELECT cancellation_requested FROM app.agent_executions WHERE run_id=%s",
                (identifier,),
            ).fetchone()
        cancelled = not row or row["cancellation_requested"]
        state = "cancelled" if cancelled else "waiting" if pending else "completed"
        self.store.state(identifier, state)
        return {
            "ok": True,
            "value": jsonable_encoder(result),
            "pending": len(pending),
            "state": state,
        }
