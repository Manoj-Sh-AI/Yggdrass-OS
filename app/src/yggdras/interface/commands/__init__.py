"""`yggdras <group> <verb>`: the agent-facing commands (planning/cli-build-spec.md).

Brain groups run here, in-process (BRAIN_DATABASE_URL). App groups are forwarded unchanged
to `python -m yggdress_app.commands` in the app project, because the app package never
imports this one. One implementation: the CLI and the MCP tool `yggdras_command` both call
`run`.

Each brain module (brain_read, brain_write) defines `register(verbs, common)`, which adds its
verbs to the `brain` group; a verb sets `handler=fn(args) -> contract.Out`."""

from __future__ import annotations

import argparse
import contextlib
import importlib
import io
import os
import shutil
import subprocess
import sys
from pathlib import Path

from yggdras.data.brain_db.db import DatabaseError

from .contract import CliError, Exit, common, render, render_error

BRAIN_MODULES = ("brain_read", "brain_write")
APP_GROUPS = ("notes", "links", "changes", "task", "goal", "project", "block", "event",
              "date-item", "availability")  # fmt: skip
GROUPS = ("brain", *APP_GROUPS)


def app_project() -> Path:
    configured = os.environ.get("YGGDRAS_APP_PROJECT")
    return Path(configured) if configured else Path(__file__).resolve().parents[4] / "api"


class _Parser(argparse.ArgumentParser):
    def error(self, message):  # usage errors follow the contract: one line, exit 2
        raise CliError("usage", message)


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="yggdras", description="Agent commands. `yggdras <group> --help`.")
    groups = parser.add_subparsers(dest="group", required=True, parser_class=_Parser)
    brain = groups.add_parser("brain", help="read and write the brain (api.* views only)")
    verbs = brain.add_subparsers(dest="verb", required=True, parser_class=_Parser)
    for name in BRAIN_MODULES:
        try:
            module = importlib.import_module(f"{__name__}.{name}")
        except ModuleNotFoundError as missing:
            if missing.name != f"{__name__}.{name}":
                raise
            continue
        module.register(verbs, common())
    for name in APP_GROUPS:  # listed for --help; the work happens in the app project
        groups.add_parser(name, help=f"app: `yggdras {name} --help`", add_help=False)
    return parser


def forward(argv: list[str], stdout, stderr) -> int:
    uv = shutil.which("uv")
    if not uv:
        stderr.write(render_error(CliError("failed", "uv not found: cannot reach the app"), False))
        return int(Exit.FAILED)
    done = subprocess.run(
        [uv, "run", "--quiet", "--project", str(app_project()), "python", "-m",
         "yggdress_app.commands", *argv],
        capture_output=True, text=True, encoding="utf-8", errors="replace", check=False,
        stdin=subprocess.DEVNULL,
    )  # fmt: skip
    stdout.write(done.stdout)
    stderr.write(done.stderr)
    return done.returncode


def run(argv: list[str], stdout=None, stderr=None) -> int:
    stdout, stderr = stdout or sys.stdout, stderr or sys.stderr
    as_json = "--json" in argv
    if argv[:1] and argv[0] in APP_GROUPS:
        return forward(argv, stdout, stderr)
    try:
        try:
            with contextlib.redirect_stdout(stdout):  # --help goes to the caller's stream
                args = build_parser().parse_args(argv)
        except SystemExit as done:  # --help
            return int(done.code or 0)
        out = args.handler(args)
        stdout.write(render(out, args.json))
        return int(Exit.OK)
    except CliError as error:
        stderr.write(render_error(error, as_json))
        return error.code
    except DatabaseError as error:  # its message never holds the URL (db.py), so show it
        stderr.write(render_error(CliError("failed", str(error)), as_json))
        return int(Exit.FAILED)
    except Exception as error:  # noqa: BLE001 -- the contract: one line, exit 1, no secrets
        stderr.write(render_error(CliError("failed", type(error).__name__), as_json))
        return int(Exit.FAILED)


def run_captured(argv: list[str]) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    code = run(list(argv), out, err)
    return code, out.getvalue(), err.getvalue()


def main(argv: list[str]) -> int:
    return run(argv)
