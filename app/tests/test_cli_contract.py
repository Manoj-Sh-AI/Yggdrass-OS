"""The agent-command base (planning/cli-build-spec.md): contract, dispatch, forwarding, MCP."""

import ast
import io
import json
import re
import subprocess
from pathlib import Path

from yggdras.interface import cli, commands
from yggdras.interface.commands import contract
from yggdras.interface.mcp_server import command_text

APP_CONTRACT = Path(__file__).resolve().parents[1] / "api/src/yggdress_app/commands/contract.py"


def code_without_docstring(path: Path) -> str:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    tree.body = tree.body[1:]  # the module docstring differs on purpose
    return ast.unparse(tree)


RAW_BRAIN = re.compile(
    r"brain\.(notes|note_bodies|relationships|note_areas|areas|aliases|verbs)\b"
    r"|brain_db\.api|brain_db import api|/api/(note|tree|search|version)|brain_api"
)


def test_brain_command_modules_read_only_the_api_views():
    """The spec's rule, checked in code: brain commands never name a brain table, the
    brain_db.api readers or the brain HTTP API (they read api.brain_* views; writes go
    through BrainWrites)."""
    folder = Path(commands.__file__).parent
    for name in commands.BRAIN_MODULES:
        path = folder / f"{name}.py"
        if path.exists():
            found = RAW_BRAIN.search(path.read_text(encoding="utf-8"))
            assert found is None, f"{path.name} names {found.group(0)!r}"


def test_the_raw_brain_rule_catches_what_it_should():
    for bad in ("SELECT * FROM brain.notes", "from yggdras.data.brain_db import api",
                "GET /api/note/x", "brain_db.api.search(conn, q)"):  # fmt: skip
        assert RAW_BRAIN.search(bad), bad
    for good in ("SELECT * FROM api.brain_notes", "api.brain_note_access(%s)",
                 "from yggdras.data.brain_db.writes import BrainWrites"):  # fmt: skip
        assert not RAW_BRAIN.search(good), good


def test_the_two_contract_copies_agree():
    here = Path(contract.__file__)
    assert code_without_docstring(here) == code_without_docstring(APP_CONTRACT)


def test_exit_codes_and_status_mapping():
    assert [int(e) for e in contract.Exit] == [0, 1, 2, 3, 4, 5, 6]
    assert contract.kind_for_status(404) == "not_found"
    assert contract.kind_for_status(403) == "not_allowed"
    assert contract.kind_for_status(409, "'x' changed since it was read") == "stale"
    assert contract.kind_for_status(409, "a note 'x' exists already") == "invalid"
    assert contract.kind_for_status(422) == "invalid"
    assert contract.kind_for_status(500) == "failed"
    assert contract.CliError("stale", "m").code == 5


def test_scalars_print_plain_in_a_cell():
    from datetime import date
    from uuid import UUID

    u = UUID("5c5ed251-825b-4096-a87e-873924fb6f87")
    line = contract.render(contract.Out(None, [(u, date(2030, 1, 2), 3, True, ["a"])]), False)
    assert line == f'{u}\t2030-01-02\t3\ttrue\t["a"]\n'


def test_output_is_tab_lines_or_json():
    out = contract.Out({"a": 1}, [("ok", "x\ty", None, 3)])
    assert contract.render(out, False) == "ok\tx y\t-\t3\n"
    assert json.loads(contract.render(out, True)) == {"a": 1}
    err = contract.CliError("not_found", "no live note 'x'")
    assert contract.render_error(err, False) == "error\tnot_found\tno live note 'x'\n"
    assert json.loads(contract.render_error(err, True)) == {
        "error": "not_found",
        "message": "no live note 'x'",
    }


def test_usage_errors_are_one_line_and_exit_2():
    for argv in (["nope"], ["brain"], ["brain", "no-such-verb"]):
        code, out, err = commands.run_captured(argv)
        assert code == 2 and out == "" and err.startswith("error\tusage\t"), argv
        assert err.count("\n") == 1


def test_a_missing_database_says_which_variable_and_never_the_url(monkeypatch):
    from yggdras import config

    monkeypatch.delenv("BRAIN_DATABASE_URL", raising=False)
    monkeypatch.setattr(config, "load_env_file", lambda *a, **k: None)
    code, out, err = commands.run_captured(["brain", "tree"])
    assert (code, out) == (1, "")
    assert err == "error\tfailed\tBRAIN_DATABASE_URL is not set (put it in the .env file)\n"


def test_help_goes_to_the_callers_stream():
    code, out, _ = commands.run_captured(["brain", "--help"])
    assert code == 0 and "usage: yggdras brain" in out


def test_app_groups_are_forwarded_unchanged(monkeypatch):
    seen = {}

    def fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 3, "", "error\tnot_found\tx\n")

    monkeypatch.setattr(commands.subprocess, "run", fake_run)
    monkeypatch.setattr(commands.shutil, "which", lambda name: "uv")
    err = io.StringIO()
    code = commands.run(["task", "update", "abc", "--version", "2"], io.StringIO(), err)
    assert code == 3 and err.getvalue() == "error\tnot_found\tx\n"
    cmd = seen["cmd"]
    assert cmd[-6:] == ["yggdress_app.commands", "task", "update", "abc", "--version", "2"]
    assert Path(cmd[cmd.index("--project") + 1]).as_posix().endswith("app/api")


def test_the_yggdras_command_routes_agent_groups(monkeypatch):
    seen = []
    monkeypatch.setattr(commands, "main", lambda argv: seen.append(argv) or 0)
    assert cli.main(["brain", "tree"]) == 0
    assert seen == [["brain", "tree"]]


def test_the_mcp_tool_is_the_same_code(monkeypatch):
    monkeypatch.setattr(commands, "run_captured", lambda argv: (0, "ok\tx\n", ""))
    assert command_text(["brain", "tree"]) == "exit 0\nok\tx\n"
    assert command_text(["rm", "-rf"]).startswith("exit 2\nerror\tusage\t")
    assert command_text([]).startswith("exit 2\n")


def test_the_mcp_tool_never_writes(monkeypatch):
    ran = []
    monkeypatch.setattr(commands, "run_captured", lambda argv: ran.append(argv) or (0, "", ""))
    for argv in (["brain", "add-fact", "x", "a line", "--version", "1"], ["brain", "undo", "u1"],
                 ["task", "create", "--set", "title=x"], ["changes", "read", "me"],
                 ["event", "remove", "e1", "--version", "2"]):  # fmt: skip
        assert command_text(argv).startswith("exit 4\nerror\tnot_allowed\t"), argv
    assert ran == []
    assert command_text(["notes", "find", "garden", "--json"]).startswith("exit 0")
    assert command_text(["task", "--help"]).startswith("exit 0")  # help is fine
