"""ensure_worktree against a real local git repo (no network)."""

import subprocess
from concurrent.futures import ThreadPoolExecutor

from orchestrate.isolation import Config, ensure_worktree


def git(repo, *args):
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def make_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.email", "t@example.invalid")
    git(repo, "config", "user.name", "t")
    (repo / "a.txt").write_text("x")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "base")
    return Config(repo, tmp_path / "root", "127.0.0.1:1")


def test_parallel_worktrees_do_not_collide(tmp_path):
    config = make_repo(tmp_path)
    with ThreadPoolExecutor(4) as pool:
        paths = list(
            pool.map(lambda i: ensure_worktree(config, f"w{i}", f"b{i}", "main"), range(4))
        )
    assert all((p / "a.txt").exists() for p in paths)
    assert "branch.b0" not in git(config.repo, "config", "--list").stdout  # --no-track


def test_retry_after_a_half_made_worktree_reuses_the_branch(tmp_path):
    config = make_repo(tmp_path)
    git(config.repo, "branch", "b1", "main")  # an earlier attempt created the branch, then failed
    path = ensure_worktree(config, "w1", "b1", "main")
    assert git(path, "branch", "--show-current").stdout.strip() == "b1"
    assert ensure_worktree(config, "w1", "b1", "main") == path  # idempotent
