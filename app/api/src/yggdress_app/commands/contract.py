"""The CLI's output and error contract (planning/cli-build-spec.md). Short, exact and
machine-readable: one tab-separated line per result, or one JSON document with --json.
An agent tells "not found" (3) from "not allowed" (4) from "stale" (5) by the exit code alone.

A copy of yggdras.interface.commands.contract (the app never imports the memory package);
app/tests/test_cli_contract.py checks that the two agree."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any


class Exit(IntEnum):
    OK = 0
    FAILED = 1
    USAGE = 2
    NOT_FOUND = 3
    NOT_ALLOWED = 4
    STALE = 5
    INVALID = 6


KIND_EXIT = {
    "failed": Exit.FAILED,
    "usage": Exit.USAGE,
    "not_found": Exit.NOT_FOUND,
    "not_allowed": Exit.NOT_ALLOWED,
    "stale": Exit.STALE,
    "invalid": Exit.INVALID,
}


class CliError(Exception):
    def __init__(self, kind: str, message: str):
        if kind not in KIND_EXIT:
            raise ValueError(f"unknown error kind {kind!r}")
        super().__init__(message)
        self.kind, self.message = kind, message

    @property
    def code(self) -> int:
        return int(KIND_EXIT[self.kind])


def kind_for_status(status: int, message: str = "") -> str:
    """Map an existing HTTP-style error to a kind. 409 means stale only when it is about the
    version ("changed since it was read", "version"); any other 409 is invalid."""
    if status == 404:
        return "not_found"
    if status == 403:
        return "not_allowed"
    if status == 409:
        text = message.lower()
        return "stale" if ("changed" in text or "version" in text) else "invalid"
    if status in (400, 422):
        return "invalid"
    return "failed"


@dataclass
class Out:
    """What a handler returns: `data` for --json, `lines` (tuples) for the default output."""

    data: Any
    lines: list[tuple] = field(default_factory=list)


def common() -> argparse.ArgumentParser:
    """A parent parser every verb uses, so every verb takes --json."""
    parent = argparse.ArgumentParser(add_help=False)
    parent.add_argument("--json", action="store_true", help="one JSON document on stdout")
    return parent


def _cell(value: Any) -> str:
    if value is None:
        return "-"
    # Only lists and dicts are JSON in a cell; a UUID, date or number prints plain (a UUID
    # through json.dumps came out quoted: found when cross-testing the two Phase C runs).
    if isinstance(value, bool):
        text = "true" if value else "false"
    elif isinstance(value, (dict, list, tuple)):
        text = json.dumps(value, default=str)
    else:
        text = str(value)
    return text.replace("\t", " ").replace("\r", " ").replace("\n", "\\n")


def render(out: Out, as_json: bool) -> str:
    if as_json:
        return json.dumps(out.data, ensure_ascii=False, default=str) + "\n"
    return "".join("\t".join(_cell(v) for v in line) + "\n" for line in out.lines)


def render_error(error: CliError, as_json: bool) -> str:
    if as_json:
        return (
            json.dumps({"error": error.kind, "message": error.message}, ensure_ascii=False) + "\n"
        )
    return f"error\t{error.kind}\t{_cell(error.message)}\n"
