"""Optional local LiveKit worker. No network/model work occurs at import time."""

import asyncio
import json
import logging
import os
from pathlib import Path
from uuid import UUID

# Male British voice (Cartesia "Classy British Man" via LiveKit Inference); YGGDRAS_VOICE_ID overrides.
VOICE = "a0e99841-438c-4a64-b679-ae501e7d6091"


def configured(home):
    from .voice_runtime import load_voice_environment

    config = json.loads((home / "runtime.json").read_text())
    load_voice_environment(config["brain_env"])
    return config


class CallYggdras:
    """The full Yggdras role, bound to one reminder call and its own short history."""

    def __init__(self, runtime, call_id):
        self.runtime, self.call_id, self.history = runtime, call_id, []

    def pending(self):
        return bool(self.runtime.pending(self.call_id))

    def turn(self, text):
        answer = self.runtime.turn(self.call_id, text, self.history)
        self.history += [
            {"role": "user", "content": text},
            {"role": "assistant", "content": answer},
        ]
        return answer


def reminder_answerer(database, runtime, agent_config, call_id):
    """The fast answerer for the newest reminder on this call (the one that rang it, or one
    announced into it), or None for a call Manoj started. If the background briefing is
    missing or failed, a plain one is built from the item; end check-ins never use one."""
    from functools import partial

    from .call_briefs import (
        BRIEF_MODEL,
        Answerer,
        Brief,
        BriefStore,
        act,
        ask_lia,
        end_summary,
        fallback_summary,
        is_end,
        item_for,
    )

    with database.connect() as db:
        schedule, brief = BriefStore().for_call(db, call_id)
        if not schedule or schedule["source_type"] not in ("event", "routine"):
            return None
        if brief is None or is_end(schedule):
            item = item_for(db, schedule)
            if item is None:
                return None
            summary = end_summary(item) if is_end(schedule) else fallback_summary(item)
            brief = Brief(schedule["source_key"], item["title"], schedule["due_at"], "failed",
                          summary=summary, context=item.get("description") or "")  # fmt: skip
        follow_up = None
        if schedule["source_type"] == "routine" and not is_end(schedule):
            from .call_outcomes import follow_up as earlier
            from .call_outcomes import occurrence

            routine_item = item_for(db, schedule)
            if routine_item:
                follow_up = earlier(db, schedule["source_id"], occurrence(routine_item)[2])
    # The one backup lookup goes through Lia, the single door to the notes; anything else
    # (calendar, tasks, reminders, suggestions) is handed to the full Yggdras role.
    return Answerer(
        database, call_id, schedule, brief, agent_config["model_factory"](BRIEF_MODEL),
        lookup=partial(ask_lia, agent_config.get("lia"), runtime.notes, brief.title),
        yggdras=CallYggdras(runtime, call_id),
        follow_up=follow_up,
        actions=partial(act, database, call_id, schedule),
    )  # fmt: skip


async def voice_session(ctx):
    from livekit.agents import Agent, AgentSession, inference

    from .agent_worker import private_agent_configuration
    from .database import Database
    from .local_runtime import brain_http
    from .notes_proxy import NotesProxy
    from .voice_runtime import VoiceRuntime

    config = configured(Path(os.environ["YGGDRAS_VOICE_HOME"]))
    database = Database(config["database_url"])
    agent_config = private_agent_configuration(config)
    runtime = VoiceRuntime(
        database,
        NotesProxy(brain_http(config["brain_env"])),
        agent_config["model_factory"](agent_config["default_model"]),
        lia=agent_config.get("lia"),
    )
    try:
        identifier = UUID(json.loads(ctx.job.metadata)["call_id"])
    except (ValueError, KeyError, TypeError):
        return
    with database.connect() as db:
        call = db.execute(
            "SELECT * FROM app.calls WHERE id=%s AND room=%s AND state='answered'",
            (identifier, ctx.job.room.name),
        ).fetchone()
    if not call:
        return
    history = []

    from .livekit_adapter import CallLLM

    # A reminder call (rung by a schedule) answers from its prepared briefing: fast.
    # A call Manoj starts himself uses the full Yggdras role until a reminder is announced.
    answerer = reminder_answerer(database, runtime, agent_config, identifier)

    def hang_up():
        # Let the goodbye play, then end the call; finish() records it and tells clients.
        async def later():
            await asyncio.sleep(4)
            ctx.shutdown(reason="Manoj ended the call")

        asyncio.get_running_loop().create_task(later())

    call_llm = CallLLM(runtime, identifier, history, hang_up, answerer)
    with database.connect() as db:
        # Reminders already on this call (the one that rang it) are not announced again.
        announced = {r["id"] for r in db.execute(
            "SELECT id FROM app.call_schedules WHERE call_id=%s", (identifier,)).fetchall()}  # fmt: skip
    started = []

    def announce_due():
        """A reminder that came due during this call (the scheduler attached it here
        instead of ringing a second call): speak it now and put it in focus."""
        with database.connect() as db:
            fresh = [r for r in db.execute(
                "SELECT id FROM app.call_schedules WHERE call_id=%s AND state='rung' ORDER BY due_at",
                (identifier,)).fetchall() if r["id"] not in announced]  # fmt: skip
        if not fresh or not started:
            return None
        announced.update(r["id"] for r in fresh)
        focus = reminder_answerer(database, runtime, agent_config, identifier)
        if focus is None:
            return None
        call_llm.answerer = focus
        text = focus.announcement()
        history.append({"role": "assistant", "content": text})
        return text  # spoken by the caller on the event loop (AgentSession is not thread-safe)

    audio = AgentSession(
        llm=call_llm,
        # The speech-to-text service decides when Manoj has finished speaking. A local VAD
        # ran "slower than realtime" on this laptop and his turns were never detected.
        stt=inference.STT(
            model=os.environ.get("YGGDRAS_VOICE_STT", "deepgram/nova-3-general"), language="en"
        ),
        turn_detection="stt",
        tts=inference.TTS(
            model=os.environ.get("YGGDRAS_VOICE_TTS", "cartesia/sonic-3"),
            voice=os.environ.get("YGGDRAS_VOICE_ID", VOICE),
        ),
    )

    @audio.on("error")
    def on_audio_error(event):
        if getattr(event.error, "recoverable", False):
            return
        with database.connect() as db:
            db.execute(
                "UPDATE app.calls SET media_state='failed',failure='Voice transport failed',version=version+1 WHERE id=%s AND state='answered'",
                (identifier,),
            )
        ctx.shutdown(reason="Voice transport unavailable")

    async def monitor():
        while True:
            with database.connect() as db:
                db.execute(
                    "INSERT INTO app.voice_worker_lease(name) VALUES ('yggdras-voice') ON CONFLICT(name) DO UPDATE SET seen_at=now()"
                )
                active = db.execute(
                    "SELECT 1 FROM app.calls WHERE id=%s AND state='answered'", (identifier,)
                ).fetchone()
            if not active:
                await audio.aclose()
                return
            try:
                text = await asyncio.to_thread(announce_due)
                if text:
                    audio.say(text)
            except Exception as exc:  # noqa: BLE001 -- an announcement never ends the call
                logging.getLogger("yggdras.voice").error("announce failed: %s", type(exc).__name__)
            await asyncio.sleep(10)

    async def finish():
        # A reminder attached to this call that was never spoken goes back to the queue:
        # it rings on its own (or shows as missed if too late). Never lost with the call.
        with database.connect() as db:
            db.execute(
                "UPDATE app.call_schedules SET state='pending',call_id=NULL "
                "WHERE call_id=%s AND state='rung' AND NOT (id = ANY(%s))",
                (identifier, list(announced)),
            )
        # Summaries stay in app storage; raw audio/transcripts are not retained.
        summary = await asyncio.to_thread(runtime.summarize, history)
        with database.connect() as db:
            row = db.execute(
                "UPDATE app.calls SET summary=CASE WHEN summary='' THEN %s ELSE summary END,state='ended',media_state=CASE WHEN media_state='failed' THEN 'failed' ELSE 'ended' END,ended_at=coalesce(ended_at,now()),version=version+1 WHERE id=%s RETURNING *",
                (summary, identifier),
            ).fetchone()
            if row:
                from .call_service import CallService
                from .security import token_hash

                service = CallService(database)
                service.auth_fingerprint = token_hash(config["password_hash"])
                service.event(db, row)
        task.cancel()

    ctx.add_shutdown_callback(finish)
    task = asyncio.create_task(monitor())
    stage = "connect"
    try:
        await ctx.connect()
        from .security import token_hash

        stage = "wait for caller"

        expected = "client-" + token_hash(call["answer_session"] + call["answered_by"])[:24]
        await asyncio.wait_for(ctx.wait_for_participant(identity=expected), timeout=45)
        stage = "start session"
        await audio.start(
            room=ctx.room,
            agent=Agent(
                instructions="You are Yggdras. Use the existing application coordinator for each spoken turn."
            ),
            # Never record: without this, LiveKit follows the cloud project's setting and
            # uploads audio, transcripts and logs. Calls are not recorded (planning invariant).
            record=False,
        )
        started.append(True)
        if answerer:
            # The summary was written in the background: speak it at once, no model call.
            opening = answerer.opening()
            history.append({"role": "assistant", "content": opening})
            stage = "speak summary"
            audio.say(opening)  # plays in the background; setup must not wait on playout
        else:
            await audio.generate_reply(
                user_input="Open this call with a brief, calm greeting and the current scheduled-item context if available. Ask one useful question. Do not propose or make changes unless I ask."
            )
    except Exception as exc:  # noqa: BLE001 -- credentials and transcripts must never enter logs
        # Only the step and the error type: never its message, which may hold private data.
        logging.getLogger("yggdras.voice").error(
            "voice session failed at %s: %s", stage, type(exc).__name__
        )
        with database.connect() as db:
            db.execute(
                "UPDATE app.calls SET state='ended',media_state='failed',failure='Voice transport failed',ended_at=now(),version=version+1 WHERE id=%s",
                (identifier,),
            )
        task.cancel()
        raise RuntimeError("Voice transport unavailable.") from None


def main():
    import argparse
    import sys

    from . import voice

    parser = argparse.ArgumentParser()
    parser.add_argument("--home", type=Path, required=True)
    args = parser.parse_args()
    config = configured(args.home)
    if os.environ.get("YGGDRAS_CALLS_MODE") != "live" or voice.missing(voice.LIVEKIT_VARS):
        raise SystemExit(
            "Voice is disabled. Configure LiveKit and explicitly enable live mode first."
        )
    os.environ["YGGDRAS_VOICE_HOME"] = str(args.home)
    from livekit import agents
    from livekit.agents import AgentServer

    from .database import Database

    database = Database(config["database_url"])
    # INFO adds job and connection events only; transcripts and credentials are not logged.
    level = "info" if os.environ.get("YGGDRAS_VOICE_DEBUG") == "1" else "error"

    # One call slot stays warm so LiveKit's job assignment is answered in time.
    # Load is "a call is running", not the laptop's CPU: brief CPU spikes from other local
    # services marked this one-person worker full, and LiveKit stopped sending it calls.
    def load(server):
        return 1.0 if server.active_jobs else 0.0

    idle = int(os.environ.get("YGGDRAS_VOICE_IDLE_PROCESSES", "1"))  # 0 on a small host
    server = AgentServer(host="127.0.0.1", port=0, num_idle_processes=idle, log_level=level,
                         initialize_process_timeout=60.0,
                         load_fnc=load, load_threshold=0.5)  # fmt: skip
    server.rtc_session(agent_name="yggdras-voice")(voice_session)
    heartbeat_task = None

    def beat():
        with database.connect() as db:
            db.execute(
                "INSERT INTO app.voice_worker_lease(name) VALUES ('yggdras-voice') ON CONFLICT(name) DO UPDATE SET seen_at=now()"
            )

    async def heartbeat():
        while True:
            # Off the event loop: a blocking database call here stalled LiveKit's connection.
            await asyncio.to_thread(beat)
            await asyncio.sleep(10)

    def on_registered(*_):
        nonlocal heartbeat_task
        if heartbeat_task is None or heartbeat_task.done():
            heartbeat_task = asyncio.create_task(heartbeat())

    server.on("worker_registered", on_registered)
    sys.argv = [sys.argv[0], "start"]
    agents.cli.run_app(server)


if __name__ == "__main__":
    main()
