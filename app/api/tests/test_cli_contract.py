"""The app side of the agent-command base (planning/cli-build-spec.md)."""

import json
import re
from pathlib import Path

import pytest

from yggdress_app import commands
from yggdress_app.commands.contract import CliError

# The spec's read rule for the app side, checked in code (a Phase C run broke it and every
# behavioural check still passed): app commands read only the api.* views, never the brain over
# HTTP, and never decide sensitivity in Python. Writes go through the routers' apply_* functions.
RAW_APP = re.compile(
    r"notes_proxy|NotesProxy|verified_note|mobile_policy|\bsensitive\(|urlopen|httpx|requests\."
    r"|\b(FROM|JOIN|UPDATE|INTO)\s+app\.",
    re.IGNORECASE,
)


def test_app_command_modules_read_only_the_api_views():
    folder = Path(commands.__file__).parent
    for name in commands.MODULES:
        path = folder / f"{name}.py"
        if path.exists():
            found = RAW_APP.search(path.read_text(encoding="utf-8"))
            assert found is None, f"{path.name} uses {found.group(0)!r}"


def test_the_raw_app_rule_catches_what_it_should():
    for bad in ("from ..notes_proxy import NotesProxy", "verified_note(client, slug)",
                "from ..mobile_policy import sensitive", "SELECT * FROM app.note_refs",
                "JOIN app.tasks t ON"):  # fmt: skip
        assert RAW_APP.search(bad), bad
    for good in ("SELECT * FROM api.note_refs", "events.read(db, consumer, limit)",
                 "apply_command(database(), command)"):  # fmt: skip
        assert not RAW_APP.search(good), good


def test_usage_errors_are_one_line_and_exit_2():
    for argv in ([], ["nope"]):
        code, out, err = commands.run_captured(argv)
        assert code == 2 and out == "" and err.startswith("error\tusage\t"), argv


def test_json_errors(monkeypatch):
    code, _, err = commands.run_captured(["nope", "--json"])
    assert code == 2 and json.loads(err)["error"] == "usage"


def test_database_needs_the_url_and_never_prints_it(monkeypatch):
    monkeypatch.delenv(commands.URL_VAR, raising=False)
    with pytest.raises(CliError) as caught:
        commands.database()
    assert caught.value.kind == "failed" and "YGGDRESS_DATABASE_URL" in caught.value.message


def test_unexpected_errors_exit_1_with_the_class_name_only(monkeypatch):
    def boom(args):
        raise RuntimeError("postgresql://user:secret@host/db")

    real = commands.build_parser

    def parser():
        p = real()
        sub = next(a for a in p._actions if a.dest == "group")
        sub.add_parser("boom").set_defaults(handler=boom, json=False)
        return p

    monkeypatch.setattr(commands, "build_parser", parser)
    code, _, err = commands.run_captured(["boom"])
    assert code == 1 and err == "error\tfailed\tRuntimeError\n"
