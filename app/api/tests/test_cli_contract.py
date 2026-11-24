"""The app side of the agent-command base (planning/cli-build-spec.md)."""

import json

import pytest

from yggdress_app import commands
from yggdress_app.commands.contract import CliError


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
