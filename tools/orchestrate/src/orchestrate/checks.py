"""The orchestrator's own verdict (design §5). Pure code, no model, never the worker's word."""

from __future__ import annotations

import os
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .isolation import worker_env
from .plan import PROTECTED, Check, Task, matches

CHECK_TIMEOUT = 600


@dataclass
class Verdict:
    passed: bool
    reason: str = ""
    command: str = ""
    exit_code: int | None = 0
    output: str = ""
    ran: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _git(worktree: Path, *args: str) -> tuple[int, str]:
    done = subprocess.run(["git", *args], cwd=worktree, capture_output=True, text=True, check=False)
    return done.returncode, (done.stdout + done.stderr).strip()


def out_of_scope(files: list[str], touches: list[str]) -> list[str]:
    bad = []
    for path in files:
        protected = any(matches(path, guard) for guard in PROTECTED)
        if protected or not any(matches(path, pattern) for pattern in touches):
            bad.append(path)
    return bad


def run_command(check: Check, worktree: Path, scratch_url: str, log: Path | None) -> dict:
    env = {**os.environ, **worker_env(scratch_url)}
    try:
        done = subprocess.run(
            check.command, shell=True, cwd=worktree, env=env, capture_output=True, text=True,
            timeout=CHECK_TIMEOUT, encoding="utf-8", errors="replace", check=False,
        )  # fmt: skip
        code, output = done.returncode, done.stdout + done.stderr
    except subprocess.TimeoutExpired as late:
        code, output = None, f"timed out after {CHECK_TIMEOUT}s\n{late.stdout or ''}"
    if log:
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text(f"$ {check.command}\nexit {code}\n\n{output}", encoding="utf-8")
    return {"command": check.command, "exit_code": code, "expected": check.expect_exit,
            "output": output}  # fmt: skip


def judge(task: Task, worktree: Path, base: str, scratch_url: str, logs: Path | None) -> Verdict:
    code, ahead = _git(worktree, "rev-list", "--count", f"{base}..HEAD")
    if code != 0 or not ahead.isdigit() or int(ahead) < 1:
        return Verdict(False, "The branch has no new commit.", exit_code=None, output=ahead)
    _, dirty = _git(worktree, "status", "--porcelain")
    if dirty:
        return Verdict(False, "The worktree has uncommitted changes.", exit_code=None, output=dirty)
    _, names = _git(worktree, "diff", "--name-only", f"{base}...HEAD")
    files = [n for n in names.splitlines() if n.strip()]
    bad = out_of_scope(files, task.touches)
    if bad:
        return Verdict(False, "Files changed outside the task's allowed paths.", exit_code=None,
                       output="\n".join(bad))  # fmt: skip
    ran = []
    for index, check in enumerate([*task.checks, *task.holdout_checks]):
        log = logs / f"check-{index}.log" if logs else None
        result = run_command(check, worktree, scratch_url, log)
        ran.append({k: v for k, v in result.items() if k != "output"})
        if result["exit_code"] != check.expect_exit:
            return Verdict(False, "A check failed.", check.command, result["exit_code"],
                           result["output"][-20000:], ran)  # fmt: skip
    return Verdict(True, "All checks passed.", ran=ran)
