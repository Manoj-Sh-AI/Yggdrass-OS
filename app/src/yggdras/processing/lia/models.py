"""The model client (D27): one interface, the model chosen by setting, cost logged per call."""

from __future__ import annotations

import os
import threading
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Protocol

# $ per million tokens: input, output, cache-read multiplier, 1-hour cache-write multiplier.
# From the prompt-caching docs, checked 2026-11-01 (reads 0.05x on Opus 5.5 and Sonnet 5.5).
PRICES = {
    "claude-opus-5-5": (4.00, 20.00, 0.05, 2.0),
    "claude-sonnet-5-5": (2.00, 10.00, 0.05, 2.0),
    "claude-haiku-5-5": (0.10, 0.50, 0.10, 2.0),
}


@dataclass
class Usage:
    model: str
    input_tokens: int = 0
    cache_write: int = 0
    cache_read: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: float = 0.0

    def as_dict(self) -> dict:
        return asdict(self)


def cost_of(model: str, inp: int, write: int, read: int, out: int) -> float:
    p_in, p_out, read_x, write_x = PRICES[model]
    return (inp * p_in + write * p_in * write_x + read * p_in * read_x + out * p_out) / 1e6


@dataclass
class Reply:
    blocks: list[dict]  # the reply's content blocks, as plain dicts (for the trace)
    stop_reason: str
    usage: Usage
    content: Any = None  # the reply's content as the SDK returned it, sent back unchanged

    @property
    def text(self) -> str:
        return "".join(b.get("text", "") for b in self.blocks if b.get("type") == "text")

    @property
    def tool_calls(self) -> list[dict]:
        return [b for b in self.blocks if b.get("type") == "tool_use"]


class ModelClient(Protocol):
    model: str

    def send(
        self,
        *,
        system: list[dict],
        tools: list[dict],
        messages: list[dict],
        max_tokens: int = 4096,
        tool_choice: dict | None = None,
    ) -> Reply: ...


class BudgetStop(RuntimeError):
    """The spend reached the stop line."""


@dataclass
class Budget:
    """Live spend across every call; raises BudgetStop once the stop line is reached."""

    stop_at: float
    spent: float = 0.0
    calls: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def add(self, cost: float) -> None:
        with self._lock:
            self.spent += cost
            self.calls += 1

    def check(self) -> None:
        with self._lock:
            if self.spent >= self.stop_at:
                raise BudgetStop(
                    f"spend ${self.spent:.2f} reached the stop line ${self.stop_at:.2f}"
                )


class AnthropicClient:
    """Claude through the Anthropic SDK. Thinking is left at the model's default (adaptive);
    depth is set with effort, which is the one control on the 5.5 models."""

    def __init__(self, model: str, effort: str = "low", budget: Budget | None = None):
        import anthropic

        if model not in PRICES:
            raise ValueError(f"no price for {model}")
        self.model, self.effort, self.budget = model, effort, budget
        self._client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

    def send(
        self,
        *,
        system: list[dict],
        tools: list[dict],
        messages: list[dict],
        max_tokens: int = 4096,
        tool_choice: dict | None = None,
    ) -> Reply:
        if self.budget:
            self.budget.check()
        start = time.perf_counter()
        response = self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            tools=tools,
            messages=messages,
            output_config={"effort": self.effort},
            **({"tool_choice": tool_choice} if tool_choice else {}),
        )
        u = response.usage
        usage = Usage(
            model=self.model,
            input_tokens=u.input_tokens,
            cache_write=u.cache_creation_input_tokens or 0,
            cache_read=u.cache_read_input_tokens or 0,
            output_tokens=u.output_tokens,
            latency_ms=round((time.perf_counter() - start) * 1000, 1),
        )
        usage.cost_usd = cost_of(
            self.model, usage.input_tokens, usage.cache_write, usage.cache_read, usage.output_tokens
        )
        if self.budget:
            self.budget.add(usage.cost_usd)
        blocks = [b.model_dump(exclude_none=True) for b in response.content]
        return Reply(blocks, response.stop_reason or "", usage, response.content)
