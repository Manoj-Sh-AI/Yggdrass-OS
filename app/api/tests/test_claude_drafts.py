"""The owner-installed drafts in planning/claude-drafts behave as documented (items 17, 19, 43, 58, 59)."""

import importlib.util
import json
from pathlib import Path

import pytest

DRAFTS = Path(__file__).resolve().parents[3] / "planning" / "claude-drafts"


def load(name):
    spec = importlib.util.spec_from_file_location(name, DRAFTS / "hooks" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def trim():
    return load("trim_output")


@pytest.mark.parametrize("command", ["uv run pytest -q tests", "npx vitest run", "npm test",
                                     "cd app/web && node node_modules/vitest/vitest.mjs run"])  # fmt: skip
def test_verbose_test_commands_are_cut_to_their_tail_keeping_the_exit_status(trim, command):
    new = trim.rewrite(command)
    assert new.startswith("set -o pipefail; {") and new.endswith("2>&1 | tail -n 80")
    assert command in new


@pytest.mark.parametrize("command", ["git status", "uv run pytest -q | tail -5",
                                     "npx vitest run > out.txt", "ls tests"])  # fmt: skip
def test_other_or_already_short_commands_are_left_alone(trim, command):
    assert trim.rewrite(command) is None


def test_hook_output_keeps_every_field_and_grants_no_permission(trim, capsys, monkeypatch):
    payload = {
        "tool_name": "Bash",
        "tool_input": {"command": "pytest", "description": "Run tests", "timeout": 5},
    }
    monkeypatch.setattr("sys.stdin", __import__("io").StringIO(json.dumps(payload)))
    assert trim.main() == 0
    out = json.loads(capsys.readouterr().out)["hookSpecificOutput"]
    assert out["hookEventName"] == "PreToolUse" and "permissionDecision" not in out
    assert out["updatedInput"]["description"] == "Run tests" and out["updatedInput"]["timeout"] == 5


def test_a_real_failing_run_still_fails_after_rewriting(trim, tmp_path):
    import subprocess

    new = trim.rewrite("pytest; exit 3")
    result = subprocess.run(
        ["bash", "-c", new.replace("pytest; ", "")], capture_output=True, check=False
    )
    assert result.returncode == 3


def test_gate_draft_routes_the_scratch_db_and_drops_real_credentials(monkeypatch):
    gate = load("gate")
    monkeypatch.setenv("DATABASE_URL", "postgresql://real")
    monkeypatch.setenv("GATE_SCRATCH_DB_URL", "postgresql://localhost/yggdress_test_scratch")
    env = gate.clean_env()
    assert "DATABASE_URL" not in env
    assert env["YGGDRESS_TEST_ADMIN_URL"] == "postgresql://localhost/yggdress_test_scratch"
    assert "--timeout=60" in gate.PYTEST_FLAGS and "not flaky and not slow" in gate.PYTEST_FLAGS


def test_gate_draft_skips_on_an_unreachable_scratch_db(monkeypatch):
    gate = load("gate")
    monkeypatch.setenv("GATE_SCRATCH_DB_URL", "postgresql://127.0.0.1:1/yggdress_test_nowhere")
    assert gate.scratch_unreachable() == "GATE_SCRATCH_DB_URL is unreachable"


@pytest.mark.parametrize(("name", "fields"), [("Explore", {"model: haiku", "tools: Read, Grep, Glob"}),
                                              ("refactorer", {"isolation: worktree"})])  # fmt: skip
def test_subagent_drafts_carry_the_documented_fields(name, fields):
    text = (DRAFTS / "agents" / f"{name}.md").read_text(encoding="utf-8")
    front = text.split("---")[1]
    assert f"name: {name}" in front and all(f in front for f in fields)


def test_settings_draft_adds_the_trim_hook_and_keeps_every_gate():
    draft = json.loads((DRAFTS / "settings.json").read_text(encoding="utf-8"))
    current = json.loads(
        (DRAFTS.parents[1] / ".claude" / "settings.json").read_text(encoding="utf-8")
    )
    for event, groups in current["hooks"].items():
        assert all(g in draft["hooks"][event] for g in groups)
    assert any(g["matcher"] == "Bash" and "trim_output.py" in g["hooks"][0]["command"]
               for g in draft["hooks"]["PreToolUse"])  # fmt: skip
