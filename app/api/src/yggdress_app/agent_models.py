"""Private, bounded Claude Messages transport. No implicit paid retries."""

import json
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener

from .notes_proxy import NoRedirect


class AgentError(Exception):
    pass


@dataclass(frozen=True)
class ModelReply:
    content: list
    input_tokens: int = 0
    output_tokens: int = 0


class Claude:
    def __init__(self, key, model, *, opener=None):
        if not key or not model or len(model) > 100:
            raise ValueError("Configure the model and private Anthropic credential.")
        self._key, self.model = key, model
        self.opener = opener or build_opener(NoRedirect())

    def complete(self, system, messages, tools):
        payload = {"model": self.model, "max_tokens": 2048, "system": system, "messages": messages}
        if tools:
            payload.update(
                tools=tools, tool_choice={"type": "auto", "disable_parallel_tool_use": True}
            )
        data = json.dumps(payload, ensure_ascii=False).encode()
        if len(data) > 240000:
            raise AgentError("The selected context is too large. Narrow this request.")
        request = Request(
            "https://api.anthropic.com/v1/messages",
            data=data,
            headers={
                "x-api-key": self._key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
        )
        try:
            with self.opener.open(request, timeout=60) as response:
                raw = response.read(500001)
            if len(raw) > 500000:
                raise AgentError("The model response exceeded the allowed size.")
            out = json.loads(raw)
            if out.get("stop_reason") in ("max_tokens", "refusal", "pause_turn"):
                raise AgentError("The model did not finish this step. No changes were applied.")
            content = out["content"]
            if not isinstance(content, list) or not content:
                raise ValueError
            usage = out.get("usage", {})
            return ModelReply(content, usage.get("input_tokens", 0), usage.get("output_tokens", 0))
        except HTTPError as error:
            message = (
                "The model provider rejected this request. Check the backend model configuration."
            )
            if error.code == 429:
                message = (
                    "The model provider is busy or its usage limit was reached. Try again later."
                )
            raise AgentError(message) from None
        except (URLError, TimeoutError, OSError):
            raise AgentError(
                "The model connection was interrupted. It was not retried automatically."
            ) from None
        except (ValueError, KeyError, TypeError):
            raise AgentError(
                "The model returned an unreadable response. No changes were applied."
            ) from None


class RoutedClaude:
    """Claude with a model per step (orchestration: router, planner, helpers each choose)."""

    ALLOWED = ("claude-haiku-5-5", "claude-sonnet-5-5")

    def __init__(self, key, default="claude-sonnet-5-5", *, opener=None):
        self._key, self.default, self.opener = key, default, opener

    def for_agent(self, agent):
        return self

    def with_model(self, model):
        if model not in self.ALLOWED:
            raise AgentError("The plan chose a model that is not allowed.")
        return Claude(self._key, model, opener=self.opener)

    def complete(self, system, messages, tools):
        return Claude(self._key, self.default, opener=self.opener).complete(system, messages, tools)


class NoModel:
    """Until ANTHROPIC_API_KEY is configured: every model step fails plainly, nothing is spent."""

    def for_agent(self, agent):
        return self

    def with_model(self, model):
        return self

    def complete(self, system, messages, tools):
        raise AgentError("Yggdras's model is not configured (ANTHROPIC_API_KEY).")
