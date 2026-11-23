"""Model access for the conductor, by role. One small interface (`Models`) so the
orchestrator never touches an SDK and every test runs on `FakeModels` (no spend).

Roles [owner decision 2026-11-22]: the conversation/orchestrator defaults to Sonnet 5.5;
Haiku 5.5 only routes and verifies. Workers per step are chosen by the planner. Opus and
Fable are selectable per conversation, never defaults.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any, ClassVar, Literal, Protocol, TypeVar

from pydantic import BaseModel

from .state import Usage

Role = Literal["router", "orchestrator", "worker", "verifier", "composer"]

# Prices per million tokens (input, output) [cited: Anthropic model table, 2026-11-03].
PRICES: dict[str, tuple[float, float]] = {
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-opus-5-5": (4.00, 20.00),
    "claude-fable-5-2": (8.00, 40.00),
}
CHAT_DEFAULT = "claude-sonnet-5-5"
ROLE_DEFAULTS: dict[str, str] = {
    "router": "claude-haiku-5-5",
    "verifier": "claude-haiku-5-5",
    "orchestrator": CHAT_DEFAULT,
    "composer": CHAT_DEFAULT,
    "worker": CHAT_DEFAULT,
}
CHOOSABLE = {
    "claude-sonnet-5-5": "Sonnet 5.5",
    "claude-opus-5-5": "Opus 5.5",
    "claude-fable-5-2": "Fable 5.2",
    "claude-haiku-5-5": "Haiku 5.5",
}
# Models with a server-side refusal fallback (Haiku 5.5 has none) [cited].
FALLBACK_MODELS = {"claude-sonnet-5-5", "claude-opus-5-5", "claude-fable-5-2"}
FALLBACK_BETA = "server-side-fallback-2026-07-01"
EFFORT: dict[str, str] = {
    "router": "low",
    "verifier": "low",
    "worker": "medium",
    "orchestrator": "medium",
    "composer": "medium",
}


def cost(model: str, input_tokens: int, output_tokens: int) -> float:
    p_in, p_out = PRICES.get(model, PRICES[CHAT_DEFAULT])
    return round((input_tokens * p_in + output_tokens * p_out) / 1_000_000, 6)


def usage(role: str, model: str, input_tokens: int, output_tokens: int) -> Usage:
    return Usage(
        role=role,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost(model, input_tokens, output_tokens),
    )


class ModelError(RuntimeError):
    """A model call failed in a way the run should report (refusal, truncation, API)."""


# ---- stream events ---------------------------------------------------------------------
@dataclass(frozen=True)
class TextDelta:
    text: str


@dataclass(frozen=True)
class ReasoningDelta:
    text: str


@dataclass(frozen=True)
class ToolUse:
    id: str
    name: str
    input: dict[str, Any]


@dataclass(frozen=True)
class Reset:
    """A server-side refusal fallback took over mid-stream: discard what streamed so far
    (the declining model's partial text) [cited: refusal fallbacks]."""


@dataclass(frozen=True)
class Finished:
    usage: Usage
    stop_reason: str
    content: list[dict[str, Any]] = field(default_factory=list)  # to append to history


Event = TextDelta | ReasoningDelta | ToolUse | Reset | Finished
Schema = TypeVar("Schema", bound=BaseModel)


class Models(Protocol):
    def stream(
        self,
        *,
        role: Role,
        model: str,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 16000,
    ) -> Iterator[Event]: ...

    def structured(
        self,
        *,
        role: Role,
        model: str,
        system: str,
        messages: list[dict[str, Any]],
        schema: type[Schema],
        max_tokens: int = 4000,
    ) -> tuple[Schema, Usage]: ...


def replayable(content: list[Any]) -> list[dict[str, Any]]:
    """Blocks to send back in the next turn: after a server-side fallback, only what the
    fallback model produced (blocks after the last `fallback` marker, not the marker)."""
    blocks = [b.model_dump(mode="json", exclude_none=True, by_alias=True) for b in content]
    last = max((i for i, b in enumerate(blocks) if b.get("type") == "fallback"), default=-1)
    return blocks[last + 1 :]


class AnthropicModels:
    """The real client (official SDK). Runs in worker threads, so it is synchronous."""

    def __init__(self, api_key: str | None = None):
        import anthropic

        self._anthropic = anthropic
        self._client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()

    def _options(self, role: str, model: str) -> dict[str, Any]:
        options: dict[str, Any] = {"output_config": {"effort": EFFORT.get(role, "medium")}}
        if model != "claude-haiku-5-5":
            # Readable reasoning for the Reasoning card; thinking is always on.
            options["thinking"] = {"type": "adaptive", "display": "summarized"}
        if model in FALLBACK_MODELS:
            options["betas"] = [FALLBACK_BETA]
            options["fallbacks"] = "default"
        return options

    def stream(self, *, role, model, system, messages, tools=None, max_tokens=16000):
        options = self._options(role, model)
        if tools:
            options["tools"] = tools
        try:
            with self._client.beta.messages.stream(
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=messages,
                **options,
            ) as stream:
                for event in stream:
                    if (
                        event.type == "content_block_start"
                        and event.content_block.type == "fallback"
                    ):
                        yield Reset()
                    elif event.type == "content_block_delta":
                        if event.delta.type == "text_delta":
                            yield TextDelta(event.delta.text)
                        elif event.delta.type == "thinking_delta":
                            yield ReasoningDelta(event.delta.thinking)
                final = stream.get_final_message()
        except self._anthropic.APIStatusError as error:
            raise ModelError(f"The model service returned {error.status_code}.") from error
        except self._anthropic.APIConnectionError as error:
            raise ModelError("The model service could not be reached.") from error
        if final.stop_reason == "refusal":
            raise ModelError("The model declined this request.")
        for block in final.content:
            if block.type == "tool_use":
                yield ToolUse(block.id, block.name, dict(block.input))
        yield Finished(
            usage(role, final.model, final.usage.input_tokens, final.usage.output_tokens),
            final.stop_reason or "end_turn",
            replayable(final.content),
        )

    def structured(self, *, role, model, system, messages, schema, max_tokens=4000):
        try:
            response = self._client.beta.messages.parse(
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=messages,
                output_format=schema,
                **self._options(role, model),
            )
        except self._anthropic.APIStatusError as error:
            raise ModelError(f"The model service returned {error.status_code}.") from error
        except self._anthropic.APIConnectionError as error:
            raise ModelError("The model service could not be reached.") from error
        if response.stop_reason == "refusal" or response.parsed_output is None:
            raise ModelError("The model gave no usable structured answer.")
        return response.parsed_output, usage(
            role, response.model, response.usage.input_tokens, response.usage.output_tokens
        )


class FakeModels:
    """Deterministic stand-in for tests and YGGDRAS_FAKE_MODEL=1 previews. Scripted by
    role: `replies[role]` is a list consumed in order; a reply is a str (streamed in
    small chunks), a BaseModel/dict (structured), a ToolUse, or an Exception."""

    def __init__(self, replies: dict[str, list[Any]] | None = None, chunk: int = 7):
        self.replies = {k: list(v) for k, v in (replies or {}).items()}
        self.calls: list[dict[str, Any]] = []
        self.chunk = chunk

    def _next(self, role: str, **call) -> Any:
        self.calls.append({"role": role, **call})
        queue = self.replies.get(role) or []
        if not queue:
            return f"(fake {role} reply)"
        reply = queue.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply

    def stream(self, *, role, model, system, messages, tools=None, max_tokens=16000):
        reply = self._next(role, model=model, system=system, messages=messages, tools=tools)
        if callable(reply):
            reply = reply(messages)
        items = reply if isinstance(reply, list) else [reply]
        text = ""
        for item in items:
            if isinstance(item, (ToolUse, ReasoningDelta)):
                yield item
            elif isinstance(item, Reset):
                text = ""
                yield item
            else:
                for i in range(0, len(str(item)), self.chunk):
                    piece = str(item)[i : i + self.chunk]
                    text += piece
                    yield TextDelta(piece)
        tools_used = [i for i in items if isinstance(i, ToolUse)]
        content = ([{"type": "text", "text": text}] if text else []) + [
            {"type": "tool_use", "id": t.id, "name": t.name, "input": t.input} for t in tools_used
        ]
        yield Finished(
            usage(role, model, 10, max(1, len(text) // 4)),
            "tool_use" if tools_used else "end_turn",
            content,
        )

    # Unscripted structured calls: the router answers directly, the verifier passes.
    DEFAULTS: ClassVar[dict[str, dict[str, Any]]] = {
        "router": {"mode": "answer", "reason": "fake"},
        "verifier": {"passed": True, "reason": "fake"},
    }

    def structured(self, *, role, model, system, messages, schema, max_tokens=4000):
        if not self.replies.get(role) and role in self.DEFAULTS:
            self.calls.append(
                {"role": role, "model": model, "system": system, "messages": messages}
            )
            value = schema.model_validate(self.DEFAULTS[role])
            return value, usage(role, model, 10, 5)
        reply = self._next(role, model=model, system=system, messages=messages, schema=schema)
        if callable(reply):
            reply = reply(messages)
        value = reply if isinstance(reply, schema) else schema.model_validate(reply)
        return value, usage(role, model, 10, len(json.dumps(value.model_dump())) // 4)
