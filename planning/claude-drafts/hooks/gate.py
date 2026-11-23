"""Verification gates for agent sessions (planning/agentic-engineering.md, Stage 2).

One module, one subcommand per gate; the .sh files beside it are the names the plan uses.
Exit contract (documented hook semantics):
  exit 2 + stderr  -> the code is wrong; the tool call / task / turn is blocked
  exit 0 + JSON {"systemMessage": ...} -> a tooling failure; never read as "your code is wrong"
Gates never use the real DATABASE_URL or brain credentials: tests run on the throwaway
cluster in app/api/tests/postgres_fixture.py, and those variables are removed here.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path(__file__).resolve().parents[2])
API = ROOT / "app" / "api"
STATE = ROOT / ".claude" / "state"
PROTECTED = (".claude/", ".github/", "railway.json", "railway.toml", "Dockerfile.backend")
SECRET_ENV = ("DATABASE_URL", "ADMIN_DATABASE_URL", "BRAIN_SERVER_URL", "BRAIN_API_USER",
              "BRAIN_API_PASSWORD", "ANTHROPIC_API_KEY")  # fmt: skip
# Item 19: deterministic gates. --timeout needs pytest-timeout (dev dependency since
# 2026-11-22); -p no:randomly is harmless when pytest-randomly is absent.
PYTEST_FLAGS = ["-q", "-p", "no:cacheprovider", "-p", "no:randomly", "--color=no",
                "--timeout=60", "-m", "not flaky and not slow"]  # fmt: skip
FULL_TIER_TRIGGERS = ("app/api/migrations/", "pyproject.toml", "conftest.py", ".env")


def payload() -> dict:
    try:
        return json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        return {}


def skip(message: str) -> int:
    print(json.dumps({"systemMessage": f"Gate skipped (tooling, not your code): {message}"}))
    return 0


def block(message: str) -> int:
    print(message[:4000], file=sys.stderr)
    return 2


def clean_env() -> dict:
    env = {k: v for k, v in os.environ.items() if k not in SECRET_ENV}
    env.update(PYTHONHASHSEED="0", YGGDRAS_FAKE_MODEL="1")
    # Item 17: an explicit scratch database for gates (tools/scratch-db.sh prints one).
    # Without it the fixture starts its own throwaway cluster, so workers never share one.
    scratch = os.environ.get("GATE_SCRATCH_DB_URL", "").strip()
    if scratch:
        env["YGGDRESS_TEST_ADMIN_URL"] = scratch
    else:
        env.pop("YGGDRESS_TEST_ADMIN_URL", None)
    return env


def scratch_unreachable() -> str:
    """A wrong GATE_SCRATCH_DB_URL is a tooling problem, never 'your code is wrong'."""
    scratch = os.environ.get("GATE_SCRATCH_DB_URL", "").strip()
    if not scratch:
        return ""
    probe = run(["uv", "run", "--no-sync", "python", "-c",
                 "import sys,psycopg;psycopg.connect(sys.argv[1],connect_timeout=3).close()", scratch],
                API, 20)  # fmt: skip
    return "" if probe is not None and probe.returncode == 0 else "GATE_SCRATCH_DB_URL is unreachable"


def run(cmd: list[str], cwd: Path, timeout: int) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run(cmd, cwd=cwd, env=clean_env(), capture_output=True, text=True,
                              timeout=timeout, encoding="utf-8", errors="replace")  # fmt: skip
    except (OSError, subprocess.TimeoutExpired):
        return None


def rel(path: str) -> str:
    """Repo-relative POSIX path from a Windows, Git-Bash (/c/...) or relative path."""
    text = path.replace("\\", "/")
    match = re.match(r"^/([a-zA-Z])/(.*)$", text)
    if match:
        text = f"{match.group(1)}:/{match.group(2)}"
    root = ROOT.resolve().as_posix().rstrip("/")
    candidate = Path(text) if Path(text).is_absolute() else ROOT / text
    full = candidate.resolve().as_posix()
    if full.lower().startswith(root.lower() + "/"):
        return full[len(root) + 1 :]
    return text.lstrip("./")


def changed_files() -> list[str]:
    out = run(["git", "status", "--porcelain", "--untracked-files=all"], ROOT, 20)
    if out is None or out.returncode:
        return []
    return [line[3:].strip().strip('"') for line in out.stdout.splitlines() if line.strip()]


# ---- PreToolUse: the agent cannot rewrite its own gate --------------------------------
def protect() -> int:
    data = payload()
    path = (data.get("tool_input") or {}).get("file_path") or ""
    target = rel(path) if path else ""
    if any(target == p or target.startswith(p) for p in PROTECTED):
        return block(f"Protected path: {target}. Gates, CI and deploy config are edited by Manoj, "
                     "not by an agent (planning/agentic-engineering.md item 13).")  # fmt: skip
    return 0


# ---- T1: one changed Python file -------------------------------------------------------
def t1_python() -> int:
    path = (payload().get("tool_input") or {}).get("file_path") or ""
    if not path.endswith(".py") or not (API in Path(path).resolve().parents):
        return 0
    fmt = run(["uv", "run", "--no-sync", "ruff", "format", path], API, 20)
    check = run(["uv", "run", "--no-sync", "ruff", "check", "--fix", "--output-format", "concise", path], API, 20)  # fmt: skip
    if fmt is None or check is None:
        return skip("ruff could not run")
    if check.returncode:
        first = next((l for l in check.stdout.splitlines() if ":" in l), check.stdout.strip())
        return block(f"ruff: {first}")
    return 0


# ---- T1: TypeScript (token lint is instant; tsc is the project check) -------------------
def t1_ts() -> int:
    path = (payload().get("tool_input") or {}).get("file_path") or ""
    web = ROOT / "app" / "web"
    if not path.endswith((".ts", ".tsx")) or web not in Path(path).resolve().parents:
        return 0
    lint = run(["node", "scripts/lint-tokens.mjs"], web, 20)
    if lint is None:
        return skip("node could not run")
    if lint.returncode or "warning" in lint.stdout.lower() + lint.stderr.lower():
        return block("Token lint: " + (lint.stderr or lint.stdout).strip()[:1500])
    return 0


# ---- T2: once per completed task --------------------------------------------------------
def selected_tests(files: list[str]) -> list[str]:
    tests = set()
    for f in files:
        p = Path(f)
        if f.startswith("app/api/tests/") and p.name.startswith("test_") and p.suffix == ".py":
            tests.add(p.as_posix().removeprefix("app/api/"))
        elif f.startswith("app/api/src/") and p.suffix == ".py":
            stem = p.parent.name if p.stem == "__init__" else p.stem
            for t in (API / "tests").glob(f"test_*{stem}*.py"):
                tests.add(f"tests/{t.name}")
            if "conductor" in p.parts:
                tests.update(f"tests/{t.name}" for t in (API / "tests").glob("test_conductor_*.py"))
    return sorted(tests)


def migration_problems(files: list[str]) -> list[str]:
    problems = []
    names = [p.name for p in (API / "migrations").glob("*.sql")]
    prefixes = [n.split("_", 1)[0] for n in names]
    duplicates = sorted({p for p in prefixes if prefixes.count(p) > 1})
    if duplicates:
        problems.append(f"Two migrations share a number: {', '.join(duplicates)} (rename one; numbers are the order).")
    tracked = run(["git", "ls-files", "app/api/migrations"], ROOT, 20)
    committed = set(tracked.stdout.split()) if tracked else set()
    edited = [f for f in files if f in committed and f.endswith(".sql")]
    if edited:
        problems.append(f"A committed migration was edited: {', '.join(edited)}. Applied migrations are "
                        "checksummed; add a new migration instead (expand-contract, AGENTS.md).")  # fmt: skip
    return problems


def t2() -> int:
    data = payload()
    subject = data.get("task_subject") or "this task"
    files = changed_files()
    code = [f for f in files if f.startswith("app/") and not re.search(r"(^|/)tests?/", f)]
    tests_changed = [f for f in files if re.search(r"(^|/)tests?/", f)]
    if tests_changed and not code:
        return block(f"Task '{subject}': only tests changed ({', '.join(tests_changed[:5])}). "
                     "Changing tests without code is the edited-test failure mode; explain or revert.")  # fmt: skip
    problems = migration_problems(files)
    if problems:
        return block(f"Task '{subject}': " + " ".join(problems))
    py = [f for f in files if f.startswith("app/api/") and f.endswith(".py")]
    if not py:
        return 0
    if any(f.startswith(FULL_TIER_TRIGGERS) or Path(f).name in ("pyproject.toml", "conftest.py") for f in files):
        return skip("migration/config change: needs the full suite (run full-suite-async.sh or CI)")
    unreachable = scratch_unreachable()
    if unreachable:
        return skip(unreachable)
    tests = selected_tests(py)
    if not tests:
        return block(f"Task '{subject}': Python changed ({', '.join(py[:4])}) but no test was selected. "
                     "Add or name a test for it.")  # fmt: skip
    result = run(["uv", "run", "--no-sync", "pytest", *PYTEST_FLAGS, *tests], API, 170)
    if result is None:
        return skip("pytest could not run in time")
    if result.returncode == 5:
        return block(f"Task '{subject}': the selected tests collected nothing: {' '.join(tests)}")
    if result.returncode:
        tail = "\n".join(result.stdout.strip().splitlines()[-25:])
        return block(f"Task '{subject}': tests failed ({' '.join(tests)}):\n{tail}")
    return 0


# ---- T3: Stop, cheap, with the documented loop guard -------------------------------------
def t3() -> int:
    data = payload()
    if data.get("stop_hook_active") or data.get("background_tasks"):
        return 0
    lint = run(["uv", "run", "--no-sync", "ruff", "check", "."], API, 60)
    if lint is None:
        return skip("ruff could not run")
    if lint.returncode:
        first = next((l for l in lint.stdout.splitlines() if ":" in l), "ruff failed")
        print(json.dumps({"decision": "block", "reason": f"Lint fails repo-wide: {first}"}))
        return 0
    verdict = STATE / "last-full-run.json"
    if verdict.exists():
        try:
            last = json.loads(verdict.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return 0
        if last.get("status") == "failed" and time.time() - last.get("at", 0) < 6 * 3600:
            print(json.dumps({"decision": "block",
                              "reason": f"The last full suite failed: {last.get('summary', '')[:500]}"}))  # fmt: skip
    return 0


# ---- the full suite, in the background; T3 reads its verdict ------------------------------
def full_suite() -> int:
    STATE.mkdir(parents=True, exist_ok=True)
    start = time.time()
    result = run(["uv", "run", "--no-sync", "pytest", *PYTEST_FLAGS], API, 3600)
    summary = (result.stdout.strip().splitlines() or ["no output"])[-1] if result else "did not finish"
    status = "passed" if result is not None and result.returncode == 0 else "failed"
    (STATE / "last-full-run.json").write_text(json.dumps(
        {"status": status, "summary": summary, "at": time.time(), "seconds": round(time.time() - start)}),
        encoding="utf-8")  # fmt: skip
    return 0


if __name__ == "__main__":
    commands = {"protect": protect, "t1-python": t1_python, "t1-ts": t1_ts, "t2": t2, "t3": t3,
                "full-suite": full_suite}  # fmt: skip
    try:
        sys.exit(commands[sys.argv[1]]())
    except Exception as error:  # noqa: BLE001 - a crashing gate must never block work
        sys.exit(skip(f"{type(error).__name__} in gate {sys.argv[1:]}"))
