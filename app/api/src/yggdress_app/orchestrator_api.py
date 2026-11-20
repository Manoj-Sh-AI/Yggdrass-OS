"""Yggdras's HTTP surface: requests (streamed), approval cards, Undo, the feedback page's data,
notifications, devices and calls.

- Requests from chat, voice, mobile and notification replies all enter `intake` and run the
  orchestration pipeline; the reply streams back as server-sent events.
- Cards (risky actions and offered facts) are held in process memory keyed to the session,
  never stored server-side; Approve re-sends the action with preview:false. A restart expires
  them (the card says so). Brain changes go only through the brain HTTP API.
- Runs and Manoj's reactions are logged in the app database (Phase 4), never in the brain.
- Every open window holds one event stream (`/v1/yggdras/events`): cards, notifications and
  calls ring there; registered phones get a push.
"""

from __future__ import annotations

import json
import queue
import threading
import time
import uuid
from collections import OrderedDict
from datetime import UTC, datetime, timedelta
from html import escape

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field

from . import voice
from .agent_effects import drive
from .agent_orchestrator import Yggdras
from .agent_tools import Proposal
from .orchestration import Checker, intake
from .orchestration_host import Host
from .skill_registry import registry
from .tool_gate import Toolbelt, default_registry

CARD_TTL = timedelta(minutes=30)
MAX_CARDS = 50
RING_SECONDS = 45
STREAM_LIMIT = 240  # seconds a request may stay silent before its stream closes


# ---------------------------------------------------------------- the event hub (Phase 5)


class Hub:
    """Fan-out to every open window. Each subscriber is one browser tab or desktop window."""

    def __init__(self):
        self._lock, self._subs = threading.Lock(), {}

    def subscribe(self) -> tuple[str, queue.Queue]:
        sid, q = uuid.uuid4().hex, queue.Queue(maxsize=200)
        with self._lock:
            self._subs[sid] = q
        return sid, q

    def unsubscribe(self, sid: str) -> None:
        with self._lock:
            self._subs.pop(sid, None)

    def publish(self, event: dict) -> int:
        with self._lock:
            subs = list(self._subs.values())
        for q in subs:
            try:
                q.put_nowait(event)
            except queue.Full:
                pass
        return len(subs)


# ---------------------------------------------------------------- cards held in the session


class Cards:
    """Cards per session, in memory only (bounded, expiring): the preview is never stored."""

    def __init__(self):
        self._lock, self._by_session = threading.Lock(), {}
        self.last_undo: dict[str, dict] = {}

    def add(self, session: str, card: dict) -> dict:
        card = {**card, "id": uuid.uuid4().hex[:12],  # unique across a session's requests
                "created": datetime.now(UTC).isoformat()}  # fmt: skip
        with self._lock:
            cards = self._by_session.setdefault(session, OrderedDict())
            cards[card["id"]] = card
            while len(cards) > MAX_CARDS:
                cards.popitem(last=False)
        return card

    def waiting(self, session: str) -> list[dict]:
        cutoff = (datetime.now(UTC) - CARD_TTL).isoformat()
        with self._lock:
            cards = self._by_session.get(session, OrderedDict())
            for key in [k for k, c in cards.items() if c["created"] < cutoff]:
                del cards[key]
            return [c for c in cards.values() if c["state"] == "waiting"]

    def take(self, session: str, card_id: str) -> dict:
        with self._lock:
            card = self._by_session.get(session, {}).get(card_id)
            if card is None:
                raise HTTPException(404, "This card expired or belongs to another session. "
                                         "Ask Yggdras again.")  # fmt: skip
            if card["state"] != "waiting":
                raise HTTPException(409, f"This card was already {card['state']}.")
            card["state"] = "deciding"
            return card

    def settle(self, card: dict, state: str) -> None:
        with self._lock:
            card["state"] = state


def shape(card: dict) -> dict:
    """What the chat card shows: exactly what changes, and a plain warning if it is final."""
    tool, values = card.get("tool", ""), card.get("input") or {}
    view = {"id": card["id"], "tool": tool, "reasons": card.get("reasons", []),
            "offer": bool(card.get("offer")), "state": card["state"], "old_text": None,
            "new_text": None, "links_added": [], "links_removed": [], "warning": "",
            "title": tool.replace("_", " ")}  # fmt: skip
    preview = card.get("preview") or {}
    if tool == "offer_brain_fact":
        view.update(title=f"File in {values.get('slug')}", new_text=values.get("fact"))
    elif tool == "propose_brain_change":
        view.update(title=f"Change {values.get('slug')}", old_text=values.get("old_line"),
                    new_text=values.get("new_line") or None,
                    links_added=preview.get("links_added", []),
                    links_removed=preview.get("links_removed", []))  # fmt: skip
        if not values.get("new_line"):
            view["warning"] = "This removes the line for good. It cannot be undone."
    elif tool == "send_email":
        view.update(title=f"Send email to {values.get('to')}",
                    new_text=f"Subject: {values.get('subject')}\n\n{values.get('body')}",
                    warning="Once sent, an email cannot be unsent.")  # fmt: skip
    elif tool.startswith("propose_"):
        view.update(title=values.get("explanation") or "Change", new_text=json.dumps(
            values.get("data", {}), ensure_ascii=False, indent=1))  # fmt: skip
    return view


# ---------------------------------------------------------------- bodies


class Ask(BaseModel):
    text: str = Field(min_length=1, max_length=12000)
    source: str = Field(default="chat", pattern="^(chat|voice|mobile)$")
    history: list[dict] = Field(default_factory=list, max_length=12)


class Decision(BaseModel):
    correction: str = Field(default="", max_length=2000)


class Device(BaseModel):
    platform: str = Field(pattern="^(android|ios|web)$")
    push_token: str = Field(min_length=1, max_length=4096)
    label: str = Field(default="", max_length=100)


class Reply(BaseModel):
    reply: str = Field(min_length=1, max_length=4000)


class Ring(BaseModel):
    reason: str = Field(default="", max_length=300)


class Answer(BaseModel):
    device: str = Field(min_length=1, max_length=100)


class End(BaseModel):
    summary: str = Field(default="", max_length=4000)


class Switch(BaseModel):
    enabled: bool


class Schedule(BaseModel):
    at: datetime | None = None
    minutes: int | None = Field(default=None, ge=1, le=240)
    reason: str = Field(default="", max_length=300)


# ---------------------------------------------------------------- the routers


class Yggdrass:
    """Everything the routes share; built once per application."""

    def __init__(self, database, notes, model, tools, *, pusher=None, sensitive=lambda: set()):
        self.database, self.notes, self.model, self.app_tools = database, notes, model, tools
        self.hub, self.cards = Hub(), Cards()
        self.pusher = pusher or voice.SimulatedPusher()
        self.sensitive, self.skills, self.registry = sensitive, registry(), default_registry()
        from . import connector_mcp
        from .connector_auth import Auth, Vault
        from .connector_directory import APPS
        from .connectors import Catalog, default_path, mcp_lister

        self.catalog = Catalog(default_path(), self.registry, mcp_lister, apps=APPS,
                               auth=Auth(Vault()), mcp_list=connector_mcp.list_tools,
                               mcp_call=connector_mcp.call_tool)  # fmt: skip
        self.connector_issue = ""
        try:
            self.catalog.refresh()  # enabled connectors' tools, under their skill domains
        except Exception as exc:  # noqa: BLE001 - a broken connector never stops Yggdras
            self.connector_issue = str(exc)[:300]

    # -- one request through the pipeline

    def run(self, session: str, source: str, payload: dict, emit=lambda e: None):
        started = time.monotonic()
        run_id = uuid.uuid4()
        request = intake(source, payload)
        handlers = {**self.catalog.handlers(), "search_brain": self.search_brain}
        host = Host(self.skills, self.registry, handlers=handlers,
                    on_card=lambda card: self._card(session, card, emit),
                    lessons=self.lessons)  # fmt: skip
        ygg = Yggdras(self.model, host, _Lia(self.notes))
        steps = ygg.handle(request, skills=self.skills,
                           belt_for=lambda: Toolbelt(self.registry, self.skills),
                           checker=Checker(self.sensitive()))  # fmt: skip
        emit({"stage": "intake", "source": source})
        error = ""
        try:
            out = drive(steps, self.model, host, _Lia(self.notes))
        except Exception as exc:  # noqa: BLE001 - the user sees a plain message, never a trace
            out, error = None, str(exc)[:500] or "Yggdras could not finish this request."
        record = host.runs[0] if host.runs else {}
        usage = record.get("usage", [])
        with self.database.connect() as db:
            db.execute(
                "INSERT INTO app.yggdras_runs(id,source,request,route,plan,steps,usage,cost_usd,"
                "latency_ms,checker_stopped,cards,error) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (run_id, source, request.text[:4000], record.get("route") or "multi",
                 Jsonb(record.get("plan")), Jsonb(record.get("steps", [])), Jsonb(usage),
                 round(sum(u["cost"] for u in usage), 6),
                 int((time.monotonic() - started) * 1000), bool(record.get("checker_stopped")),
                 len(host.cards), error),
            )  # fmt: skip
        for card in host.cards:
            card["run_id"] = str(run_id)
        return out, error, run_id

    def _card(self, session: str, card: dict, emit) -> dict:
        if card["tool"] == "propose_brain_change":  # the preview comes from the brain API
            v = card["input"]
            op = "replace-fact" if v.get("new_line") else "remove-fact"
            body = {"preview": True, "old_line": v["old_line"], "line": v["old_line"],
                    "new_line": v.get("new_line", "")}  # fmt: skip
            card["preview"] = self.notes.http.call("POST", f"note/{v['slug']}/{op}", body)
        held = self.cards.add(session, card)
        emit({"card": shape(held)})
        self.hub.publish({"type": "card", "card": shape(held)})
        return held

    def search_brain(self, values: dict) -> dict:
        from urllib.parse import quote

        found = self.notes.http.call("GET", "search?q=" + quote(values["query"]))
        hidden = self.sensitive()
        return {"hits": [n["slug"] for n in found or [] if n["slug"] not in hidden][:5]}

    def lessons(self, source: str) -> list[str]:
        with self.database.connect() as db:
            rows = db.execute(
                "SELECT tool, correction FROM app.yggdras_feedback WHERE decision='rejected' "
                "AND correction<>'' ORDER BY created_at DESC LIMIT 8"
            ).fetchall()
        return [f"{r['tool']}: {r['correction']}" for r in rows]

    # -- approving a card: the action itself

    def execute(self, session: str, card: dict) -> dict:
        tool, v = card["tool"], card["input"]
        if tool == "offer_brain_fact":
            out = self.notes.http.call("POST", f"note/{v['slug']}/add-fact", {"line": v["fact"]})
            self.cards.last_undo[session] = {"undo_id": out["undo_id"], "what": card["id"]}
            return {"done": True, "undo": True}
        if tool == "propose_brain_change":
            op = "replace-fact" if v.get("new_line") else "remove-fact"
            body = {"preview": False, "old_line": v["old_line"], "line": v["old_line"],
                    "new_line": v.get("new_line", "")}  # fmt: skip
            out = self.notes.http.call("POST", f"note/{v['slug']}/{op}", body)
            if out.get("undo_id"):
                self.cards.last_undo[session] = {"undo_id": out["undo_id"], "what": card["id"]}
            return {"done": True, "undo": bool(out.get("undo_id"))}
        if tool in ("propose_tasks_change", "propose_calendar_change", "propose_task_change"):
            proposal = Proposal.model_validate(v)
            with self.database.connect() as db:
                result = self.app_tools.execute(proposal, uuid.uuid4(), db)
            return {"done": True, "undo": False, "result": result}
        if self.catalog.owns(tool):  # a connected app's write, approved by Manoj just now
            from .connector_auth import AuthError
            from .connector_mcp import MCPError

            try:
                out = self.catalog.call(tool, v)
            except (AuthError, MCPError) as exc:
                raise HTTPException(502, str(exc)) from None
            if out["error"]:
                raise HTTPException(502, out["text"][:500] or "The app refused the change.")
            return {"done": True, "undo": False, "result": out["text"][:2000]}
        if tool == "send_email":
            raise HTTPException(409, "No email connector is switched on, so nothing was sent.")
        raise HTTPException(409, "This action is not connected yet; nothing changed.")

    def feedback(self, card: dict, decision: str, correction: str = "") -> None:
        with self.database.connect() as db:
            db.execute(
                "INSERT INTO app.yggdras_feedback(run_id,card_id,tool,decision,correction) "
                "VALUES (%s,%s,%s,%s,%s)",
                (card.get("run_id"), card["id"], card["tool"], decision, correction),
            )

    # -- notifications (Phase 5)

    def notify(self, kind: str, title: str, body: str, dedupe: str, **when) -> bool:
        now = datetime.now(UTC).astimezone()
        with self.database.connect() as db:
            recent = db.execute("SELECT count(*) AS n FROM app.notifications WHERE "
                                "created_at > now() - interval '1 hour'").fetchone()["n"]  # fmt: skip
            duplicate = db.execute("SELECT 1 FROM app.notifications WHERE dedupe_key=%s",
                                   (dedupe,)).fetchone() is not None  # fmt: skip
            verdict = voice.focused(
                kind, now=now, sent_last_hour=recent, duplicate=duplicate, **when
            )
            if not verdict.send:
                return False
            nid = uuid.uuid4()
            db.execute("INSERT INTO app.notifications(id,kind,title,body,dedupe_key) VALUES "
                       "(%s,%s,%s,%s,%s)", (nid, kind, title[:120], body[:500], dedupe))  # fmt: skip
            devices = db.execute("SELECT * FROM app.devices ORDER BY created_at").fetchall()
        message = {"id": str(nid), "kind": kind, "title": title, "body": body}
        self.hub.publish({"type": "notification", **message})
        for device in devices:
            try:
                self.pusher.send(dict(device), message)
            except voice.PushNotConfigured:
                pass  # e.g. an iPhone before CallKit exists; the open windows still got it
        return True

    # -- calls (Phase 6)

    def ring(self, reason: str, direction: str = "outbound") -> dict:
        call = {"id": str(uuid.uuid4()), "room": f"yggdras-{uuid.uuid4().hex[:10]}",
                "reason": reason, "direction": direction}  # fmt: skip
        with self.database.connect() as db:
            db.execute("INSERT INTO app.calls(id,direction,reason,room) VALUES (%s,%s,%s,%s)",
                       (call["id"], direction, reason, call["room"]))  # fmt: skip
        if direction == "outbound":
            self.hub.publish({"type": "call", "state": "ringing", **call})
            self.notify("call", "Yggdras is calling", reason, f"call:{call['id']}")
        return call


class _Lia:
    """Lia, reached only through the brain HTTP API's search (no brain tables)."""

    def __init__(self, notes):
        self.notes = notes

    def ask(self, question, **_):
        from urllib.parse import quote

        hits = self.notes.http.call("GET", "search?q=" + quote(question[:200])) or []
        return (
            "Notes that match: " + ", ".join(n["title"] for n in hits[:5])
            if hits
            else "No notes match."
        )


CALLBACK = "/api/backend/connectors/callback"  # the web proxy forwards it to /v1/connectors


def _page(title: str, text: str, status: int = 200) -> HTMLResponse:
    """A plain page for the browser tab that finished a sign-in. Never shows a token."""
    return HTMLResponse(
        "<!doctype html><meta charset='utf-8'><meta name='viewport' content='width=device-"
        "width'><title>Yggdras</title><body style='font-family:system-ui;background:#232b2d;"
        "color:#f6f5ed;display:grid;place-items:center;min-height:90vh;margin:0'><main "
        "style='max-width:440px;padding:28px;border:1px solid #eef2e538;border-radius:20px;"
        f"background:#202223'><h1 style='font-weight:400'>{escape(title)}</h1><p style="
        f"'color:#cbd2cc;line-height:1.6'>{escape(text)}</p></main>",
        status_code=status,
    )


def sse(event: dict) -> bytes:
    return f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n".encode()


def yggdras_routers(state: Yggdrass, session) -> list[APIRouter]:
    r = APIRouter(prefix="/v1/yggdras")
    calls = APIRouter(prefix="/v1/calls")
    callback = APIRouter(prefix="/v1/connectors")
    authenticated = Depends(session)

    def key(request: Request) -> str:
        return request.cookies.get("yggdress_session", "")[:200] or "default"

    @r.post("/requests")
    def ask(body: Ask, request: Request, _=authenticated):
        events: queue.Queue = queue.Queue()
        sess = key(request)

        def work():
            try:
                out, error, run_id = state.run(sess, body.source, {"content": body.text,
                    "transcript": body.text, "text": body.text, "history": body.history},
                    events.put)  # fmt: skip
                if out is not None:
                    for i in range(0, len(out.answer), 80):  # the reply, streamed in pieces
                        events.put({"delta": out.answer[i : i + 80]})
                    events.put({"done": str(run_id), "route": out.route})
                else:
                    events.put({"error": error, "done": str(run_id)})
            except Exception as exc:  # noqa: BLE001 - the stream must always end, never hang
                events.put({"error": "Yggdras could not finish this request "
                            f"({type(exc).__name__}).", "done": ""})  # fmt: skip
            finally:
                events.put(None)

        threading.Thread(target=work, daemon=True).start()

        def stream():
            while True:
                try:
                    event = events.get(timeout=STREAM_LIMIT)
                except queue.Empty:  # a stuck step never holds the page open forever
                    yield sse({"error": "Yggdras took too long; nothing more will arrive."})
                    return
                if event is None:
                    return
                yield sse(event)

        return StreamingResponse(stream(), media_type="text/event-stream")

    @r.get("/cards")
    def cards(request: Request, _=authenticated):
        return [shape(c) for c in state.cards.waiting(key(request))]

    @r.post("/cards/{card_id}/approve")
    def approve(card_id: str, request: Request, _=authenticated):
        card = state.cards.take(key(request), card_id)
        try:
            out = state.execute(key(request), card)
        except Exception:
            state.cards.settle(card, "waiting")
            raise
        state.cards.settle(card, "approved")
        state.feedback(card, "approved")
        return {**out, "card": shape(card)}

    @r.post("/cards/{card_id}/reject")
    def reject(card_id: str, body: Decision, request: Request, _=authenticated):
        card = state.cards.take(key(request), card_id)
        state.cards.settle(card, "rejected")
        state.feedback(card, "rejected", body.correction)
        return {"rejected": True}

    @r.post("/undo")
    def undo(request: Request, _=authenticated):
        last = state.cards.last_undo.pop(key(request), None)
        if last is None:
            raise HTTPException(404, "Nothing to undo in this session.")
        out = state.notes.http.call("POST", f"undo/{last['undo_id']}", {})
        with state.database.connect() as db:
            db.execute("INSERT INTO app.yggdras_feedback(card_id,tool,decision) VALUES "
                       "(%s,'undo','undone')", (last["what"],))  # fmt: skip
        return {"undone": True, **(out or {})}

    @r.get("/runs")
    def runs(_=authenticated):
        with state.database.connect() as db:
            rows = db.execute("SELECT r.*, (SELECT json_agg(json_build_object('tool',f.tool,"
                              "'decision',f.decision,'correction',f.correction)) FROM "
                              "app.yggdras_feedback f WHERE f.run_id=r.id) AS reactions FROM "
                              "app.yggdras_runs r ORDER BY created_at DESC LIMIT 100").fetchall()  # fmt: skip
        return [dict(row) for row in rows]

    @r.get("/events")
    def events(_=authenticated):
        sid, q = state.hub.subscribe()

        def stream():
            try:
                yield sse({"type": "hello"})
                while True:
                    try:
                        yield sse(q.get(timeout=25))
                    except queue.Empty:
                        yield b": keep-alive\n\n"
            finally:
                state.hub.unsubscribe(sid)

        return StreamingResponse(stream(), media_type="text/event-stream")

    @r.post("/devices")
    def device(body: Device, _=authenticated):
        with state.database.connect() as db:
            db.execute("INSERT INTO app.devices(id,platform,push_token,label) VALUES "
                       "(%s,%s,%s,%s) ON CONFLICT (platform,push_token) DO UPDATE SET "
                       "last_seen_at=now(), label=EXCLUDED.label",
                       (uuid.uuid4(), body.platform, body.push_token, body.label))  # fmt: skip
        return {"registered": True}

    @r.post("/notifications/{notification_id}/reply")
    def reply(notification_id: str, body: Reply, request: Request, _=authenticated):
        out, error, run_id = state.run(key(request), "notification",
                                       {"reply": body.reply, "notification_id": notification_id})  # fmt: skip
        if out is None:
            raise HTTPException(502, error)
        return {"answer": out.answer, "run": str(run_id), "cards": len(out.cards)}

    @r.get("/connectors")
    def connectors(_=authenticated):
        return state.catalog.view()

    @r.get("/skills")
    def skills(_=authenticated):
        """The skill catalog: frontmatter only, the same cards Yggdras sees before loading."""
        return [{"name": c.name, "description": c.description, "domains": list(c.domains)}
                for _n, c in sorted(state.skills.cards.items())]  # fmt: skip

    @r.get("/skills/{name}")
    def skill(name: str, _=authenticated):
        """One skill with its instructions. Read-only: skills change through pull requests."""
        card = state.skills.cards.get(name)
        if card is None:
            raise HTTPException(404, f"No skill named {name!r}.")
        # Read the file directly so a person browsing does not count as a task loading it.
        text = card.path.read_text(encoding="utf-8").split("---", 2)[2].strip()
        return {"name": card.name, "description": card.description,
                "domains": list(card.domains), "instructions": text}  # fmt: skip

    @r.post("/connectors/{name}")
    def switch(name: str, body: Switch, _=authenticated):
        from .connectors import ConnectorError

        try:
            return state.catalog.switch(name, body.enabled)
        except ConnectorError as exc:
            raise HTTPException(409, str(exc)) from None

    @r.post("/connectors/{name}/connect")
    def connect(name: str, request: Request, _=authenticated):
        """The address to open for signing in to one app. The laptop only (mobile gate)."""
        from .connector_auth import AuthError
        from .connectors import ConnectorError

        origin = request.headers.get("origin", "").rstrip("/")
        if not origin.startswith(("http://127.0.0.1", "http://localhost", "https://")):
            raise HTTPException(400, "Open Connectors from the Yggdras app to connect.")
        try:
            url = state.catalog.connect_url(name, f"{origin}{CALLBACK}")
        except (AuthError, ConnectorError) as exc:
            raise HTTPException(409, str(exc)) from None
        return {"authorize_url": url}

    @r.post("/connectors/{name}/disconnect")
    def disconnect(name: str, _=authenticated):
        from .connectors import ConnectorError

        try:
            return state.catalog.disconnect(name)
        except ConnectorError as exc:
            raise HTTPException(409, str(exc)) from None

    @callback.get("/callback", response_class=HTMLResponse)
    def returned(state_: str = Query("", alias="state"), code: str = "", error: str = ""):
        """Where the app sends Manoj back after sign-in. No session cookie reaches here (it
        often opens in the system browser), so the one-time `state` is the proof."""
        from .connector_auth import AuthError
        from .connector_mcp import MCPError

        if error or not code:
            return _page("Not connected", "The sign-in was cancelled or refused. Nothing "
                         "was saved. Return to Yggdras and try again.", 400)  # fmt: skip
        try:
            view = state.catalog.connected(state_, code)
        except AuthError as exc:
            return _page("Not connected", str(exc), 400)
        except MCPError as exc:
            return _page("Signed in, but", f"{exc} Try switching the app on again later.", 502)
        return _page(f"{view['title']} is connected",
                     f"Yggdras can now use {view['tool_count']} of its tools. Anything that "
                     "changes data still waits for your approval. You can close this tab.")  # fmt: skip

    @calls.post("")
    def call_yggdras(_=authenticated):
        """Manoj calls Yggdras: a call record and room access for this client."""
        call = state.ring("Manoj called", "inbound")
        access = voice.join("manoj", call["room"])
        return {**call, "url": access.url, "token": access.token, "simulated": access.simulated}

    @calls.post("/ring")
    def ring(body: Ring, _=authenticated):
        return state.ring(body.reason or "Check-in")

    @calls.post("/{call_id}/answer")
    def answer(call_id: str, body: Answer, _=authenticated):
        with state.database.connect() as db:
            row = db.execute("UPDATE app.calls SET state='answered',answered_by=%s,answered_at=now() "
                             "WHERE id=%s AND state='ringing' AND created_at > now() - %s "
                             "RETURNING room", (body.device, call_id,
                             timedelta(seconds=RING_SECONDS))).fetchone()  # fmt: skip
        if row is None:
            raise HTTPException(409, "Another device answered, or the call ended.")
        state.hub.publish({"type": "call", "state": "answered", "id": call_id,
                           "answered_by": body.device})  # the others stop ringing  # fmt: skip
        access = voice.join("manoj", row["room"])
        return {"url": access.url, "token": access.token, "simulated": access.simulated}

    @calls.post("/{call_id}/decline")
    def decline(call_id: str, _=authenticated):
        with state.database.connect() as db:
            db.execute("UPDATE app.calls SET state='declined',ended_at=now() WHERE id=%s AND "
                       "state='ringing'", (call_id,))  # fmt: skip
        state.hub.publish({"type": "call", "state": "declined", "id": call_id})
        return {"declined": True}

    @calls.post("/{call_id}/end")
    def end(call_id: str, body: End, _=authenticated):
        with state.database.connect() as db:
            db.execute("UPDATE app.calls SET state='ended',ended_at=now(),summary=%s WHERE id=%s "
                       "AND state='answered'", (body.summary, call_id))  # fmt: skip
        state.hub.publish({"type": "call", "state": "ended", "id": call_id})
        return {"ended": True}

    @calls.post("/schedule")
    def schedule(body: Schedule, _=authenticated):
        """ "Call me at 6pm" (at) or "give me 5 minutes" (minutes)."""
        if (body.at is None) == (body.minutes is None):
            raise HTTPException(422, "Give either a time or a number of minutes.")
        due = body.at or datetime.now(UTC) + timedelta(minutes=body.minutes)
        kind = "one_off" if body.at else "snooze"
        with state.database.connect() as db:
            sid = db.execute("INSERT INTO app.call_schedules(id,kind,due_at,reason) VALUES "
                             "(%s,%s,%s,%s) RETURNING id", (uuid.uuid4(), kind, due,
                             body.reason)).fetchone()["id"]  # fmt: skip
        return {"scheduled": str(sid), "due_at": due.isoformat(), "kind": kind}

    @calls.get("")
    def history(_=authenticated):
        with state.database.connect() as db:
            rows = db.execute("SELECT id,direction,reason,state,summary,created_at,answered_at,"
                              "ended_at FROM app.calls ORDER BY created_at DESC LIMIT 50").fetchall()  # fmt: skip
        return [dict(row) for row in rows]

    # The durable, device-bound call service owns /calls. Keep these legacy
    # handlers unreachable so no client can bypass its lifecycle protections.
    return [r, callback]


def due_rings(state: Yggdrass) -> int:
    """Ring every schedule that is due, once (the scheduler's tick; Temporal calls it)."""
    with state.database.connect() as db:
        rows = db.execute("UPDATE app.call_schedules SET state='rung' WHERE state='pending' AND "
                          "due_at <= now() RETURNING reason").fetchall()  # fmt: skip
        db.execute("UPDATE app.calls SET state='missed',ended_at=now() WHERE state='ringing' AND "
                   "created_at < now() - %s", (timedelta(seconds=RING_SECONDS),))  # fmt: skip
    for row in rows:
        state.ring(row["reason"] or "Your scheduled check-in")
    return len(rows)
