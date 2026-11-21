"""Use the installed media SDK with a scripted existing Yggdras model; never paid APIs."""

import asyncio
import pickle
from uuid import uuid4

import pytest

from yggdress_app.agent_models import ModelReply
from yggdress_app.voice_runtime import VoiceRuntime


def test_worker_entrypoint_is_picklable_for_windows_spawn():
    from yggdress_app.voice_worker import voice_session

    assert pickle.loads(pickle.dumps(voice_session)) is voice_session


def test_sdk_adapter_runs_a_scripted_existing_role_and_summarizes_in_app(postgres):
    pytest.importorskip("livekit.agents")
    from livekit.agents import llm

    from yggdress_app.database import Database
    from yggdress_app.livekit_adapter import CallLLM

    database = Database(postgres["runtime"])
    identifier = uuid4()
    with database.connect() as db:
        db.execute(
            "INSERT INTO app.calls(id,direction,room,state,simulated) VALUES (%s,'inbound',%s,'answered',true)",
            (identifier, "fixture-" + identifier.hex),
        )

    class Scripted:
        def __init__(self):
            self.calls = 0

        def complete(self, system, messages, tools):
            self.calls += 1
            return ModelReply(
                [
                    {
                        "type": "text",
                        "text": "The invented meeting is ready."
                        if self.calls == 1
                        else "Discussed an invented meeting. No changes were applied.",
                    }
                ]
            )

    class NoNotes:
        def search(self, *_):
            raise AssertionError("This simple voice turn needs no note retrieval.")

    model = Scripted()
    runtime = VoiceRuntime(database, NoNotes(), model)
    history = []

    async def run():
        context = llm.ChatContext()
        context.add_message(role="user", content="Brief me about an invented meeting.")
        adapter = CallLLM(runtime, identifier, history)
        async with adapter.chat(chat_ctx=context) as stream:
            chunks = [chunk.delta.content or "" async for chunk in stream if chunk.delta]
            return "".join(chunks)

    assert asyncio.run(run()) == "The invented meeting is ready."
    assert len(history) == 2
    summary = runtime.summarize(history)
    assert summary == "Discussed an invented meeting. No changes were applied."
    assert model.calls == 2
    with database.connect() as db:
        db.execute("UPDATE app.calls SET summary=%s WHERE id=%s", (summary, identifier))
        assert (
            db.execute("SELECT summary FROM app.calls WHERE id=%s", (identifier,)).fetchone()[
                "summary"
            ]
            == summary
        )


def test_turns_are_detected_by_speech_to_text_not_a_local_vad():
    """A local VAD ran slower than realtime on the laptop and Manoj's turns were never
    detected; the speech-to-text service ends turns. No plugin registers inside a call."""
    import inspect

    from yggdress_app import voice_worker

    session = inspect.getsource(voice_worker.voice_session)
    main = inspect.getsource(voice_worker.main)
    assert 'turn_detection="stt"' in session and "vad=" not in session
    assert "livekit.plugins" not in session and "silero" not in main
    assert "initialize_process_timeout=60.0" in main
    assert "num_idle_processes=idle" in main and "asyncio.to_thread(beat)" in main
    assert 'YGGDRAS_VOICE_IDLE_PROCESSES", "1"' in main  # one warm process unless told 0
    assert "load_fnc=load" in main  # busy means a call is running, never laptop CPU


def test_yggdras_speaks_with_a_male_british_voice_by_default():
    from yggdress_app import voice_worker

    assert voice_worker.VOICE == "a0e99841-438c-4a64-b679-ae501e7d6091"


def test_a_call_is_never_recorded_whatever_the_cloud_project_says():
    """LiveKit defaults to the cloud project's recording setting (audio, transcript, logs)."""
    import inspect

    from yggdress_app import voice_worker

    assert "record=False" in inspect.getsource(voice_worker.voice_session)


def test_a_spoken_yes_applies_the_change_waiting_on_the_call_and_no_drops_it(postgres):
    """The same execute path as the Calls review's Accept; Manoj's spoken yes approves."""
    import json

    from psycopg.types.json import Jsonb

    from yggdress_app.database import Database

    database = Database(postgres["runtime"])
    runtime = VoiceRuntime(database, None, None)
    call = uuid4()

    def waiting(title):
        payload = {"operation": "event.create", "explanation": f"Add {title} at 15:00.",
                   "data": {"title": title, "start": "2030-04-11T15:00:00+02:00",
                            "end": "2030-04-11T16:00:00+02:00", "timezone": "Europe/Berlin"}}  # fmt: skip
        with database.connect() as db:
            db.execute("INSERT INTO app.call_reviews(id,call_id,payload) VALUES (%s,%s,%s)",
                       (uuid4(), call, Jsonb(payload)))  # fmt: skip

    with database.connect() as db:
        db.execute(
            "INSERT INTO app.calls(id,direction,room,state,simulated) VALUES (%s,'inbound',%s,'answered',true)",
            (call, "fixture-" + call.hex),
        )
    waiting("Invented accepted event")
    assert runtime.turn(call, "yes", []) == "Done."
    waiting("Invented declined event")
    assert runtime.turn(call, "no thanks", []) == "Alright, I've left everything as it was."
    with database.connect() as db:
        titles = {
            r["title"] for r in db.execute("SELECT title FROM app.calendar_events").fetchall()
        }
        states = [r["state"] for r in db.execute(
            "SELECT state FROM app.call_reviews WHERE call_id=%s ORDER BY created_at", (call,)).fetchall()]  # fmt: skip
        summary = db.execute("SELECT summary FROM app.calls WHERE id=%s", (call,)).fetchone()[
            "summary"
        ]
    assert "Invented accepted event" in titles and "Invented declined event" not in titles
    assert states == ["accepted", "dismissed"]
    assert "Applied: Add Invented accepted event" in summary and "Declined:" in summary
    assert json.dumps(runtime.pending(call)) == "[]"
