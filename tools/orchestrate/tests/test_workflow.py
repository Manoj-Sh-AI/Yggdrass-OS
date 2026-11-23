"""The control loop on a real Temporal dev server with fake activities: no model calls, no DB.
Each test drives one Phase 2 criterion through the workflow's own logic."""

import asyncio
import os
import time
import uuid
from pathlib import Path

import pytest
from temporalio import activity
from temporalio.client import Client, WorkflowHandle
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Replayer, Worker

from orchestrate.workflow import Orchestration

QUEUE = "test-orchestration"


class Fake:
    """Shared script and call log for the fake activities."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.calls: list[dict] = []
        self.spans: dict[str, list[tuple[float, float]]] = {}
        self.verdicts: dict[str, list[bool]] = {}
        self.worker_results: dict[str, list[dict]] = {}
        self.cost = 0.5
        self.hang: set[str] = set()
        self.cancelled: list[str] = []
        self.seen_attempts: list[tuple[str, int, object]] = []
        self.finished: list[dict] = []


FAKE = Fake()


@activity.defn(name="prepare_task")
async def prepare_task(data: dict) -> dict:
    FAKE.calls.append({"name": "prepare", **data})
    name = f"{data['run']}-{data['task_id']}"
    return {"worktree": f"/wt/{name}", "scratch_url": f"postgresql://scratch/{name}",
            "scratch_name": name}  # fmt: skip


@activity.defn(name="run_worker")
async def run_worker(data: dict) -> dict:
    task_id = data["task"]["id"]
    info = activity.info()
    details = info.heartbeat_details[0] if info.heartbeat_details else None
    FAKE.seen_attempts.append((task_id, info.attempt, details))
    FAKE.calls.append({"name": "worker", "task": task_id, "prompt": data["prompt"],
                       "resume": data["resume"], "budget": data["budget"]})  # fmt: skip
    start = time.monotonic()
    try:
        if task_id in FAKE.hang:
            while True:
                activity.heartbeat({"session_id": data["session_id"], "pid": 4242})
                await asyncio.sleep(0.2)
        activity.heartbeat({"session_id": data["session_id"], "pid": 4242})
        await asyncio.sleep(0.6)
    except asyncio.CancelledError:
        FAKE.cancelled.append(task_id)
        raise
    finally:
        FAKE.spans.setdefault(task_id, []).append((start, time.monotonic()))
    scripted = FAKE.worker_results.get(task_id)
    structured = scripted.pop(0) if scripted else {"status": "done"}
    return {"structured": structured, "cost_usd": FAKE.cost, "duration_ms": 600,
            "tokens": {"input": 10, "output": 5}, "subtype": "success", "last_tool": "Bash"}  # fmt: skip


@activity.defn(name="judge_task")
async def judge_task(data: dict) -> dict:
    FAKE.calls.append({"name": "judge", "task": data["task"]["id"], "base": data["base"]})
    script = FAKE.verdicts.get(data["task"]["id"])
    passed = script.pop(0) if script else True
    return {"passed": passed, "reason": "ok" if passed else "A check failed.",
            "command": "uv run pytest -q", "exit_code": 0 if passed else 1,
            "output": "" if passed else "FAILED test_x - assert 1 == 2"}  # fmt: skip


@activity.defn(name="finish_run")
async def finish_run(data: dict) -> str:
    FAKE.finished.append(data)
    return "report.json"


ACTIVITIES = [prepare_task, run_worker, judge_task, finish_run]


def task(id, touches, deps=()):
    return {"id": id, "objective": f"do {id}", "touches": touches,
            "checks": [{"command": "uv run pytest -q"}], "done_means": "x", "depends_on": list(deps)}  # fmt: skip


@pytest.fixture(scope="module")
def env():
    binary = os.environ.get("ORCH_TEMPORAL_BINARY")
    loop = asyncio.new_event_loop()
    environment = loop.run_until_complete(
        WorkflowEnvironment.start_local(
            dev_server_existing_path=binary if binary and Path(binary).is_file() else None,
            dev_server_log_level="error",
        )
    )
    yield loop, environment
    loop.run_until_complete(environment.shutdown())
    loop.close()


def run(env, coro):
    loop, _ = env
    return loop.run_until_complete(coro)


def worker(client: Client) -> Worker:
    return Worker(client, task_queue=QUEUE, workflows=[Orchestration], activities=ACTIVITIES)


async def until(handle: WorkflowHandle, check, seconds=30):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        status = await handle.query(Orchestration.status)
        if check(status):
            return status
        await asyncio.sleep(0.1)
    raise AssertionError(f"never reached: {status}")


async def start(client, tasks, limits=None, run=None):
    run = run or f"r{uuid.uuid4().hex[:6]}"
    handle = await client.start_workflow(
        Orchestration.run, {"run": run, "tasks": tasks, "limits": limits or {}},
        id=f"orch-{run}", task_queue=QUEUE,
    )  # fmt: skip
    await until(handle, lambda s: s["phase"] == "awaiting_approval")
    assert (await handle.execute_update(Orchestration.approve_plan, []))["ok"]
    return handle


def states(report):
    return {t["id"]: t["state"] for t in report["tasks"]}


def test_two_workers_run_at_the_same_time_and_replay_is_deterministic(env):
    FAKE.reset()
    client = env[1].client

    async def go():
        async with worker(client):
            handle = await start(client, [task("a", ["docs/a.md"]), task("b", ["docs/b.md"])])
            report = await handle.result()
            history = await handle.fetch_history()
        await Replayer(workflows=[Orchestration]).replay_workflow(history)
        return report

    report = run(env, go())
    assert states(report) == {"a": "passed", "b": "passed"}
    (a0, a1), (b0, b1) = FAKE.spans["a"][0], FAKE.spans["b"][0]
    assert a0 < b1 and b0 < a1, "the two workers did not overlap"
    worktrees = {t["worktree"] for t in report["tasks"]}
    urls = {t["scratch_url"] for t in report["tasks"]}
    assert len(worktrees) == 2 and len(urls) == 2
    assert report["totals"]["cost_usd"] == pytest.approx(1.0)
    assert report["totals"]["tokens"] == {"input": 20, "output": 10}


def test_failing_check_is_sent_back_then_passes(env):
    FAKE.reset()
    FAKE.verdicts["a"] = [False, True]
    client = env[1].client

    async def go():
        async with worker(client):
            return await (await start(client, [task("a", ["docs/a.md"])])).result()

    report = run(env, go())
    t = report["tasks"][0]
    assert t["state"] == "passed" and t["attempts"] == 2 and t["send_backs"] == 1
    prompts = [c for c in FAKE.calls if c["name"] == "worker"]
    assert prompts[0]["resume"] is False and prompts[1]["resume"] is True
    assert "did not pass" in prompts[1]["prompt"] and "FAILED test_x" in prompts[1]["prompt"]


def test_failing_check_is_reported_after_the_retry_limit(env):
    FAKE.reset()
    FAKE.verdicts["a"] = [False, False, False, False]
    client = env[1].client

    async def go():
        async with worker(client):
            return await (await start(client, [task("a", ["docs/a.md"])])).result()

    t = run(env, go())["tasks"][0]
    assert t["state"] == "failed_after_retries" and t["attempts"] == 3 and t["send_backs"] == 2


def test_worker_saying_done_does_not_pass_a_failing_check(env):
    FAKE.reset()
    FAKE.verdicts["a"] = [False, False, False]
    FAKE.worker_results["a"] = [{"status": "done"}] * 3
    client = env[1].client

    async def go():
        async with worker(client):
            return await (await start(client, [task("a", ["docs/a.md"])])).result()

    assert run(env, go())["tasks"][0]["state"] == "failed_after_retries"


def test_blocked_worker_waits_for_manoj_and_resumes_with_the_answer(env):
    FAKE.reset()
    FAKE.worker_results["a"] = [{"status": "blocked", "missing": "SECRET_ORCHESTRATION_TOKEN"}]
    client = env[1].client

    async def go():
        async with worker(client):
            handle = await start(client, [task("a", ["docs/a.md"])])
            status = await until(handle, lambda s: s["tasks"][0]["state"] == "waiting_for_manoj")
            assert status["tasks"][0]["missing"] == "SECRET_ORCHESTRATION_TOKEN"
            assert status["running"] == 0  # a blocked task holds no worker slot
            assert not [c for c in FAKE.calls if c["name"] == "judge"]
            await handle.signal(Orchestration.answer, args=["a", "use the value abc"])
            return await handle.result()

    report = run(env, go())
    assert report["tasks"][0]["state"] == "passed"
    second = [c for c in FAKE.calls if c["name"] == "worker"][1]
    assert second["resume"] is True and "use the value abc" in second["prompt"]


def test_blocked_worker_can_be_skipped(env):
    FAKE.reset()
    FAKE.worker_results["a"] = [{"status": "blocked", "missing": "a key"}]
    client = env[1].client

    async def go():
        async with worker(client):
            handle = await start(client, [task("a", ["docs/a.md"])])
            await until(handle, lambda s: s["tasks"][0]["state"] == "waiting_for_manoj")
            await handle.signal(Orchestration.skip, "a")
            return await handle.result()

    assert states(run(env, go())) == {"a": "skipped"}


def test_stop_cancels_every_running_worker(env):
    FAKE.reset()
    FAKE.hang = {"a", "b"}
    client = env[1].client

    async def go():
        async with worker(client):
            handle = await start(client, [task("a", ["docs/a.md"]), task("b", ["docs/b.md"])])
            await until(handle, lambda s: s["running"] == 2 and
                        all(t["state"] == "working" for t in s["tasks"]))  # fmt: skip
            await asyncio.sleep(0.5)
            await handle.signal(Orchestration.stop, "stopped by Manoj")
            return await handle.result()

    report = run(env, go())
    assert states(report) == {"a": "stopped", "b": "stopped"}
    assert sorted(FAKE.cancelled) == ["a", "b"]
    assert report["phase"] == "stopped" and FAKE.finished


def test_overlapping_tasks_never_run_together_and_stack_branches(env):
    FAKE.reset()
    client = env[1].client

    async def go():
        async with worker(client):
            # note: fnmatch's * also matches "/", so "tools/*" would reach the protected workflow
            return await (
                await start(client, [task("a", ["lib/*"]), task("b", ["lib/x.py"])])
            ).result()

    report = run(env, go())
    assert states(report) == {"a": "passed", "b": "passed"}
    assert FAKE.spans["a"][0][1] <= FAKE.spans["b"][0][0]
    a_branch = report["tasks"][0]["branch"]
    prepares = [c for c in FAKE.calls if c["name"] == "prepare"]
    assert prepares[1]["base"] == a_branch


def test_dependent_task_is_not_started_when_its_dependency_fails(env):
    FAKE.reset()
    FAKE.verdicts["a"] = [False] * 3
    client = env[1].client

    async def go():
        async with worker(client):
            return await (
                await start(client, [task("a", ["docs/a.md"]), task("b", ["docs/b.md"], ["a"])])
            ).result()

    assert states(run(env, go())) == {"a": "failed_after_retries", "b": "dependency_failed"}


def test_run_budget_stops_new_attempts(env):
    FAKE.reset()
    FAKE.cost = 6.0
    FAKE.verdicts["a"] = [False] * 3
    client = env[1].client

    async def go():
        async with worker(client):
            return await (
                await start(client, [task("a", ["docs/a.md"])], {"run_usd": 10.0})
            ).result()

    t = run(env, go())["tasks"][0]
    assert t["state"] == "out_of_budget" and t["attempts"] == 2
    budgets = [c["budget"] for c in FAKE.calls if c["name"] == "worker"]
    assert budgets == [3.0, 3.0]  # the second attempt gets min(per attempt, money left)


def test_at_most_max_parallel_workers(env):
    FAKE.reset()
    client = env[1].client
    tasks = [task(f"t{i}", [f"docs/{i}.md"]) for i in range(4)]

    async def go():
        async with worker(client):
            return await (await start(client, tasks, {"max_parallel": 2})).result()

    run(env, go())
    events = sorted([(s, 1) for v in FAKE.spans.values() for s, _ in v] +
                    [(e, -1) for v in FAKE.spans.values() for _, e in v])  # fmt: skip
    peak = level = 0
    for _, step in events:
        level += step
        peak = max(peak, level)
    assert peak == 2


def test_host_crash_resumes_without_starting_workers_twice(env):
    """Host dies while b runs: a's finished activity is not re-run, and b's retry carries the
    same session id in its heartbeat details (the real activity resumes that session)."""
    FAKE.reset()
    FAKE.hang = {"b"}
    client = env[1].client
    limits = {"heartbeat_seconds": 2}

    async def go():
        first = worker(client)
        async with first:
            handle = await start(
                client, [task("a", ["docs/a.md"]), task("b", ["docs/b.md"])], limits
            )
            await until(handle, lambda s: s["tasks"][0]["state"] == "passed" and
                        s["tasks"][1]["state"] == "working")  # fmt: skip
            await asyncio.sleep(0.5)
        # the host is gone; b's activity stops heartbeating. A new host picks up from history.
        FAKE.hang = set()
        async with worker(client):
            return await handle.result()

    report = run(env, go())
    assert states(report) == {"a": "passed", "b": "passed"}
    a_runs = [c for c in FAKE.calls if c["name"] == "worker" and c["task"] == "a"]
    assert len(a_runs) == 1, "a finished worker was started again"
    b_attempts = [(n, d) for t, n, d in FAKE.seen_attempts if t == "b"]
    assert [n for n, _ in b_attempts] == [1, 2]
    assert b_attempts[1][1]["session_id"] == report["tasks"][1]["session_id"]
