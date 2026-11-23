"""Temporal activities: every bit of I/O (git, scratch DBs, SDK sessions, checks, run folder).
The workflow passes plain dicts so histories stay readable and replayable."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

from temporalio import activity
from temporalio.exceptions import ApplicationError

from . import checks, isolation, probe, session
from .brief import PLANNER_SYSTEM, RESUMED
from .plan import task_from_dict


class Activities:
    def __init__(self, config: isolation.Config, runner=session.run_session):
        self.config = config
        self.runner = runner  # swapped for a fake in tests

    def _task_dir(self, run: str, task_id: str) -> Path:
        folder = self.config.run_dir(run) / task_id
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    @activity.defn(name="plan_job")
    async def plan_job(self, data: dict) -> dict:
        reason = probe.probe_passed(self.config)
        if reason:
            raise ApplicationError(reason, non_retryable=True)
        prompt = data["job"]
        if data.get("rejected"):
            prompt += f"\n\nYour previous plan was refused: {data['rejected']}\nFix that."
        options = session.planner_options(self.config.repo, data["session_id"], data["budget"])
        outcome = await self.runner(prompt, options)
        folder = self.config.run_dir(data["run"])
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "plan.json").write_text(
            json.dumps(outcome.structured, indent=1), encoding="utf-8"
        )
        tasks = (outcome.structured or {}).get("tasks") if not outcome.is_error else None
        return {"tasks": tasks, "outcome": outcome.to_dict(), "system": PLANNER_SYSTEM[:80]}

    @activity.defn(name="prepare_task")
    async def prepare_task(self, data: dict) -> dict:
        name = f"{data['run']}-{data['task_id']}"
        worktree = await asyncio.to_thread(
            isolation.ensure_worktree, self.config, name, data["branch"], data["base"]
        )
        url = await asyncio.to_thread(isolation.scratch_db, self.config, name, "up")
        return {"worktree": str(worktree), "scratch_url": url, "scratch_name": name}

    @activity.defn(name="run_worker")
    async def run_worker(self, data: dict) -> dict:
        reason = probe.probe_passed(self.config)
        if reason:
            raise ApplicationError(reason, non_retryable=True)
        info = activity.info()
        task = task_from_dict(data["task"])
        folder = self._task_dir(data["run"], task.id)
        prompt, resume = data["prompt"], data["resume"]
        previous = info.heartbeat_details[0] if info.heartbeat_details else None
        if info.attempt > 1 and previous:
            # The host died mid-session: kill what is left, then resume the SAME session.
            await asyncio.to_thread(isolation.kill_tree, previous.get("pid"))
            prompt, resume = RESUMED, True
        live = {"attempt": data["attempt"], "started": time.time(), "last_tool": "", "tools": 0}
        state = {"session_id": data["session_id"], "pid": None}

        def beat() -> None:
            activity.heartbeat(dict(state))
            (folder / "live.json").write_text(json.dumps(live), encoding="utf-8")

        def on_event(tool: str) -> None:
            live["last_tool"], live["tools"] = tool, live["tools"] + 1
            beat()

        def on_pid(pid: int | None) -> None:
            state["pid"] = pid
            isolation.record_pid(self.config, data["run"], task.id, pid)
            beat()

        async def ticker() -> None:
            while True:  # a long pytest run sends no messages; keep the heartbeat alive
                await asyncio.sleep(5)  # also how fast a stop reaches this activity
                beat()

        log = (folder / f"stderr-{data['attempt']}.log").open("a", encoding="utf-8")
        options = session.worker_options(
            Path(data["worktree"]), data["scratch_url"], data["session_id"], resume,
            data["budget"], data["max_turns"], [c.command for c in task.checks],
            log=lambda line: log.write(line + "\n"),
        )  # fmt: skip
        (folder / f"prompt-{data['attempt']}.txt").write_text(prompt, encoding="utf-8")
        beat()
        tick = asyncio.create_task(ticker())
        try:
            outcome = await self.runner(prompt, options, on_event, on_pid)
        finally:
            tick.cancel()
            log.close()
        result = outcome.to_dict()
        (folder / f"result-{data['attempt']}.json").write_text(json.dumps(result, indent=1),
                                                                encoding="utf-8")  # fmt: skip
        result["last_tool"] = live["last_tool"]
        return result

    @activity.defn(name="judge_task")
    async def judge_task(self, data: dict) -> dict:
        task = task_from_dict(data["task"])
        logs = self._task_dir(data["run"], task.id) / f"checks-{data['attempt']}"
        verdict = await asyncio.to_thread(
            checks.judge, task, Path(data["worktree"]), data["base"], data["scratch_url"], logs
        )
        return verdict.to_dict()

    @activity.defn(name="finish_run")
    async def finish_run(self, data: dict) -> str:
        for name in data.get("scratch_down", []):
            try:
                await asyncio.to_thread(isolation.scratch_db, self.config, name, "down")
            except RuntimeError:
                pass  # a stopped cluster is fine; the report still gets written
        folder = self.config.run_dir(data["run"])
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / "report.json"
        path.write_text(json.dumps(data["report"], indent=1), encoding="utf-8")
        return str(path)

    def all(self) -> list:
        return [self.plan_job, self.prepare_task, self.run_worker, self.judge_task, self.finish_run]
