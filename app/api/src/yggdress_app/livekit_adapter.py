"""SDK LLM node for every call, with no paid retry.

One class serves both kinds of call: while a reminder is in focus (a reminder call, or a
reminder announced into a call already running) each turn goes to call_briefs.Answerer
over its prepared briefing; otherwise to the full Yggdras role (VoiceRuntime.turn). A
failure inside a turn is spoken as a short apology: the call itself never breaks.
"""

import asyncio
import logging
from uuid import uuid4

from livekit.agents import llm
from livekit.agents.types import APIConnectOptions

# Yggdras hand-offs and Lia can take well over a minute (prep took 72 s on the laptop).
TURN_TIMEOUT = 180
TROUBLE = "Sorry, sir, I ran into a problem with that. Could you try again?"
# Spoken at once when a turn needs the full Yggdras role, so the line never goes silent
# while it works (that can take tens of seconds). Free: no model call.
HOLD = "One moment."


class CallLLM(llm.LLM):
    def __init__(self, runtime, identifier, history, hang_up=lambda: None, answerer=None):
        super().__init__()
        self.runtime, self.identifier, self.history = runtime, identifier, history
        self.hang_up = hang_up
        self.answerer = answerer  # call_briefs.Answerer while a reminder is in focus
        self.wants_end = False  # set by a turn; hang_up() runs on the event loop

    @property
    def model(self):
        return "reminder-briefing" if self.answerer else "existing-yggdras-role"

    @property
    def provider(self):
        return "application"

    def chat(self, *, chat_ctx, tools=None, **_):
        return CallStream(
            self,
            chat_ctx=chat_ctx,
            tools=[],
            conn_options=APIConnectOptions(max_retry=0, timeout=TURN_TIMEOUT),
        )


class CallStream(llm.LLMStream):
    async def _run(self):
        text = next(
            (
                item.text_content
                for item in reversed(self._chat_ctx.items)
                if getattr(item, "role", None) == "user"
            ),
            "",
        )
        if not text:
            return
        owner, loop = self._llm, asyncio.get_running_loop()

        def send(piece):
            chunk = llm.ChatChunk(
                id=str(uuid4()), delta=llm.ChoiceDelta(role="assistant", content=piece + " ")
            )
            loop.call_soon_threadsafe(self._event_ch.send_nowait, chunk)

        answer = await asyncio.to_thread(answer_turn, owner, text, send)
        if answer is None:
            return
        owner.history.extend(
            [{"role": "user", "content": text}, {"role": "assistant", "content": answer}]
        )
        self._event_ch.send_nowait(
            llm.ChatChunk(id=str(uuid4()), delta=llm.ChoiceDelta(role="assistant", content=answer))
        )
        if owner.wants_end or (owner.answerer is not None and owner.answerer.wants_end):
            owner.hang_up()  # on the event loop: hang_up schedules a task on it


def answer_turn(owner, text, send=lambda piece: None):
    """One spoken turn, run in a worker thread. Returns the reply, or None when the call is
    no longer answered. Never touches the event loop: hanging up is flagged, not done."""
    from .call_briefs import GOODBYE, plain_end

    try:
        if owner.answerer is not None:
            messages = [*owner.history[-10:], {"role": "user", "content": text}]
            return owner.answerer.reply(messages, send)
        if plain_end(text):  # "bye" / "end the call": hang up without the slow pipeline
            owner.wants_end = True
            return GOODBYE
        with owner.runtime.database.connect() as db:
            if not db.execute(
                "SELECT 1 FROM app.calls WHERE id=%s AND state='answered'", (owner.identifier,)
            ).fetchone():
                return None
        send(HOLD)
        return owner.runtime.turn(owner.identifier, text, owner.history)
    except Exception as exc:  # noqa: BLE001 -- never break a live call; no private details logged
        logging.getLogger("yggdras.voice").error("voice turn failed: %s", type(exc).__name__)
        return TROUBLE
