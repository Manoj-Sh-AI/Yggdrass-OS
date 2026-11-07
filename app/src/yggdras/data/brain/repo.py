"""Git and the write lock for the brain repo (D36). Lia commits; she never pushes."""

from __future__ import annotations

import os
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path

STALE_LOCK_S = 600


class RepoError(RuntimeError):
    pass


class Busy(RuntimeError):
    """Another write holds the lock."""


def git(repo: Path, *args: str, check: bool = True) -> str:
    out = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if check and out.returncode != 0:
        raise RepoError(f"git {' '.join(args)}: {out.stderr.strip() or out.stdout.strip()}")
    return out.stdout


def dirty(repo: Path, paths: list[str], ignore: list[str]) -> list[str]:
    """Uncommitted changes (tracked or not) under *paths*, minus those under *ignore*."""
    out = git(repo, "status", "--porcelain", "--untracked-files=all", "--", *paths)
    found = []
    for line in out.splitlines():
        path = line[3:].strip().strip('"')
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        if not any(path == i or path.startswith(i.rstrip("/") + "/") for i in ignore):
            found.append(path)
    return found


def head(repo: Path) -> str:
    return git(repo, "rev-parse", "HEAD").strip()


def commit(repo: Path, paths: list[str], message: str) -> str:
    """Stage exactly *paths* (written, moved or removed) and commit them."""
    git(repo, "add", "-A", "--", *paths)
    git(repo, "commit", "-q", "-m", message, "--", *paths)
    return head(repo)


def changed_files(repo: Path, sha: str) -> list[str]:
    out = git(repo, "show", "--name-only", "--pretty=format:", sha)
    return [p for p in out.splitlines() if p.strip()]


def later_commits(repo: Path, sha: str, paths: list[str]) -> list[str]:
    """Commits after *sha* that touched any of *paths* ("<short sha> <subject>")."""
    if not paths:
        return []
    out = git(repo, "log", "--format=%h %s", f"{sha}..HEAD", "--", *paths)
    return [ln for ln in out.splitlines() if ln.strip()]


def subject(repo: Path, sha: str) -> str:
    return git(repo, "log", "-1", "--format=%s", sha).strip()


@contextmanager
def write_lock(folder: Path):
    """One write at a time, across processes: an exclusive lock file. A lock older than
    STALE_LOCK_S is taken over (its writer died)."""
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "write.lock"
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        if time.time() - path.stat().st_mtime < STALE_LOCK_S:
            raise Busy("another change is being written; try again in a moment") from None
        path.unlink(missing_ok=True)
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    try:
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        yield
    finally:
        path.unlink(missing_ok=True)
