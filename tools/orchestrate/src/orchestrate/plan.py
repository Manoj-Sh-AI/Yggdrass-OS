"""Tasks, plan validation and file-overlap scheduling (design §2, §6). Pure code, no I/O."""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass, field

MAX_TASKS = 6
# Never in a task's `touches` (design §2): gates, CI, deploy, migrations, Temporal workflows, secrets.
PROTECTED = (
    ".claude/**",
    ".github/**",
    "railway.*",
    "app/api/migrations/**",
    "app/api/src/yggdress_app/temporal_*workflow*.py",
    "tools/orchestrate/src/orchestrate/workflow.py",
    "**/.env",
    "**/.env.*",
    ".env",
    ".env.*",
)
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,30}$")


@dataclass
class Check:
    command: str
    expect_exit: int = 0


@dataclass
class Task:
    id: str
    objective: str
    touches: list[str]
    checks: list[Check]
    done_means: str
    depends_on: list[str] = field(default_factory=list)
    # Run by the orchestrator but not shown in the brief, like a held-out eval question.
    holdout_checks: list[Check] = field(default_factory=list)
    # Screenshot checks (design §2) are not built in Phase 2: the harmless tasks have no UI.


def task_from_dict(data: dict) -> Task:
    def checks(key: str) -> list[Check]:
        return [Check(c["command"], int(c.get("expect_exit", 0))) for c in data.get(key, [])]

    return Task(
        id=data["id"],
        objective=data["objective"],
        touches=list(data["touches"]),
        checks=checks("checks"),
        done_means=data["done_means"],
        depends_on=list(data.get("depends_on", [])),
        holdout_checks=checks("holdout_checks"),
    )


def matches(path: str, pattern: str) -> bool:
    path = path.replace("\\", "/")
    if fnmatch.fnmatchcase(path, pattern):
        return True
    # "dir/**" also matches "dir/x" with fnmatch, but "**/x" must match a top-level "x" too.
    return pattern.startswith("**/") and fnmatch.fnmatchcase(path, pattern[3:])


def _literal_prefix(pattern: str) -> str:
    cut = len(pattern)
    for char in "*?[":
        index = pattern.find(char)
        if index != -1:
            cut = min(cut, index)
    return pattern[:cut]


def globs_overlap(a: str, b: str) -> bool:
    """True if some path could match both. When unsure, say yes (a false yes only costs time)."""
    a, b = a.replace("\\", "/"), b.replace("\\", "/")
    if a == b:
        return True
    pa, pb = _literal_prefix(a), _literal_prefix(b)
    if pa == a:  # a is a literal path: exact answer
        return matches(a, b)
    if pb == b:
        return matches(b, a)
    for x, y in ((a, b), (b, a)):
        if x == "**":
            return True
        if x.startswith("**/"):
            tail, last = x[3:], y.rsplit("/", 1)[-1]
            if _literal_prefix(tail) == tail:  # "**/name": y must be able to end in "name"
                return fnmatch.fnmatchcase(tail, last)
            return True
    # Wildcards: they can only meet if one literal prefix extends the other.
    return pa.startswith(pb) or pb.startswith(pa)


def tasks_overlap(a: Task, b: Task) -> bool:
    return any(globs_overlap(x, y) for x in a.touches for y in b.touches)


def protected_hit(pattern: str) -> str | None:
    for guard in PROTECTED:
        if guard.startswith("**/"):
            # Any directory glob *could* hold a .env; refusing all of them would make plans
            # useless. Here we refuse only a glob that names it. Real .env edits are still
            # refused by the scope check (actual changed files) and by the guard hook.
            last = pattern.replace("\\", "/").rsplit("/", 1)[-1]
            if pattern == "**" or (last == _literal_prefix(last) and matches(last, guard[3:])):
                return guard
        elif globs_overlap(pattern, guard):
            return guard
    return None


def validate(tasks: list[Task]) -> list[str]:
    """Reasons the plan is refused; empty means valid."""
    problems: list[str] = []
    if not tasks:
        problems.append("The plan has no tasks.")
    if len(tasks) > MAX_TASKS:
        problems.append(f"The plan has {len(tasks)} tasks; the limit is {MAX_TASKS}.")
    ids = [t.id for t in tasks]
    for dup in sorted({i for i in ids if ids.count(i) > 1}):
        problems.append(f"Task id {dup!r} is used twice.")
    for task in tasks:
        if not SLUG.match(task.id):
            problems.append(f"Task id {task.id!r} must be a short lowercase slug.")
        if not task.checks:
            problems.append(f"Task {task.id} has no checks, so it cannot be proven done.")
        if not task.touches:
            problems.append(f"Task {task.id} lists no paths it may change.")
        for pattern in task.touches:
            guard = protected_hit(pattern)
            if guard:
                problems.append(
                    f"Task {task.id} may touch {pattern!r}, which hits protected {guard!r}."
                )
        for dep in task.depends_on:
            if dep not in ids:
                problems.append(f"Task {task.id} depends on unknown task {dep!r}.")
    if not problems and _has_cycle(tasks):
        problems.append("The task dependencies form a cycle.")
    return problems


def _has_cycle(tasks: list[Task]) -> bool:
    deps = {t.id: set(t.depends_on) for t in tasks}
    state: dict[str, int] = {}

    def visit(node: str) -> bool:
        if state.get(node) == 1:
            return True
        if state.get(node) == 2:
            return False
        state[node] = 1
        if any(visit(d) for d in deps.get(node, ())):
            return True
        state[node] = 2
        return False

    return any(visit(t.id) for t in tasks)


def schedule(tasks: list[Task]) -> list[Task]:
    """Add an implicit dependency between overlapping tasks (later waits for earlier)."""
    for index, later in enumerate(tasks):
        for earlier in tasks[:index]:
            if earlier.id in later.depends_on or later.id in earlier.depends_on:
                continue
            if tasks_overlap(earlier, later):
                later.depends_on.append(earlier.id)
    return tasks
