"""The orchestrator's control loop (design §1, §5, §6, §8, §9, §10). Deterministic code only:
all I/O is in activities. A model never decides whether a task passed.

Tier 3: an edit here can break in-flight runs. Change it only with a new workflow name (V2)."""

from __future__ import annotations

import asyncio
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError

with workflow.unsafe.imports_passed_through():
    from .brief import answered, send_back, worker_brief
    from .plan import schedule, task_from_dict, validate

DEFAULT_LIMITS = {
    "attempt_usd": 3.0,  # D3
    "run_usd": 15.0,
    "max_turns": 60,
    "attempt_minutes": 45,
    "heartbeat_seconds": 120,
    "run_hours": 3.0,
    "send_backs": 2,
    "max_parallel": 3,
    "plan_usd": 1.0,
}
TERMINAL = {"passed", "failed", "failed_after_retries", "skipped", "stopped", "out_of_budget",
            "dependency_failed", "error"}  # fmt: skip
FREE = RetryPolicy(maximum_attempts=3, initial_interval=timedelta(seconds=2))


@workflow.defn(name="YggdrasSessionOrchestrationV1")
class Orchestration:
    def __init__(self) -> None:
        self.phase = "starting"
        self.run_id = ""
        self.tasks: dict[str, dict] = {}
        self.order: list[str] = []
        self.spent = 0.0
        self.running = 0
        self.approved = False
        self.dropped: list[str] = []
        self.stopped = ""
        self.answers: dict[str, str] = {}
        self.skips: set[str] = set()
        self.plan_problems: list[str] = []
        self.handles: list[asyncio.Task] = []

    # ---- what Manoj sees and does -------------------------------------------------------------
    @workflow.query
    def status(self) -> dict:
        return {"run": self.run_id, "phase": self.phase, "spent_usd": round(self.spent, 4),
                "running": self.running, "stopped": self.stopped, "plan_problems": self.plan_problems,
                "tasks": [self._public(i) for i in self.order]}  # fmt: skip

    @workflow.update
    def approve_plan(self, drop: list[str]) -> dict:
        unknown = [d for d in drop if d not in self.tasks]
        if self.phase != "awaiting_approval" or unknown:
            return {"ok": False, "phase": self.phase, "unknown": unknown}
        self.dropped, self.approved = list(drop), True
        return {"ok": True}

    @workflow.signal
    def answer(self, task_id: str, text: str) -> None:
        self.answers[task_id] = text

    @workflow.signal
    def skip(self, task_id: str) -> None:
        self.skips.add(task_id)

    @workflow.signal
    def stop(self, reason: str = "stopped by Manoj") -> None:
        self._stop(reason)

    def _stop(self, reason: str) -> None:
        if self.stopped:
            return
        self.stopped = reason
        for handle in self.handles:
            handle.cancel()  # cancels the awaited activity; it interrupts and kills its session

    def _public(self, task_id: str) -> dict:
        t = self.tasks[task_id]
        keys = ("state", "attempts", "send_backs", "cost_usd", "tokens", "session_ms", "wall_s",
                "branch", "reason", "missing", "session_id", "depends_on", "worktree", "scratch_url",
                "started_at", "ended_at", "last_tool")  # fmt: skip
        return {"id": task_id, **{k: t.get(k) for k in keys}}

    # ---- the loop -----------------------------------------------------------------------------
    @workflow.run
    async def run(self, data: dict) -> dict:
        self.run_id = data["run"]
        limits = {**DEFAULT_LIMITS, **data.get("limits", {})}
        base = data.get("base", "origin/main")
        raw = data.get("tasks") or await self._plan(data, limits)
        if raw is None:
            return await self._finish(limits, "plan_rejected")
        tasks = schedule([task_from_dict(t) for t in raw])
        problems = validate(tasks)
        if problems:
            self.plan_problems = problems
            return await self._finish(limits, "plan_rejected")
        for task in tasks:
            self.order.append(task.id)
            self.tasks[task.id] = {"spec": task, "state": "planned", "attempts": 0, "send_backs": 0,
                                   "cost_usd": 0.0, "tokens": {}, "session_ms": 0,
                                   "depends_on": task.depends_on}  # fmt: skip
        self.phase = "awaiting_approval"
        await workflow.wait_condition(lambda: self.approved or bool(self.stopped))
        if self.stopped:
            return await self._finish(limits, "stopped")
        for task_id in self.dropped:
            self.tasks[task_id]["state"] = "skipped"
        self.phase = "running"
        self.handles = [asyncio.create_task(self._drive(i, base, limits)) for i in self.order
                        if self.tasks[i]["state"] == "planned"]  # fmt: skip
        try:
            await workflow.wait_condition(
                lambda: all(h.done() for h in self.handles),
                timeout=timedelta(hours=limits["run_hours"]),
            )
        except TimeoutError:
            self._stop("run time limit reached")
            await workflow.wait_condition(lambda: all(h.done() for h in self.handles))
        return await self._finish(limits, "stopped" if self.stopped else "finished")

    async def _plan(self, data: dict, limits: dict) -> list | None:
        self.phase = "planning"
        rejected = ""
        for _ in range(2):  # the plan is re-asked once (design §2)
            result = await workflow.execute_activity(
                "plan_job",
                {"run": self.run_id, "job": data["job"], "rejected": rejected,
                 "session_id": str(workflow.uuid4()), "budget": limits["plan_usd"]},
                start_to_close_timeout=timedelta(minutes=20),
                retry_policy=RetryPolicy(maximum_attempts=1),
            )  # fmt: skip
            self.spent += float(result["outcome"].get("cost_usd") or 0)
            raw = result.get("tasks")
            if not raw:
                rejected = "No plan came back (the structured output was missing)."
                self.plan_problems = [rejected]
                continue
            problems = validate(schedule([task_from_dict(t) for t in raw]))
            if not problems:
                return raw
            rejected, self.plan_problems = "; ".join(problems), problems
        return None

    async def _drive(self, task_id: str, base: str, limits: dict) -> None:
        t = self.tasks[task_id]
        try:
            await self._drive_inner(t, task_id, base, limits)
        except asyncio.CancelledError:
            t["state"] = "stopped"
            t["reason"] = self.stopped
        except ActivityError as error:
            if self.stopped:
                t["state"], t["reason"] = "stopped", self.stopped
            else:
                t["state"], t["reason"] = "error", str(error.cause or error)[:500]
        finally:
            t.setdefault("ended_at", workflow.now().timestamp())

    async def _drive_inner(self, t: dict, task_id: str, base: str, limits: dict) -> None:
        task = t["spec"]
        t["state"] = "waiting_for_dependencies"
        await workflow.wait_condition(
            lambda: all(self.tasks[d]["state"] in TERMINAL for d in task.depends_on)
        )
        if any(self.tasks[d]["state"] != "passed" for d in task.depends_on):
            t["state"], t["reason"] = "dependency_failed", "a task it depends on did not pass"
            return
        t["state"] = "queued"
        # Several waiters can wake in one activation; re-check so the limit really holds.
        while True:
            await workflow.wait_condition(lambda: self.running < limits["max_parallel"])
            if self.running < limits["max_parallel"]:
                break
        # D7: a dependent task builds on its predecessor's branch (the last one listed).
        start = self.tasks[task.depends_on[-1]]["branch"] if task.depends_on else base
        day = workflow.now().strftime("%Y%m%d")
        t["branch"] = f"claude/{day}-{self.run_id}-{task_id}"
        self.running += 1
        try:
            prepared = await workflow.execute_activity(
                "prepare_task",
                {"run": self.run_id, "task_id": task_id, "branch": t["branch"], "base": start},
                start_to_close_timeout=timedelta(minutes=5), retry_policy=FREE,
            )  # fmt: skip
            t.update(worktree=prepared["worktree"], scratch_url=prepared["scratch_url"],
                     scratch_name=prepared["scratch_name"], started_at=workflow.now().timestamp())  # fmt: skip
            t["session_id"] = str(workflow.uuid4())
            prompt, resume = worker_brief(task, t["branch"]), False
            while True:
                left = limits["run_usd"] - self.spent
                if left <= 0.01:
                    t["state"], t["reason"] = "out_of_budget", "the run's money is used up"
                    return
                t["attempts"] += 1
                t["state"] = "working"
                outcome = await workflow.execute_activity(
                    "run_worker",
                    {"run": self.run_id, "task": _task_dict(task), "worktree": t["worktree"],
                     "scratch_url": t["scratch_url"], "session_id": t["session_id"],
                     "resume": resume, "prompt": prompt, "attempt": t["attempts"],
                     "budget": round(min(limits["attempt_usd"], left), 2),
                     "max_turns": limits["max_turns"]},
                    start_to_close_timeout=timedelta(minutes=limits["attempt_minutes"]),
                    heartbeat_timeout=timedelta(seconds=limits["heartbeat_seconds"]),
                    retry_policy=RetryPolicy(maximum_attempts=2),
                    cancellation_type=workflow.ActivityCancellationType.WAIT_CANCELLATION_COMPLETED,
                )  # fmt: skip
                self._account(t, outcome)
                structured = outcome.get("structured") or {}
                if structured.get("status") == "blocked":
                    t["state"], t["missing"] = "waiting_for_manoj", structured.get("missing", "")
                    self.running -= 1
                    try:
                        await workflow.wait_condition(
                            lambda: task_id in self.answers or task_id in self.skips
                            or bool(self.stopped)
                        )  # fmt: skip
                    finally:
                        self.running += 1
                    if task_id in self.skips or self.stopped:
                        t["state"] = "skipped" if task_id in self.skips else "stopped"
                        return
                    prompt, resume = answered(self.answers.pop(task_id)), True
                    continue
                t["state"] = "checking"
                verdict = await workflow.execute_activity(
                    "judge_task",
                    {"run": self.run_id, "task": _task_dict(task), "worktree": t["worktree"],
                     "base": start, "scratch_url": t["scratch_url"], "attempt": t["attempts"]},
                    start_to_close_timeout=timedelta(minutes=45), retry_policy=FREE,
                )  # fmt: skip
                t["reason"] = verdict["reason"]
                t["worker_said"] = structured.get("status", outcome.get("subtype"))
                if verdict["passed"]:
                    t["state"] = "passed"
                    return
                if t["send_backs"] >= limits["send_backs"]:
                    t["state"] = "failed_after_retries"
                    t["last_failure"] = verdict["output"][-3000:]
                    return
                t["send_backs"] += 1
                prompt = send_back(verdict["command"] or verdict["reason"], verdict["exit_code"],
                                   verdict["output"])  # fmt: skip
                resume = True
        finally:
            self.running -= 1
            t["ended_at"] = workflow.now().timestamp()
            if t.get("started_at"):
                t["wall_s"] = round(t["ended_at"] - t["started_at"], 1)

    def _account(self, t: dict, outcome: dict) -> None:
        cost = float(outcome.get("cost_usd") or 0)
        t["cost_usd"] = round(t["cost_usd"] + cost, 6)
        self.spent += cost
        t["session_ms"] += int(outcome.get("duration_ms") or 0)
        t["last_tool"] = outcome.get("last_tool", "")
        for key, value in (outcome.get("tokens") or {}).items():
            t["tokens"][key] = t["tokens"].get(key, 0) + int(value)

    async def _finish(self, limits: dict, phase: str) -> dict:
        self.phase = phase
        tasks = [self._public(i) for i in self.order]
        totals: dict = {"cost_usd": round(self.spent, 6), "tokens": {}}
        for t in tasks:
            for key, value in (t.get("tokens") or {}).items():
                totals["tokens"][key] = totals["tokens"].get(key, 0) + value
        report = {"run": self.run_id, "phase": phase, "stopped": self.stopped, "limits": limits,
                  "plan_problems": self.plan_problems, "tasks": tasks, "totals": totals}  # fmt: skip
        keep = {"failed", "failed_after_retries", "error"}
        down = [self.tasks[i]["scratch_name"] for i in self.order
                if self.tasks[i].get("scratch_name") and self.tasks[i]["state"] not in keep]  # fmt: skip
        await workflow.execute_activity(
            "finish_run", {"run": self.run_id, "report": report, "scratch_down": down},
            start_to_close_timeout=timedelta(minutes=5), retry_policy=FREE,
        )  # fmt: skip
        return report


def _task_dict(task) -> dict:
    return {"id": task.id, "objective": task.objective, "touches": task.touches,
            "checks": [vars(c) for c in task.checks], "done_means": task.done_means,
            "depends_on": task.depends_on,
            "holdout_checks": [vars(c) for c in task.holdout_checks]}  # fmt: skip
