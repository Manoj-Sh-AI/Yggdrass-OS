"""Writes one run's changes to the log efficiently.

Token deltas arrive dozens of times a second; writing each would mean a connection,
a row lock and a snapshot rewrite per token. The recorder coalesces consecutive text
deltas for the same path and flushes them at most every `flush_seconds`. Structural
changes (`set`) flush pending text first and are written immediately, so order is kept.
Each flush also refreshes the run's heartbeat.
"""

from __future__ import annotations

import threading
import time
from typing import Any

from .log import Op, Path, RunLog, append_text, set_


class Recorder:
    def __init__(self, log: RunLog, run_id: str, owner: str, flush_seconds: float = 0.12):
        self.log, self.run_id, self.owner = log, run_id, owner
        self.flush_seconds = flush_seconds
        self._lock = threading.RLock()
        self._pending: list[Op] = []
        self._last_flush = time.monotonic()

    def text(self, path: Path, delta: str) -> None:
        if not delta:
            return
        with self._lock:
            last = self._pending[-1] if self._pending else None
            if last is not None and last.op == "append-text" and last.path == path:
                self._pending[-1] = append_text(path, last.value + delta)
            else:
                self._pending.append(append_text(path, delta))
            if time.monotonic() - self._last_flush >= self.flush_seconds:
                self._flush()

    def set(self, path: Path, value: Any) -> None:
        with self._lock:
            self._pending.append(set_(path, value))
            self._flush()

    def sets(self, changes: list[tuple[Path, Any]]) -> None:
        """Several changes that must land together (one seq range, one transaction)."""
        with self._lock:
            self._pending.extend(set_(p, v) for p, v in changes)
            self._flush()

    def flush(self) -> None:
        with self._lock:
            self._flush()

    def _flush(self) -> None:
        if self._pending:
            ops, self._pending = self._pending, []
            self.log.append(self.run_id, ops, owner=self.owner)
        self._last_flush = time.monotonic()
