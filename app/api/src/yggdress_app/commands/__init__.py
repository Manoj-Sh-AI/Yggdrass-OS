"""`python -m yggdress_app.commands <group> <verb>`: the app's agent commands, reached through
`yggdras <group> …` (planning/cli-build-spec.md). In-process with YGGDRESS_DATABASE_URL: no
HTTP and no session. The command surface is what an HTTP version would need, so a token-based
transport (N5) can replace this one later without changing commands.

Each module (notes, changes, planning) defines `register(groups, common)`, which adds its
groups and verbs; a verb sets `handler=fn(args) -> contract.Out`."""

from __future__ import annotations

import argparse
import contextlib
import importlib
import io
import os
import sys

from .contract import CliError, Exit, common, render, render_error

MODULES = ("notes", "changes", "planning")
URL_VAR = "YGGDRESS_DATABASE_URL"


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise CliError("usage", message)


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="yggdras", description="App agent commands. `yggdras <group> --help`.")
    groups = parser.add_subparsers(dest="group", required=True, parser_class=_Parser)
    for name in MODULES:
        try:
            module = importlib.import_module(f"{__name__}.{name}")
        except ModuleNotFoundError as missing:
            if missing.name != f"{__name__}.{name}":
                raise
            continue
        module.register(groups, common())
    return parser


def database():
    """The app database, from YGGDRESS_DATABASE_URL (never printed)."""
    from ..database import Database

    url = os.environ.get(URL_VAR, "").strip()
    if not url:
        raise CliError("failed", f"{URL_VAR} is not set")
    return Database(url)


def run(argv: list[str], stdout=None, stderr=None) -> int:
    stdout, stderr = stdout or sys.stdout, stderr or sys.stderr
    as_json = "--json" in argv
    try:
        try:
            with contextlib.redirect_stdout(stdout):
                args = build_parser().parse_args(argv)
        except SystemExit as done:
            return int(done.code or 0)
        out = args.handler(args)
        stdout.write(render(out, args.json))
        return int(Exit.OK)
    except CliError as error:
        stderr.write(render_error(error, as_json))
        return error.code
    except Exception as error:  # noqa: BLE001 -- one line, exit 1, no secrets
        stderr.write(render_error(CliError("failed", type(error).__name__), as_json))
        return int(Exit.FAILED)


def run_captured(argv: list[str]) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    code = run(list(argv), out, err)
    return code, out.getvalue(), err.getvalue()
