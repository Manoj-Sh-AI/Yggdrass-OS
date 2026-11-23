"""Durable, authenticated call lifecycle. No Brain queries, audio recordings or secrets in events."""

import hashlib
import json
import os
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse
from psycopg.types.json import Jsonb
from pydantic import Field, field_validator

from . import voice
from .planning_models import Model
from .security import token_hash

LOCK = 719218418


class CallCommand(Model):
    key: UUID
    device: str = Field(min_length=1, max_length=100)


class CallUpdate(CallCommand):
    version: int = Field(ge=1)
    state: str = Field(pattern="^(connected|reconnecting|failed|ended)$")


class Preferences(Model):
    version: int = Field(ge=1)
    scheduled: bool = True
    calendar_starts: bool = True
    calendar_ends: bool = True
    routines: bool = True
    timezone: str = "Europe/Berlin"
    quiet_start: str = Field(default="22:00", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    quiet_end: str = Field(default="08:00", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")

    @field_validator("timezone")
    @classmethod
    def zone(cls, value):
        try:
            ZoneInfo(value)
        except (KeyError, ValueError):
            raise ValueError("Choose a valid named timezone.") from None
        return value


class Schedule(Model):
    key: UUID
    at: datetime | None = None
    minutes: int | None = Field(default=None, ge=1, le=240)


class Device(Model):
    push_token: str = Field(min_length=10, max_length=4096)
    platform: str = Field(default="android", pattern="^android$")
    label: str = Field(default="Android phone", max_length=100)


class Review(Model):
    key: UUID
    version: int = Field(ge=1)
    decision: str = Field(pattern="^(accept|dismiss)$")


def quiet(now, pref):
    local = now.astimezone(ZoneInfo(pref["timezone"])).time().replace(tzinfo=None)
    start, end = pref["quiet_start"], pref["quiet_end"]
    return start == end or (start <= local < end if start < end else local >= start or local < end)


def session_id(auth):
    return token_hash(auth["csrf"])


class CallService:
    def __init__(self, database, *, mode=None, pusher=None, transport=None, now=None, notes=None):
        self.notes = notes
        self.briefs = None  # call_briefs.BriefPreparer, set where a model is configured
        self.auth_fingerprint = ""
        self.database = database
        self.mode = mode or os.environ.get("YGGDRAS_CALLS_MODE", "disabled")
        self.pusher = pusher
        self.transport = transport
        if self.mode == "live" and transport is None:
            from .voice_runtime import LiveKitTransport

            self.transport = LiveKitTransport()
        if self.mode == "live" and pusher is None and not voice.missing(voice.FIREBASE_VARS):
            self.pusher = voice.FcmPusher()
        self.now = now or (lambda: datetime.now(UTC))

    def preferences(self, db):
        db.execute(
            "INSERT INTO app.call_preferences(singleton) VALUES (true) ON CONFLICT DO NOTHING"
        )
        return db.execute("SELECT * FROM app.call_preferences").fetchone()

    def capabilities(self):
        absent = voice.missing(voice.LIVEKIT_VARS + voice.FIREBASE_VARS)
        worker = False
        if self.mode == "live":
            with self.database.connect() as db:
                worker = bool(
                    db.execute(
                        "SELECT 1 FROM app.voice_worker_lease WHERE name='yggdras-voice' AND seen_at>now()-interval '45 seconds'"
                    ).fetchone()
                )
        return {
            "mode": self.mode,
            "simulated": self.mode == "simulated",
            "voice_ready": self.mode == "simulated"
            or (self.mode == "live" and worker and not voice.missing(voice.LIVEKIT_VARS)),
            "push_ready": self.mode == "live" and not voice.missing(voice.FIREBASE_VARS),
            "worker_ready": worker,
            "missing": absent,
            "local_backend_required": True,
        }

    def require_ready(self):
        if not self.capabilities()["voice_ready"]:
            raise HTTPException(
                503,
                "Live calls are off until LiveKit and the voice worker are configured. No call was placed.",
            )

    def event(self, db, row):
        db.execute(
            "INSERT INTO app.call_events(call_id,state) VALUES (%s,%s)", (row["id"], row["state"])
        )
        db.execute(
            "INSERT INTO app.call_delivery(call_id,device_id,event_state) SELECT %s,id,%s FROM app.devices WHERE revoked_at IS NULL AND session_expires_at>%s AND password_fingerprint=%s ON CONFLICT DO NOTHING",
            (row["id"], row["state"], self.now(), self.auth_fingerprint),
        )

    def expire(self, db):
        sessions = {
            token_hash(r["csrf"])
            for r in db.execute(
                "SELECT csrf FROM app.sessions WHERE expires_at>now() AND password_fingerprint=%s",
                (self.auth_fingerprint,),
            ).fetchall()
        }
        for row in db.execute("SELECT * FROM app.calls WHERE state='answered'").fetchall():
            if row["answer_session"] not in sessions:
                ended = db.execute(
                    "UPDATE app.calls SET state='ended',media_state='ended',ended_at=%s,version=version+1 WHERE id=%s AND state='answered' RETURNING *",
                    (self.now(), row["id"]),
                ).fetchone()
                if ended:
                    self.event(db, ended)
        for row in db.execute(
            "UPDATE app.calls SET state='missed',ended_at=%s,version=version+1 WHERE state='ringing' AND expires_at<=%s RETURNING *",
            (self.now(), self.now()),
        ).fetchall():
            self.event(db, row)
            from .call_outcomes import after_missed

            after_missed(db, row, self.now())  # retry twice, then decide the outcome
        for row in db.execute(
            "UPDATE app.calls SET state='ended',media_state='ended',ended_at=%s,version=version+1 WHERE state='answered' AND answered_at<%s RETURNING *",
            (self.now(), self.now() - timedelta(hours=1)),
        ).fetchall():
            self.event(db, row)

    def receipt(self, db, key, payload, operation):
        fingerprint = hashlib.sha256(
            json.dumps(payload, sort_keys=True, default=str).encode()
        ).hexdigest()
        db.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK,))
        old = db.execute("SELECT * FROM app.call_commands WHERE key=%s", (key,)).fetchone()
        if old:
            if old["fingerprint"] != fingerprint:
                raise HTTPException(409, "This command key belongs to another action.")
            return old["response"]
        out = jsonable_encoder(operation())
        # Tokens are minted separately and never persisted in command receipts.
        db.execute(
            "INSERT INTO app.call_commands VALUES (%s,%s,%s,now())", (key, fingerprint, Jsonb(out))
        )
        return out

    def create(self, db, *, direction, key=None, identity="", device="", reason="Yggdras check-in"):
        self.expire(db)
        if db.execute("SELECT 1 FROM app.calls WHERE state IN ('ringing','answered')").fetchone():
            raise HTTPException(409, "A call is already active. End it before starting another.")
        identifier = uuid4()
        row = db.execute(
            "INSERT INTO app.calls(id,room,direction,reason,state,request_key,answer_session,answered_by,answered_at,expires_at,media_state,simulated) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *",
            (
                identifier,
                "yggdras-" + identifier.hex,
                direction,
                reason[:300],
                "answered" if direction == "inbound" else "ringing",
                key,
                identity,
                device,
                self.now() if direction == "inbound" else None,
                self.now() + timedelta(seconds=45),
                "connecting" if direction == "inbound" else "idle",
                self.mode == "simulated",
            ),
        ).fetchone()
        self.event(db, row)
        return row

    def access(self, row, identity, device):
        if (
            row["state"] != "answered"
            or row["answer_session"] != identity
            or row["answered_by"] != device
        ):
            raise HTTPException(409, "This call belongs to another device or has ended.")
        if self.mode == "simulated":
            return {
                "url": "sim://livekit",
                "token": "",
                "room": row["room"],
                "simulated": True,
                "id": str(row["id"]),
            }
        if self.transport:
            try:
                from .routine_voice import dispatch_metadata

                restricted = dispatch_metadata(self.database, row, self.auth_fingerprint)
                if restricted:
                    self.transport.dispatch(str(row["id"]), row["room"], metadata=restricted)
                else:
                    self.transport.dispatch(str(row["id"]), row["room"])
            except Exception:  # noqa: BLE001 -- sanitized transport boundary
                raise HTTPException(
                    503,
                    "The voice worker could not join. End this pending call before retrying.",
                ) from None
        access = voice.join("client-" + token_hash(identity + device)[:24], row["room"])
        return {
            "id": str(row["id"]),
            "url": access.url,
            "token": access.token,
            "room": row["room"],
            "simulated": False,
        }

    def snapshot(self, after=0):
        with self.database.connect() as db:
            self.expire(db)
            events = db.execute(
                "SELECT e.seq,e.call_id,e.state FROM app.call_events e WHERE seq>%s ORDER BY seq LIMIT 100",
                (after,),
            ).fetchall()
            calls = db.execute(
                "SELECT id,state,version,media_state,simulated,expires_at,created_at,answered_by,summary,reason FROM app.calls ORDER BY created_at DESC LIMIT 50"
            ).fetchall()
            return {
                "events": events,
                "cursor": events[-1]["seq"] if events else after,
                "calls": calls,
                "capabilities": self.capabilities(),
            }

    def seed_schedules(self, db, pref):
        from .call_briefs import LEAD
        from .planning import matches, wall_instant

        now = self.now()
        horizon = now + timedelta(days=2)
        candidates = []

        def early(start):
            # Ring LEAD before the start; if that moment passed but it has not started, now.
            return max(start - LEAD, now) if start > now else start - LEAD

        if pref["scheduled"] and (pref["calendar_starts"] or pref["calendar_ends"]):
            rows = db.execute(
                "SELECT id,version,starts_at,ends_at FROM app.calendar_events WHERE NOT cancelled AND ends_at>%s AND starts_at<%s",
                (now - timedelta(minutes=2), horizon),
            ).fetchall()
            for row in rows:
                for enabled, kind, at in [
                    # Starts ring LEAD early with a prepared briefing; ends ring on time.
                    (pref["calendar_starts"], "event_start", early(row["starts_at"])),
                    (pref["calendar_ends"], "event_end", row["ends_at"]),
                ]:
                    if enabled:
                        family = f"auto:{kind}:{row['id']}"
                        candidates.append(
                            (
                                family + f":{row['version']}",
                                family,
                                kind,
                                at,
                                "event",
                                row["id"],
                                row["version"],
                            )
                        )
        if pref["scheduled"] and pref["routines"]:
            for template in db.execute(
                "SELECT * FROM app.routine_templates WHERE active ORDER BY id"
            ).fetchall():
                first = now.astimezone(ZoneInfo(template["timezone"])).date()
                for offset in range(3):
                    day = first + timedelta(days=offset)
                    if not matches(template, day):
                        continue
                    if db.execute(
                        "SELECT 1 FROM app.routine_exceptions WHERE template_id=%s AND occurrence_date=%s",
                        (template["id"], day),
                    ).fetchone():
                        continue
                    task = db.execute(
                        "SELECT id,state FROM app.tasks WHERE template_id=%s AND occurrence_date=%s",
                        (template["id"], day),
                    ).fetchone()
                    if task and task["state"] in ("completed", "skipped", "in_progress"):
                        continue
                    # A marked routine block belongs to the push-first flow for that day.
                    # Otherwise the original call would ring before the owner can tap Started.
                    if (
                        task
                        and db.execute(
                            "SELECT 1 FROM app.routine_important_blocks i JOIN app.execution_blocks b "
                            "ON b.id=i.block_id CROSS JOIN app.daily_routine_settings s WHERE s.enabled "
                            "AND b.task_id=%s AND NOT b.cancelled",
                            (task["id"],),
                        ).fetchone()
                    ):
                        continue
                    block = (
                        db.execute(
                            "SELECT starts_at FROM app.execution_blocks WHERE task_id=%s AND NOT cancelled ORDER BY starts_at LIMIT 1",
                            (task["id"],),
                        ).fetchone()
                        if task
                        else None
                    )
                    try:
                        at = (
                            block["starts_at"]
                            if block
                            else wall_instant(
                                datetime.combine(day, template["window_start"]),
                                template["timezone"],
                            )
                        )
                    except HTTPException:
                        continue
                    start, at = at, early(at)
                    family = f"auto:routine:{template['id']}:{day}"
                    candidates.append(
                        (
                            # Keyed by the real start, so the moving "now" never re-keys it.
                            family + f":{template['version']}:{start.isoformat()}",
                            family,
                            "routine",
                            at,
                            "routine",
                            template["id"],
                            template["version"],
                        )
                    )
        valid = {c[0] for c in candidates if not quiet(c[3], pref)}
        db.execute(
            "UPDATE app.call_schedules SET state='cancelled' WHERE state='pending' AND source_key LIKE 'auto:%'"
        )
        for row in db.execute(
            "SELECT s.source_key,c.* FROM app.call_schedules s JOIN app.calls c ON c.id=s.call_id WHERE s.source_key LIKE 'auto:%' AND c.state='ringing'"
        ).fetchall():
            if row["source_key"] not in valid:
                ended = db.execute(
                    "UPDATE app.calls SET state='ended',media_state='ended',ended_at=%s,version=version+1 WHERE id=%s RETURNING *",
                    (now, row["id"]),
                ).fetchone()
                self.event(db, ended)
        for key, family, kind, at, source_type, source_id, revision in candidates:
            if not now - timedelta(minutes=2) < at <= horizon or quiet(at, pref):
                continue
            if db.execute(
                "SELECT 1 FROM app.call_schedules WHERE state='rung' AND due_at=%s AND (source_key=%s OR source_key LIKE %s)",
                (at, family, family + ":%"),
            ).fetchone():
                continue
            db.execute(
                "INSERT INTO app.call_schedules(id,kind,due_at,reason,source_key,source_type,source_id,source_revision) VALUES (%s,%s,%s,'Scheduled check-in',%s,%s,%s,%s) ON CONFLICT(source_key) WHERE source_key<>'' DO UPDATE SET state=CASE WHEN app.call_schedules.state='cancelled' AND app.call_schedules.call_id IS NULL THEN 'pending' ELSE app.call_schedules.state END",
                (uuid4(), kind, at, key, source_type, source_id, revision),
            )

    def record_late(self, db, pref):
        """Reminders more than 2 minutes overdue (the laptop slept, the app was off, voice
        was down) are never dropped silently: each still-current one becomes a missed call."""
        from .call_briefs import item_for

        for schedule in db.execute(
            "SELECT * FROM app.call_schedules WHERE state='pending' AND due_at<%s FOR UPDATE",
            (self.now() - timedelta(minutes=2),),
        ).fetchall():
            current = schedule["source_type"] not in ("event", "routine") or item_for(db, schedule)
            missed = (
                self.missed(db, schedule)
                if current and not quiet(schedule["due_at"], pref)
                else None
            )
            db.execute(
                "UPDATE app.call_schedules SET state='cancelled',call_id=%s WHERE id=%s",
                (missed, schedule["id"]),
            )

    def missed(self, db, schedule):
        """Record a reminder that could not ring in time as a missed call (no media, no
        push), so it is visible in Calls. Only for the last 12 hours: nothing stale floods."""
        if self.now() - schedule["due_at"] > timedelta(hours=12):
            return None
        row = db.execute(
            "INSERT INTO app.calls(id,room,direction,reason,state,ended_at,expires_at,simulated) "
            "VALUES (%s,%s,'outbound',%s,'missed',%s,%s,%s) RETURNING *",
            (uuid4(), "missed-" + uuid4().hex, ("Missed " + self.reason(db, schedule))[:300],
             self.now(), self.now(), self.mode == "simulated"),
        ).fetchone()  # fmt: skip
        self.event(db, row)
        return row["id"]

    def reason(self, db, schedule):
        """What the ringing screen says. Shown only to signed-in clients; pushes stay generic."""
        from .call_briefs import item_for

        item = item_for(db, schedule) if schedule["source_type"] in ("event", "routine") else None
        return f"Reminder · {item['title']}" if item else "Yggdras check-in"

    def tick(self):
        if self.mode == "disabled":
            return
        ready = self.capabilities()["voice_ready"]
        with self.database.connect() as db:
            db.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK,))
            self.expire(db)
            from .call_outcomes import complete_ended

            complete_ended(db, self.now())  # slots that just ended count as completed
            if ready:
                pref = self.preferences(db)
                self.record_late(db, pref)  # before seeding, which re-cancels pending ones
                self.seed_schedules(db, pref)
                due = db.execute(
                    "SELECT * FROM app.call_schedules WHERE state='pending' AND due_at<=%s ORDER BY due_at,id FOR UPDATE",
                    (self.now(),),
                ).fetchall()
                for schedule in due:
                    late = self.now() - schedule["due_at"] > timedelta(minutes=2)
                    # A manual test (call_briefs ring_now) may ring in quiet hours; nothing else.
                    manual = schedule["reason"] == "Test reminder"
                    if late or (quiet(self.now(), pref) and not manual):
                        db.execute(
                            "UPDATE app.call_schedules SET state='cancelled' WHERE id=%s",
                            (schedule["id"],),
                        )
                        continue
                    active = db.execute(
                        "SELECT id,state FROM app.calls WHERE state IN ('ringing','answered') ORDER BY created_at LIMIT 1"
                    ).fetchone()
                    if (
                        active
                        and active["state"] == "answered"
                        and not db.execute(
                            "SELECT 1 FROM app.routine_voice_bindings WHERE call_id=%s",
                            (active["id"],),
                        ).fetchone()
                    ):
                        # Manoj is already talking to Yggdras: the voice worker announces this
                        # reminder inside that call instead of ringing a second one.
                        db.execute(
                            "UPDATE app.call_schedules SET state='rung',call_id=%s WHERE id=%s",
                            (active["id"], schedule["id"]),
                        )
                        continue
                    if active:  # ringing: wait for it to be answered or missed (<= 45 s)
                        continue
                    row = self.create(db, direction="outbound", reason=self.reason(db, schedule))
                    db.execute(
                        "UPDATE app.call_schedules SET state='rung',call_id=%s WHERE id=%s",
                        (row["id"], schedule["id"]),
                    )
        if ready and self.briefs is not None:
            self.briefs.kick()  # background: briefings for reminders due within 20 minutes
        self.deliver()

    def deliver(self):
        if not self.pusher or self.mode != "live":
            return
        # At-least-once transport; clients dedupe the stable call UUID and recheck state.
        with self.database.connect() as db:
            db.execute(
                "UPDATE app.call_delivery SET state='pending' WHERE state='sending' AND available_at<now()-interval '1 minute'"
            )
            rows = db.execute(
                "SELECT d.id,d.attempts,d.call_id,d.event_state,c.expires_at,c.state AS call_state,v.push_token,v.id AS device_id,v.revoked_at,v.session_expires_at,v.password_fingerprint FROM app.call_delivery d JOIN app.calls c ON c.id=d.call_id JOIN app.devices v ON v.id=d.device_id WHERE d.state='pending' AND d.available_at<=now() ORDER BY d.id LIMIT 20 FOR UPDATE OF d SKIP LOCKED"
            ).fetchall()
            for r in rows:
                db.execute(
                    "UPDATE app.call_delivery SET state='sending',attempts=attempts+1,available_at=now() WHERE id=%s",
                    (r["id"],),
                )
        for r in rows:
            state = "expired"
            if (
                not r["revoked_at"]
                and r["session_expires_at"]
                and r["session_expires_at"] > self.now()
                and r["password_fingerprint"] == self.auth_fingerprint
                and (
                    (
                        r["event_state"] == "ringing"
                        and r["call_state"] == "ringing"
                        and r["expires_at"] > self.now()
                    )
                    or r["event_state"] != "ringing"
                )
            ):
                try:
                    self.pusher.send(
                        {"id": str(r["device_id"]), "push_token": r["push_token"]},
                        {
                            "callId": str(r["call_id"]),
                            "expiresAt": r["expires_at"].isoformat(),
                            "state": r["event_state"],
                        },
                    )
                    state = "sent"
                except voice.PushDeviceExpired:
                    state = "failed"
                    with self.database.connect() as db:
                        db.execute(
                            "UPDATE app.devices SET revoked_at=now(),version=version+1 WHERE id=%s",
                            (r["device_id"],),
                        )
                except voice.PushNotConfigured:
                    state = "failed"
                except Exception:  # noqa: BLE001 -- sanitize delivery errors
                    state = "pending" if r["attempts"] < 2 else "failed"
            with self.database.connect() as db:
                db.execute(
                    "UPDATE app.call_delivery SET state=%s,available_at=now()+interval '15 seconds' WHERE id=%s",
                    (state, r["id"]),
                )


def call_router(service, session):
    r = APIRouter(prefix="/v1/calls")
    authenticated = Depends(session)

    @r.get("/capabilities")
    def capabilities(_=authenticated):
        return service.capabilities()

    @r.get("/reviews")
    def reviews(_=authenticated):
        from .agent_tools import Proposal
        from .voice_runtime import VoiceTools

        tools = VoiceTools(service.database, service.notes)
        with service.database.connect() as db:
            rows = db.execute(
                "SELECT id,call_id,payload,version FROM app.call_reviews WHERE state='waiting' ORDER BY created_at LIMIT 50"
            ).fetchall()
        for row in rows:
            try:
                row["current"] = tools.inspect(Proposal.model_validate(row["payload"]))
                row["blocked"] = ""
            except HTTPException as error:
                row["current"] = None
                row["blocked"] = error.detail
            except Exception:  # noqa: BLE001 -- do not expose private review details
                row["current"] = None
                row["blocked"] = (
                    "This linked item cannot be reviewed in a voice context. Open its application editor."
                )
        for row in rows:
            if row["blocked"]:
                row["payload"] = {
                    "operation": row["payload"].get("operation", "change"),
                    "data": {},
                    "explanation": "Open this item privately in its application editor.",
                }
        return rows

    @r.post("/reviews/{identifier}")
    def resolve_review(identifier: UUID, body: Review, _=authenticated):
        from .agent_tools import Proposal
        from .voice_runtime import VoiceTools

        with service.database.connect() as db:

            def action():
                row = db.execute(
                    "SELECT * FROM app.call_reviews WHERE id=%s AND version=%s AND state='waiting' FOR UPDATE",
                    (identifier, body.version),
                ).fetchone()
                if not row:
                    raise HTTPException(
                        409, "This voice proposal already changed. Refresh the review."
                    )
                if body.decision == "accept":
                    tools = VoiceTools(service.database, service.notes)
                    proposal = Proposal.model_validate(row["payload"])
                    tools.inspect(proposal, db)
                    tools.execute(proposal, body.key, db)
                db.execute(
                    "UPDATE app.call_reviews SET state=%s,version=version+1 WHERE id=%s",
                    ("accepted" if body.decision == "accept" else "dismissed", identifier),
                )
                return {"resolved": True}

            return service.receipt(
                db, body.key, {"review": str(identifier), **body.model_dump()}, action
            )

    @r.get("")
    def history(after: int = Query(default=0, ge=0), _=authenticated):
        return service.snapshot(after)

    @r.get("/events")
    def events(request: Request, after: int = Query(default=0, ge=0), _=authenticated):
        import time

        def stream():
            cursor = after
            while True:
                try:
                    session(request)
                except HTTPException:
                    yield b"event: expired\ndata: {}\n\n"
                    return
                data = jsonable_encoder(service.snapshot(cursor))
                cursor = data["cursor"]
                yield f"id: {cursor}\ndata: {json.dumps(data)}\n\n".encode()
                time.sleep(2)

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
        )

    @r.post("/simulation")
    def simulate(body: CallCommand, _=authenticated):
        if service.mode != "simulated":
            raise HTTPException(404, "Simulation is not enabled.")
        with service.database.connect() as db:
            return service.receipt(
                db,
                body.key,
                {"simulation": body.model_dump()},
                lambda: service.create(db, direction="outbound"),
            )

    @r.post("/{identifier}/end")
    def end(identifier: UUID, body: CallCommand, _=authenticated):
        with service.database.connect() as db:

            def action():
                row = db.execute(
                    "UPDATE app.calls SET state='ended',media_state='ended',ended_at=%s,version=version+1 WHERE id=%s AND state IN ('ringing','answered') RETURNING *",
                    (service.now(), identifier),
                ).fetchone()
                if row:
                    service.event(db, row)
                return {"ended": True}

            return service.receipt(db, body.key, {"end": str(identifier)}, action)

    @r.get("/preferences")
    def preferences(_=authenticated):
        with service.database.connect() as db:
            pref = service.preferences(db)
            return {
                **pref,
                "quiet_start": pref["quiet_start"].strftime("%H:%M"),
                "quiet_end": pref["quiet_end"].strftime("%H:%M"),
            }

    @r.put("/preferences")
    def save_preferences(body: Preferences, _=authenticated):
        with service.database.connect() as db:
            row = db.execute(
                "UPDATE app.call_preferences SET scheduled=%s,calendar_starts=%s,calendar_ends=%s,routines=%s,timezone=%s,quiet_start=%s::time,quiet_end=%s::time,version=version+1 WHERE version=%s RETURNING version",
                (
                    body.scheduled,
                    body.calendar_starts,
                    body.calendar_ends,
                    body.routines,
                    body.timezone,
                    body.quiet_start,
                    body.quiet_end,
                    body.version,
                ),
            ).fetchone()
            if not row:
                raise HTTPException(409, "Call preferences changed. Refresh before saving.")
            return row

    @r.post("")
    def start(body: CallCommand, auth=authenticated):
        service.require_ready()
        identity = session_id(auth)
        with service.database.connect() as db:
            out = service.receipt(
                db,
                body.key,
                {"start": body.model_dump(), "session": identity},
                lambda: service.create(
                    db, direction="inbound", key=body.key, identity=identity, device=body.device
                ),
            )
            row = db.execute("SELECT * FROM app.calls WHERE id=%s", (out["id"],)).fetchone()
        return {**jsonable_encoder(row), **service.access(row, identity, body.device)}

    @r.post("/{identifier}/answer")
    def answer(identifier: UUID, body: CallCommand, auth=authenticated):
        service.require_ready()
        identity = session_id(auth)
        with service.database.connect() as db:

            def action():
                service.expire(db)
                row = db.execute(
                    "UPDATE app.calls SET state='answered',answer_session=%s,answered_by=%s,answered_at=%s,media_state='connecting',version=version+1 WHERE id=%s AND state='ringing' AND expires_at>%s RETURNING *",
                    (identity, body.device, service.now(), identifier, service.now()),
                ).fetchone()
                if not row:
                    raise HTTPException(409, "Another device answered, or this call expired.")
                service.event(db, row)
                return row

            service.receipt(
                db,
                body.key,
                {"answer": str(identifier), "device": body.device, "session": identity},
                action,
            )
            row = db.execute("SELECT * FROM app.calls WHERE id=%s", (identifier,)).fetchone()
        return {**jsonable_encoder(row), **service.access(row, identity, body.device)}

    @r.post("/{identifier}/decline")
    def decline(identifier: UUID, body: CallCommand, _=authenticated):
        with service.database.connect() as db:

            def action():
                service.expire(db)
                row = db.execute(
                    "UPDATE app.calls SET state='declined',ended_at=%s,version=version+1 WHERE id=%s AND state='ringing' RETURNING *",
                    (service.now(), identifier),
                ).fetchone()
                if not row:
                    raise HTTPException(409, "This call is no longer ringing.")
                service.event(db, row)
                return {"declined": True}

            return service.receipt(db, body.key, {"decline": str(identifier)}, action)

    @r.post("/{identifier}/media")
    def media(identifier: UUID, body: CallUpdate, auth=authenticated):
        with service.database.connect() as db:

            def action():
                row = db.execute(
                    "UPDATE app.calls SET media_state=%s,state=CASE WHEN %s IN ('failed','ended') THEN 'ended' ELSE state END,ended_at=CASE WHEN %s IN ('failed','ended') THEN %s ELSE ended_at END,version=version+1 WHERE id=%s AND version=%s AND state='answered' AND answer_session=%s AND answered_by=%s RETURNING *",
                    (
                        body.state,
                        body.state,
                        body.state,
                        service.now(),
                        identifier,
                        body.version,
                        session_id(auth),
                        body.device,
                    ),
                ).fetchone()
                if not row:
                    raise HTTPException(409, "This call changed or belongs to another device.")
                service.event(db, row)
                return row

            return service.receipt(
                db,
                body.key,
                {"media": str(identifier), "session": session_id(auth), **body.model_dump()},
                action,
            )

    @r.post("/schedule")
    def schedule(body: Schedule, _=authenticated):
        if (body.at is None) == (body.minutes is None):
            raise HTTPException(422, "Choose a time or snooze duration.")
        due = body.at or service.now() + timedelta(minutes=body.minutes)
        if due.tzinfo is None or not service.now() < due < service.now() + timedelta(days=365):
            raise HTTPException(422, "Choose an offset-aware future time within one year.")
        with service.database.connect() as db:
            pref = service.preferences(db)
            if quiet(due, pref):
                raise HTTPException(
                    409, "That time is within your quiet hours. Choose a time outside them."
                )

            def action():
                identifier = uuid4()
                db.execute(
                    "INSERT INTO app.call_schedules(id,kind,due_at,reason) VALUES (%s,%s,%s,'Requested check-in')",
                    (identifier, "snooze" if body.minutes else "one_off", due),
                )
                return {
                    "id": identifier,
                    "due_at": due,
                    "kind": "snooze" if body.minutes else "one_off",
                }

            return service.receipt(db, body.key, body.model_dump(), action)

    @r.post("/devices")
    def device(body: Device, auth=authenticated):
        with service.database.connect() as db:
            db.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK,))
            if not db.execute(
                "SELECT 1 FROM app.sessions WHERE csrf=%s AND expires_at>now() AND password_fingerprint=%s",
                (auth["csrf"], service.auth_fingerprint),
            ).fetchone():
                raise HTTPException(401, "This session expired before device registration.")
            return db.execute(
                "INSERT INTO app.devices(id,platform,push_token,label,session_hash,session_expires_at,password_fingerprint) VALUES (%s,'android',%s,%s,%s,%s,%s) ON CONFLICT(platform,push_token) DO UPDATE SET session_hash=EXCLUDED.session_hash,session_expires_at=EXCLUDED.session_expires_at,password_fingerprint=EXCLUDED.password_fingerprint,revoked_at=NULL,last_seen_at=now(),version=app.devices.version+1 RETURNING id,version",
                (
                    uuid4(),
                    body.push_token,
                    body.label,
                    session_id(auth),
                    auth["expires_at"],
                    service.auth_fingerprint,
                ),
            ).fetchone()

    @r.delete("/devices/{identifier}")
    def revoke(identifier: UUID, auth=authenticated):
        with service.database.connect() as db:
            db.execute(
                "UPDATE app.devices SET revoked_at=now(),version=version+1 WHERE id=%s AND session_hash=%s",
                (identifier, session_id(auth)),
            )
        return {"revoked": True}

    return r
