import subprocess

from orchestrate.checks import judge, out_of_scope
from orchestrate.plan import Check, Task


def git(repo, *args):
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def repo_with_branch(tmp_path, files):
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "config", "user.email", "t@example.invalid")
    git(tmp_path, "config", "user.name", "t")
    (tmp_path / "README.md").write_text("x")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-qm", "base")
    git(tmp_path, "checkout", "-qb", "work")
    for name, text in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    if files:
        git(tmp_path, "add", ".")
        git(tmp_path, "commit", "-qm", "work")
    return tmp_path


def task(touches, checks, holdout=()):
    return Task("a", "x", touches, [Check(c) for c in checks], "x", [], [Check(c) for c in holdout])


def test_scope():
    assert out_of_scope(["docs/a.md"], ["docs/*"]) == []
    assert out_of_scope(["docs/a.md", "app/x.py"], ["docs/*"]) == ["app/x.py"]
    assert out_of_scope([".claude/settings.json"], ["**"]) == [".claude/settings.json"]


def test_no_commit_fails(tmp_path):
    repo = repo_with_branch(tmp_path, {})
    verdict = judge(task(["docs/*"], ["exit 0"]), repo, "main", "postgresql://none", None)
    assert not verdict.passed and "no new commit" in verdict.reason


def test_out_of_scope_fails(tmp_path):
    repo = repo_with_branch(tmp_path, {"docs/a.md": "x", "app/b.py": "y"})
    verdict = judge(task(["docs/*"], ["exit 0"]), repo, "main", "postgresql://none", None)
    assert not verdict.passed and "app/b.py" in verdict.output


def test_dirty_tree_fails(tmp_path):
    repo = repo_with_branch(tmp_path, {"docs/a.md": "x"})
    (repo / "docs/a.md").write_text("changed")
    verdict = judge(task(["docs/*"], ["exit 0"]), repo, "main", "postgresql://none", None)
    assert not verdict.passed and "uncommitted" in verdict.reason


def test_checks_run_in_the_worktree_with_the_scratch_url(tmp_path):
    repo = repo_with_branch(tmp_path, {"docs/a.md": "x"})
    probe = "python -c \"import os,sys; sys.exit(0 if os.environ['DATABASE_URL']=='postgresql://s' else 3)\""
    logs = tmp_path / "logs"
    verdict = judge(task(["docs/*"], ["git log -1", probe]), repo, "main", "postgresql://s", logs)
    assert verdict.passed, verdict
    assert (logs / "check-1.log").read_text().startswith("$ python")


def test_failing_and_holdout_checks_report_the_command(tmp_path):
    repo = repo_with_branch(tmp_path, {"docs/a.md": "x"})
    verdict = judge(task(["docs/*"], ["exit 0"], holdout=["echo nope && exit 4"]), repo, "main",
                    "postgresql://s", None)  # fmt: skip
    assert not verdict.passed
    assert verdict.command == "echo nope && exit 4" and verdict.exit_code == 4
    assert "nope" in verdict.output
