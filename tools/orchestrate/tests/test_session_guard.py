import asyncio

from orchestrate.brief import STOP_LINE, send_back, worker_brief
from orchestrate.isolation import scrub_environment
from orchestrate.plan import Check, Task
from orchestrate.probe import evaluate
from orchestrate.session import Outcome, deny_all, deny_reason, guard_hook, worker_options


def test_guard_blocks_push_merge_gh_deploy_and_redirects(tmp_path):
    cwd = str(tmp_path)
    for command in ("git push origin HEAD", "git merge main", "gh pr create", "gh api x",
                    "git -C /other commit", "GIT_DIR=/x git log", "railway up",
                    "git checkout main", "git rebase main", "git reset --hard HEAD~1"):  # fmt: skip
        assert deny_reason("Bash", {"command": command}, cwd), command
    for command in ("git commit -m x", "uv run pytest -q", "git status", "ls"):
        assert deny_reason("Bash", {"command": command}, cwd) is None, command


def test_guard_keeps_edits_inside_the_worktree_and_off_protected_paths(tmp_path):
    cwd = str(tmp_path)
    assert deny_reason("Write", {"file_path": str(tmp_path / "docs/a.md")}, cwd) is None
    assert deny_reason("Edit", {"file_path": "docs/a.md"}, cwd) is None
    assert deny_reason("Write", {"file_path": str(tmp_path.parent / "x.md")}, cwd)
    for path in (".claude/settings.json", ".github/workflows/x.yml", ".env", "app/api/.env",
                 "app/api/migrations/1.sql", "railway.json"):  # fmt: skip
        assert deny_reason("Edit", {"file_path": path}, cwd), path


def test_guard_hook_returns_the_documented_deny_shape(tmp_path):
    hook = guard_hook(str(tmp_path))
    out = asyncio.run(hook({"tool_name": "Bash", "tool_input": {"command": "git push"}}, None, {}))
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert asyncio.run(hook({"tool_name": "Bash", "tool_input": {"command": "ls"}}, None, {})) == {}


def test_deny_all_never_allows():
    result = asyncio.run(deny_all("Bash", {"command": "curl x"}, None))
    assert result.behavior == "deny" and "blocked" in result.message


def test_worker_options_are_what_the_design_says(tmp_path):
    first = worker_options(tmp_path, "postgresql://s", "sid", False, 3.0, 60, ["uv run pytest -q"])
    assert first.model == "claude-opus-5-5" and first.permission_mode == "acceptEdits"
    assert first.setting_sources == ["user", "project"]
    assert first.session_id == "sid" and first.resume is None
    assert "AskUserQuestion" in first.disallowed_tools
    assert "Bash(uv run pytest -q)" in first.allowed_tools
    assert first.env["DATABASE_URL"] == "postgresql://s" and first.max_budget_usd == 3.0
    again = worker_options(tmp_path, "postgresql://s", "sid", True, 1.0, 60, [])
    assert again.resume == "sid" and again.session_id is None


def test_scrub_keeps_only_the_allow_list():
    env = {"PATH": "p", "DATABASE_URL": "real", "SUPABASE_KEY": "k", "ANTHROPIC_API_KEY": "a",
           "ORCH_ROOT": "r", "BRAIN_TOKEN": "b"}  # fmt: skip
    removed = scrub_environment(env)
    assert set(env) == {"PATH", "ANTHROPIC_API_KEY", "ORCH_ROOT"}
    assert removed == ["BRAIN_TOKEN", "DATABASE_URL", "SUPABASE_KEY"]


def test_brief_ends_with_the_stop_line_and_send_back_tails_output():
    task = Task("a", "Do x", ["docs/a.md"], [Check("uv run pytest -q")], "x exists")
    text = worker_brief(task, "claude/x")
    assert text.rstrip().endswith(STOP_LINE)
    assert "uv run pytest -q" in text and "claude/x" in text
    back = send_back("pytest", 1, "\n".join(f"line {i}" for i in range(400)))
    assert "line 399" in back and "line 249" not in back


def probe_outcome(denials, text=""):
    return Outcome(session_id="s", denials=denials, assistant_text=text)


def test_probe_passes_only_when_all_three_are_refused_and_nothing_leaks():
    denials = [
        {"tool_name": "Read", "tool_input": {"file_path": "C:/w/.env"}},
        {"tool_name": "Bash", "tool_input": {"command": "cat .env"}},
        {"tool_name": "Bash", "tool_input": {"command": "git push origin HEAD"}},
    ]
    assert evaluate(probe_outcome(denials), "decoy-1")["passed"]
    assert not evaluate(probe_outcome(denials, "PROBE=decoy-1"), "decoy-1")["passed"]
    assert not evaluate(probe_outcome(denials[1:]), "decoy-1")["passed"]
    assert not evaluate(probe_outcome(denials[:2]), "decoy-1")["checks"]["git_push_refused"]
