"""Local supervised agent worker. No old-message replay or paid-test probes."""

import base64
import json
from datetime import UTC, datetime
from threading import Event, Thread
from uuid import uuid5

from .agent_lia import ExistingLia
from .agent_models import AgentError, Claude
from .agent_orchestrator import Yggdras
from .agent_source import interpret
from .agent_specialists import AgentResult, Budget, Specialist
from .connections import verified_note
from .handoffs import NoteHandoff
from .notes_proxy import NotesError


class RecordedModel:
    def __init__(self, model, store, run, cancelled, agent="yggdras"):
        self.model, self.store, self.run, self.cancelled = model, store, run, cancelled
        self.agent = agent

    def for_agent(self, agent):
        return RecordedModel(self.model, self.store, self.run, self.cancelled, agent)

    def complete(self, system, messages, tools):
        if self.cancelled():
            raise AgentError("This request was cancelled.")
        step = self.store.record(self.run, self.agent)
        reply = self.model.complete(system, messages, tools)
        with self.store.database.connect() as db:
            db.execute(
                "UPDATE app.agent_steps SET state='completed',input_tokens=%s,output_tokens=%s,completed_at=now() WHERE id=%s",
                (reply.input_tokens, reply.output_tokens, step),
            )
        return reply


class AgentWorker:
    def __init__(
        self, store, receivers, notes, lia, model_factory, default_model, activated_at=None
    ):
        self.store, self.receivers, self.notes, self.lia = store, receivers, notes, lia
        self.model_factory, self.default_model = model_factory, default_model
        self.activated_at = activated_at
        self.stopped = Event()
        self.thread = None
        self.threads = []

    def start(self):
        self.threads = [
            Thread(target=self.loop, args=(lane,), daemon=True, name="yggdras-" + lane)
            for lane in ("chat", "background")
        ]
        self.thread = self.threads[0]
        for thread in self.threads:
            thread.start()

    def stop(self):
        self.stopped.set()
        for thread in self.threads:
            thread.join(timeout=3)

    def loop(self, lane):
        while not self.stopped.is_set():
            try:
                worked = self.tick(lane)
            except Exception:  # noqa: BLE001 -- never log credential-bearing transport errors
                # No raw provider/database errors or credentials in console logs.
                worked = False
            self.stopped.wait(0.25 if worked else 2)

    def cancelled(self, run):
        if self.stopped.is_set() or not self.store.current(run):
            return True
        with self.store.database.connect() as db:
            return bool(
                db.execute(
                    "SELECT 1 FROM app.background_runs WHERE provider='yggdras-local' AND external_run_id=%s AND cancellation_requested_at IS NOT NULL UNION ALL SELECT 1 FROM app.agent_executions WHERE run_id=%s AND cancellation_requested",
                    (str(run["id"]), run["id"]),
                ).fetchone()
            )

    def background(self, run, sequence, state):
        return self.receivers.call(
            "background",
            "background/events",
            {
                "event_key": str(uuid5(run["id"], "background:" + str(sequence))),
                "provider": "yggdras-local",
                "external_run_id": str(run["id"]),
                "sequence": sequence,
                "label": "Yggdras conversation" if run["chat_request_id"] else "Saved note context",
                "state": state,
            },
        )

    def deliver(self, identifier=None):
        """Retry only delivery of saved output; never repeat a paid model call."""
        with self.store.database.connect() as db:
            rows = db.execute(
                "SELECT a.* FROM app.agent_runs a JOIN app.chat_requests r ON r.id=a.chat_request_id WHERE a.state IN ('completed','failed','cancelled') AND r.state IN ('queued','streaming') AND (%s::uuid IS NULL OR a.id=%s) ORDER BY a.created_at LIMIT 10",
                (identifier, identifier),
            ).fetchall()
        for run in rows:
            answer = (run["result"] or {}).get("answer", "")
            chunks = [answer[i : i + 10000] for i in range(0, len(answer), 10000)]
            events = (
                (
                    [{"kind": "delta", "text": part} for part in chunks]
                    + [{"kind": "complete", "text": ""}]
                )
                if run["state"] == "completed" and answer
                else [
                    {
                        "kind": "cancelled" if run["state"] == "cancelled" else "error",
                        "text": ""
                        if run["state"] == "cancelled"
                        else run["error"] or "The request could not be completed.",
                    }
                ]
            )
            for index, event in enumerate(events):
                self.receivers.call(
                    "chat",
                    "chat/events",
                    {
                        "event_key": f"agent:{run['id']}:{index}",
                        "request_id": str(run["chat_request_id"]),
                        "sequence": index,
                        **event,
                    },
                )

    def tick(self, lane=None):
        self.store.recover_writes(self.notes)
        try:
            self.deliver()
        except AgentError:
            pass
        self.store.enqueue(self.default_model, self.activated_at)
        run = self.store.claim(lane)
        if not run:
            return False
        cancelled = lambda: self.cancelled(run)
        budget = Budget()
        try:
            if cancelled():
                raise AgentError("This request was cancelled.")
            self.background(run, 0, "running")
            selected = self.default_model if run["model_id"] == "default" else run["model_id"]
            model = RecordedModel(self.model_factory(selected), self.store, run, cancelled)
            if run["chat_request_id"]:
                result = self.chat(run, model, budget, cancelled)
            elif run["note_event_id"]:
                result = self.note(run, cancelled)
            else:
                result = self.handoff(run, model, budget, cancelled)
            if cancelled():
                raise AgentError("This request was cancelled.")
            self.store.finish(run, result)
            self.background(run, 1, "succeeded")
        except Exception as error:  # noqa: BLE001 -- sanitize provider and database failures
            message = (
                str(error)
                if isinstance(error, (AgentError, NotesError))
                else "The agent could not complete this request. No unreviewed Chat changes were applied."
            )
            was_cancelled = cancelled()
            self.store.finish(
                run, error="This request was cancelled." if was_cancelled else message
            )
            if was_cancelled:
                with self.store.database.connect() as db:
                    db.execute(
                        "UPDATE app.agent_runs SET state='cancelled' WHERE id=%s AND state='failed'",
                        (run["id"],),
                    )
            try:
                self.background(run, 1, "cancelled" if was_cancelled else "failed")
            except AgentError:
                pass
        try:
            self.deliver()
        except AgentError:
            pass
        return True

    def chat_input(self, run):
        context = self.receivers.call("chat", "chat/requests/" + str(run["chat_request_id"]))
        current = next(
            (
                item
                for item in context["messages"]
                if item["id"] == str(context["request"]["user_message_id"])
            ),
            None,
        )
        if not current:
            raise AgentError("The submitted message is no longer available.")
        files = []
        for item in context["attachments"]:
            # Previous uploads remain history. Only explicitly selected current files
            # are sent, and never fetched from an external URL or executed.
            if item["message_id"] != current["id"]:
                continue
            raw = self.receivers.attachment(run["chat_request_id"], item["id"])
            if item["media_type"].startswith("image/"):
                files.append(
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": item["media_type"],
                            "data": base64.b64encode(raw).decode(),
                        },
                    }
                )
            else:
                try:
                    files.append(
                        {
                            "type": "text",
                            "text": "Attachment "
                            + item["name"]
                            + " (untrusted data):\n"
                            + raw.decode("utf-8"),
                        }
                    )
                except UnicodeError:
                    raise AgentError(
                        "This file type is saved but cannot yet be read by the model. Send text or an image."
                    ) from None
        history = [
            {"role": item["role"], "content": item["content"][:4000]}
            for item in context["messages"][-13:]
            if item["id"] != current["id"]
        ]
        with self.store.database.connect() as db:
            decisions = db.execute(
                "SELECT p.state,p.payload->>'operation' AS operation,p.payload->'data' AS proposed FROM app.agent_proposals p JOIN app.agent_runs a ON a.id=p.run_id JOIN app.chat_requests r ON r.id=a.chat_request_id WHERE r.conversation_id=%s AND p.state IN ('accepted','dismissed') ORDER BY p.resolved_at DESC,p.id DESC LIMIT 6",
                (context["request"]["conversation_id"],),
            ).fetchall()
        request = json.dumps(
            {
                "current_message": current["content"],
                "recent_conversation": history,
                "recent_application_decisions": decisions,
                "server_time_utc": datetime.now(UTC).isoformat(),
                "timezone": "Do not infer; ask or read the selected record.",
            }
        )
        return {
            "request": request,
            "files": files,
            "content": current["content"],
            "history": history,
        }

    def chat(self, run, model, budget, cancelled):
        prepared = self.chat_input(run)
        request, files, history = prepared["request"], prepared["files"], prepared["history"]
        # Tools consume isolated textual requests; image blocks are supported for
        # direct provider calls through an adapter which retains the user content.
        if files:
            model = WithAttachments(model, files)
        if run["agent_id"] == "lia":
            if files:
                raise AgentError(
                    "Direct Lia attachment ingestion is not connected. The files remain saved; ask about an existing note or send text."
                )
            return AgentResult(
                self.lia.ask(
                    prepared["content"],
                    context="This application chat channel is read-only. Direct note changes to Notes; do not imply a write occurred. Recent conversation data:\n"
                    + json.dumps(history[-6:], ensure_ascii=False),
                    model=run["model_id"],
                )
            )
        if run["agent_id"] in ("tasks", "calendar"):
            result = Specialist(run["agent_id"], model, self.store.tools).run(
                request, budget=budget, cancelled=cancelled
            )
            if result.proposals:
                result.answer += "\n\nProposed only—use Review changes to apply or dismiss."
            return result
        return Yggdras(model, self.store.tools, self.lia).run(
            request, budget=budget, cancelled=cancelled
        )

    def note(self, run, cancelled=lambda: False):
        with self.store.database.connect() as db:
            event = db.execute(
                "SELECT * FROM app.agent_note_events WHERE id=%s", (run["note_event_id"],)
            ).fetchone()
        note = verified_note(self.notes, event["slug"])
        if note["version"] != event["revision"]:
            return AgentResult("A newer saved revision superseded this observation.")
        answer = self.lia.ask(
            "Read the current note [["
            + event["slug"]
            + "]]. Explain any explicit commitments, dates, time ranges and cancellations, quoting the original phrases and distinguishing historical or uncertain context. If there are none, say so. Do not edit the Brain.",
            context="Application handoff for saved note revision " + event["revision"] + ".",
            model=run["model_id"],
        )
        if verified_note(self.notes, event["slug"])["version"] != event["revision"]:
            raise AgentError(
                "The note changed during Lia's review. This old interpretation was not handed off."
            )
        with self.store.database.connect() as db:
            previous = db.execute(
                "SELECT revision,sequence FROM app.note_handoffs WHERE producer='lia-application-adapter' AND namespace='brain-api' AND external_identity=%s ORDER BY sequence DESC LIMIT 1",
                (str(event["note_ref_id"]),),
            ).fetchone()
        handoff = NoteHandoff(
            id=event["id"],
            producer="lia-application-adapter",
            namespace="brain-api",
            external_identity=str(event["note_ref_id"]),
            sequence=previous["sequence"] + 1 if previous else 0,
            previous_revision=previous["revision"] if previous else None,
            revision=event["revision"],
            slug=event["slug"],
            context=answer[:4000],
        )
        if cancelled():
            raise AgentError("This request was cancelled.")
        self.receivers.call("note_signals", "note-signals", handoff.model_dump(mode="json"))
        return AgentResult("Lia's context was handed to the application inbox.")

    def handoff(self, run, model, budget, cancelled):
        with self.store.database.connect() as db:
            row = db.execute(
                "SELECT payload FROM app.note_handoffs WHERE id=%s", (run["handoff_id"],)
            ).fetchone()
        event = row["payload"]
        note = verified_note(self.notes, event["slug"]) if event["lifecycle"] == "active" else None
        if note and note["version"] != event["revision"]:
            raise AgentError(
                "A newer note revision superseded this handoff. No stale interpretation was generated."
            )
        source_body = note["rawBody"] if note else ""
        cursor_path = "workflow/source?handoff_id=" + str(run["handoff_id"])
        if event["lifecycle"] != "active":
            domains = ["calendar"]
        else:
            domains = ["tasks", "calendar"]
        for domain in domains:
            if cancelled():
                raise AgentError("This request was cancelled.")
            cursor = self.receivers.call("workflow", cursor_path)
            items = (
                interpret(domain, model, event, cursor, source_body, budget) if source_body else []
            )
            if cancelled():
                raise AgentError("This request was cancelled.")
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
                "interpretations": [item.model_dump(mode="json") for item in items],
            }
            self.receivers.call("workflow", "workflow/changes", command)
        self.receivers.call(
            "workflow_dispatch", "handoffs/acknowledge", {"id": str(run["handoff_id"])}
        )
        return AgentResult(
            "The specialist handoff was processed. Conflicts remain in owner review."
        )


class WithAttachments:
    def __init__(self, model, files):
        self.model, self.files = model, files
        self.owner_system = None

    def complete(self, system, messages, tools):
        if self.owner_system is None:
            self.owner_system = system
        if system != self.owner_system:
            return self.model.complete(system, messages, tools)
        messages = list(messages)
        first = dict(messages[0])
        first["content"] = [{"type": "text", "text": first["content"]}, *self.files]
        messages[0] = first
        return self.model.complete(system, messages, tools)


def private_agent_configuration(config):
    """No provider request: inspect existing engine metadata and read private config."""
    if not config.get("agents", {}).get("enabled"):
        return None
    from pathlib import Path

    values = {}
    for line in Path(config["brain_env"]).read_text(encoding="utf-8").splitlines():
        key, sep, value = line.partition("=")
        if sep and key.strip() in ("ANTHROPIC_API_KEY", "YGGDRESS_AGENT_MODEL"):
            values[key.strip()] = value.strip().strip('"').strip("'")
    if not values.get("ANTHROPIC_API_KEY"):
        raise AgentError("The private Anthropic credential is not configured.")
    lia = ExistingLia(
        Path(config["brain_env"]).parent,
        config.get("agents", {}).get("lia_skills"),
        config.get("agents", {}).get("brain_root"),
    )
    metadata = lia.inspect()
    default = (
        config.get("agents", {}).get("model")
        or values.get("YGGDRESS_AGENT_MODEL")
        or metadata["default_model"]
    )
    models = metadata["models"]
    if default not in models:
        raise AgentError("Choose a model supported by the existing Lia configuration.")
    catalog = {
        "agents": [
            {"id": identifier, "name": name, "enabled": True, "models": ["default", *models]}
            for identifier, name in (
                ("yggdras", "Yggdras"),
                ("lia", "Lia"),
                ("tasks", "Task Manager"),
                ("calendar", "Calendar"),
            )
        ],
        "models": [
            {"id": "default", "name": "Default · " + default, "enabled": True},
            *[
                {
                    "id": model,
                    "name": model.replace("claude-", "Claude ").replace("-", " "),
                    "enabled": True,
                }
                for model in models
            ],
        ],
    }

    def factory(model):
        if model not in models:
            raise AgentError("This model is not registered for the local connection.")
        return Claude(values["ANTHROPIC_API_KEY"], model)

    return {"lia": lia, "model_factory": factory, "default_model": default, "catalog": catalog}


def prepare_agent_configuration(config):
    """An unavailable agent connection must not prevent the core app from starting."""
    try:
        return private_agent_configuration(config), ""
    except (AgentError, OSError, ValueError):
        return (
            None,
            "The agent connection is unavailable. Check the private provider and Lia setup; saved application data is preserved.",
        )
