"""Config, worktrees, scratch databases, a clean environment and process-tree kill (design §7)."""

from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path

PLANNER_MODEL = "claude-fable-5-2"
WORKER_MODEL = "claude-opus-5-5"
TASK_QUEUE = "yggdras-session-orchestration"

# Everything else is dropped from the host's own environment before any session starts, because
# the SDK merges `env` on top of the inherited environment and cannot remove a variable.
KEEP = {
    "PATH", "PATHEXT", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "TEMP", "TMP",
    "USERPROFILE", "HOMEDRIVE", "HOMEPATH", "HOME", "APPDATA", "LOCALAPPDATA", "PROGRAMDATA",
    "PROGRAMFILES", "PROGRAMFILES(X86)", "PROGRAMW6432", "COMMONPROGRAMFILES", "USERNAME",
    "COMPUTERNAME", "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE", "OS", "LANG", "LC_ALL",
    "TERM", "ANTHROPIC_API_KEY",
}  # fmt: skip
KEEP_PREFIXES = ("ORCH_",)


@dataclass(frozen=True)
class Config:
    repo: Path
    root: Path
    temporal: str

    @property
    def worktrees(self) -> Path:
        return self.root / "worktrees"

    def run_dir(self, run: str) -> Path:
        return self.root / "runs" / run


def load_config(env: dict[str, str] | None = None) -> Config:
    env = os.environ if env is None else env
    repo = env.get("ORCH_REPO") or _git("rev-parse", "--show-toplevel", cwd=Path.cwd()).strip()
    base = env.get("LOCALAPPDATA") or str(Path.home() / ".local" / "share")
    root = env.get("ORCH_ROOT") or str(Path(base) / "yggdras")
    return Config(Path(repo), Path(root), env.get("ORCH_TEMPORAL", "127.0.0.1:7244"))


def scrub_environment(environ: dict[str, str] | os._Environ = os.environ) -> list[str]:
    """Remove every variable not on the keep list. Returns the names removed."""
    removed = [
        k for k in list(environ) if k.upper() not in KEEP and not k.startswith(KEEP_PREFIXES)
    ]
    for name in removed:
        del environ[name]
    return sorted(removed)


def load_key(environ: dict[str, str] | os._Environ = os.environ) -> bool:
    """Use ANTHROPIC_API_KEY if set; otherwise read it from the file named by ORCH_KEY_FILE,
    so the key never has to pass through a chat or a command line. Never printed."""
    if environ.get("ANTHROPIC_API_KEY"):
        return True
    path = environ.get("ORCH_KEY_FILE")
    if not path or not Path(path).is_file():
        return False
    key = Path(path).read_text(encoding="utf-8-sig").strip()
    if not key:
        return False
    environ["ANTHROPIC_API_KEY"] = key
    return True


def worker_env(scratch_url: str) -> dict[str, str]:
    return {
        "DATABASE_URL": scratch_url,
        "APP_DATABASE_URL": scratch_url,
        "GATE_SCRATCH_DB_URL": scratch_url,
        "YGGDRESS_TEST_ADMIN_URL": scratch_url,
    }


def _git(*args: str, cwd: Path) -> str:
    done = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=False)
    if done.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {done.stderr.strip()[:500]}")
    return done.stdout


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40]


_GIT_LOCK = threading.Lock()


def branch_exists(repo: Path, branch: str) -> bool:
    done = subprocess.run(["git", "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}"],
                          cwd=repo, capture_output=True, check=False)  # fmt: skip
    return done.returncode == 0


def ensure_worktree(config: Config, name: str, branch: str, base: str) -> Path:
    """Create the worktree once; on a retry, reuse what an earlier attempt left.
    Serialized, and --no-track, because parallel `worktree add` fought over .git/config's lock
    (seen in the first live run, 2026-11-23)."""
    path = config.worktrees / name
    with _GIT_LOCK:
        if (path / ".git").exists():
            return path
        config.worktrees.mkdir(parents=True, exist_ok=True)
        _git("worktree", "prune", cwd=config.repo)  # forget a half-made worktree from a failure
        if branch_exists(config.repo, branch):
            _git("worktree", "add", str(path), branch, cwd=config.repo)
        else:
            _git("worktree", "add", "--no-track", str(path), "-b", branch, base, cwd=config.repo)
    return path


def scratch_db(config: Config, name: str, action: str = "up") -> str:
    script = config.repo / "tools" / "scratch_db.py"
    # stderr goes to a file, never a pipe: `pg_ctl start` hands its stderr to the server it
    # starts, so a captured pipe never closes and the call hangs (seen in the first live run).
    config.root.mkdir(parents=True, exist_ok=True)
    log = config.root / f"scratch-{name}-{action}.log"
    with log.open("w", encoding="utf-8") as err:
        done = subprocess.run(
            [sys.executable, str(script), action, name],
            stdout=subprocess.PIPE,
            stderr=err,
            stdin=subprocess.DEVNULL,
            text=True,
            timeout=180,
            check=False,
        )
    if done.returncode != 0:
        detail = log.read_text(encoding="utf-8", errors="replace").strip()[-500:]
        raise RuntimeError(f"scratch_db {action} {name} failed: {detail}")
    return done.stdout.strip()


def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        out = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True, check=False
        ).stdout
        return str(pid) in out
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def kill_tree(pid: int | None) -> None:
    """Stop a process and everything it started (same approach as local_runtime.stop_tree).
    The SDK docs do not say interrupt/disconnect end the CLI subprocess, so we never rely on it."""
    if not pid or not pid_alive(pid):
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/T", "/F", "/PID", str(pid)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=30,
            check=False,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        return
    try:
        os.killpg(os.getpgid(pid), signal.SIGKILL)
    except OSError:
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass


def record_pid(config: Config, run: str, key: str, pid: int | None) -> None:
    """Pids also go to disk: a terminated workflow runs no cleanup (design §10, stop --hard)."""
    folder = config.run_dir(run)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "pids.json"
    data = json.loads(path.read_text()) if path.exists() else {}
    if pid:
        data[key] = pid
    else:
        data.pop(key, None)
    path.write_text(json.dumps(data, indent=1))


def recorded_pids(config: Config, run: str) -> dict[str, int]:
    path = config.run_dir(run) / "pids.json"
    return json.loads(path.read_text()) if path.exists() else {}
