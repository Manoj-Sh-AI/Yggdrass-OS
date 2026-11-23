"""Briefs, send-backs and the two JSON schemas (design §2-§4). Filled by code, never by a model."""

from __future__ import annotations

from .plan import Task

STOP_LINE = (
    "If you can't reach something you need, say exactly what's missing in your first message "
    "and stop. Don't substitute, mock, or guess."
)

RESULT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["status", "summary", "branch", "commits", "files_changed", "evidence", "missing"],
    "properties": {
        "status": {"enum": ["done", "failed", "blocked"]},
        "summary": {"type": "string", "description": "at most 5 sentences"},
        "branch": {"type": "string"},
        "commits": {"type": "array", "items": {"type": "string"}},
        "files_changed": {"type": "array", "items": {"type": "string"}},
        "evidence": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["command", "exit_code", "output_tail"],
                "properties": {
                    "command": {"type": "string"},
                    "exit_code": {"type": "integer"},
                    "output_tail": {"type": "string", "description": "last 30 lines"},
                },
            },
        },
        "missing": {"type": "string", "description": "only when blocked: exactly what is needed"},
    },
}

_CHECK = {
    "type": "object",
    "additionalProperties": False,
    "required": ["command"],
    "properties": {"command": {"type": "string"}, "expect_exit": {"type": "integer"}},
}

PLAN_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["tasks"],
    "properties": {
        "tasks": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "objective", "touches", "checks", "done_means", "depends_on"],
                "properties": {
                    "id": {"type": "string"},
                    "objective": {"type": "string"},
                    "touches": {"type": "array", "items": {"type": "string"}},
                    "checks": {"type": "array", "items": _CHECK},
                    "done_means": {"type": "string"},
                    "depends_on": {"type": "array", "items": {"type": "string"}},
                },
            },
        }
    },
}

PLANNER_SYSTEM = (
    "You split a software job on the Yggdras repo into independent tasks for worker sessions. "
    "You never write code. Read only what you need. Each task needs: a short lowercase slug id; "
    "an objective; `touches`, the path globs it may change (as narrow as possible); `checks`, "
    "shell commands run from the repo root whose exit code proves it done; a one-sentence "
    "done_means; and depends_on. If you cannot write a command that proves a task done, leave "
    "that task out. Never let a task "
    "touch .claude/, .github/, railway.*, app/api/migrations/, Temporal workflows or .env files. "
    "At most 6 tasks."
)


def worker_brief(task: Task, branch: str) -> str:
    checks = "\n".join(f"  {c.command}" for c in task.checks)
    return f"""You are a worker on Yggdras. Do only this task.

Task {task.id}: {task.objective}
You may change only: {", ".join(task.touches)}
Done means: {task.done_means}
Before you report done, run these and paste their summary lines:
{checks}

- You are in your own git worktree on branch {branch}. Commit there only.
- Never push, merge, open a PR, deploy, or edit .claude/, .github/, railway.*,
  app/api/migrations/ or any .env file.
- Your database is DATABASE_URL (a throwaway scratch database). Never use another one.
- Finish with the result object you were given a schema for.
- {STOP_LINE}"""


def send_back(command: str, exit_code: int | None, output: str) -> str:
    tail = "\n".join(output.splitlines()[-150:])
    code = "timed out" if exit_code is None else f"exit {exit_code}"
    return (
        "Your previous attempt did not pass. "
        f"Failing check: {command}, {code}. Output (last 150 lines):\n{tail}\nFix that."
    )


def answered(text: str) -> str:
    return f"Manoj answered what you were missing:\n{text}\nContinue the task."


RESUMED = (
    "You were interrupted. Check `git status` and `git log`, then continue the task. "
    "Finish with the result object."
)
