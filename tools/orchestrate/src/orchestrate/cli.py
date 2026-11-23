"""`orchestrate` command line (design §10). Run from tools/orchestrate with `uv run orchestrate`.

orchestrate server                      Temporal dev server for orchestration (own terminal)
orchestrate host                        the worker host: runs the workflow and activities
orchestrate probe                       deny-rule probe; workers refuse to start without a pass
orchestrate start RUN --tasks FILE      start with a fixed task list (still needs approve)
orchestrate start RUN --job TEXT        start with a job for Fable to split
orchestrate status RUN                  one line per task, costs so far
orchestrate approve RUN [--drop a,b]    approve the plan (D5)
orchestrate answer RUN TASK TEXT        answer a blocked worker
orchestrate skip RUN TASK               give up on a blocked task
orchestrate stop RUN [--hard]           stop everything (hard: terminate + kill recorded pids)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import timedelta
from pathlib import Path

from temporalio.client import Client
from temporalio.worker import Worker

from . import isolation, probe
from .activities import Activities
from .workflow import Orchestration


def workflow_id(run: str) -> str:
    return f"orch-{run}"


async def client_for(config: isolation.Config) -> Client:
    return await Client.connect(config.temporal)


def temporal_binary(config: isolation.Config) -> str:
    name = "temporal.exe" if os.name == "nt" else "temporal"
    for candidate in (os.environ.get("ORCH_TEMPORAL_BINARY"),
                      str(config.repo / "app/api/runtime/temporal-tools" / name),
                      shutil.which("temporal")):  # fmt: skip
        if candidate and Path(candidate).is_file():
            return candidate
    raise SystemExit("Temporal CLI not found: set ORCH_TEMPORAL_BINARY.")


def cmd_server(config: isolation.Config) -> int:
    host, port = config.temporal.rsplit(":", 1)
    config.root.mkdir(parents=True, exist_ok=True)
    return subprocess.call([temporal_binary(config), "server", "start-dev", "--ip", host,
                            "--port", port, "--ui-port", "8244",
                            "--db-filename", str(config.root / "temporal.db")])  # fmt: skip


async def cmd_host(config: isolation.Config) -> int:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY is not set. D6: workers use an API key, never a claude.ai login.")
        return 2
    removed = isolation.scrub_environment()
    print(f"Environment scrubbed: {len(removed)} variables removed before any session starts.")
    reason = probe.probe_passed(config)
    if reason:
        print(f"Warning: {reason}")
    client = await client_for(config)
    worker = Worker(client, task_queue=isolation.TASK_QUEUE, workflows=[Orchestration],
                    activities=Activities(config).all(), max_concurrent_activities=10)  # fmt: skip
    print(f"Host running on {config.temporal}, queue {isolation.TASK_QUEUE}. Ctrl+C to stop.")
    await worker.run()
    return 0


async def cmd_start(config: isolation.Config, args) -> int:
    data: dict = {"run": isolation.slug(args.run), "base": args.base}
    if args.tasks:
        data["tasks"] = json.loads(Path(args.tasks).read_text(encoding="utf-8"))["tasks"]
    elif args.job:
        data["job"] = args.job
    else:
        print("Give --tasks FILE or --job TEXT.")
        return 2
    if args.limits:
        data["limits"] = json.loads(args.limits)
    client = await client_for(config)
    await client.start_workflow(Orchestration.run, data, id=workflow_id(data["run"]),
                                task_queue=isolation.TASK_QUEUE,
                                execution_timeout=timedelta(hours=24))  # fmt: skip
    print(f"Started {workflow_id(data['run'])}. Next: orchestrate status {data['run']}")
    return 0


async def cmd_status(config: isolation.Config, run: str) -> int:
    client = await client_for(config)
    status = await client.get_workflow_handle(workflow_id(run)).query(Orchestration.status)
    print(f"{status['run']}: {status['phase']}  spent ${status['spent_usd']:.4f}  "
          f"running {status['running']}  {status['stopped']}")  # fmt: skip
    for problem in status["plan_problems"]:
        print(f"  plan problem: {problem}")
    for t in status["tasks"]:
        live_file = config.run_dir(run) / t["id"] / "live.json"
        live = json.loads(live_file.read_text()) if live_file.exists() else {}
        tool = live.get("last_tool") or t.get("last_tool") or ""
        extra = f"  waiting for Manoj: {t['missing']}" if t["state"] == "waiting_for_manoj" else ""
        print(
            f"  {t['id']:<14} {t['state']:<22} attempt {t['attempts']} sendbacks {t['send_backs']}"
            f"  ${t['cost_usd']:.4f}  last tool {tool or '-'}  {t.get('branch') or ''}{extra}"
        )
    return 0


async def cmd_signal(config: isolation.Config, args) -> int:
    handle = (await client_for(config)).get_workflow_handle(workflow_id(args.run))
    if args.command == "approve":
        drop = [d for d in (args.drop or "").split(",") if d]
        print(await handle.execute_update(Orchestration.approve_plan, drop))
    elif args.command == "answer":
        await handle.signal(Orchestration.answer, args=[args.task, args.text])
    elif args.command == "skip":
        await handle.signal(Orchestration.skip, args.task)
    elif args.command == "stop" and not args.hard:
        await handle.signal(Orchestration.stop, "stopped by Manoj")
        print("Stop sent. Each worker is interrupted and its process tree killed.")
    else:  # stop --hard: the workflow runs no cleanup, so kill every recorded pid ourselves
        try:
            await handle.terminate("hard stop by Manoj")
        except Exception as error:  # noqa: BLE001 -- the kill below is what matters
            print(f"terminate: {error}")
        for key, pid in isolation.recorded_pids(config, args.run).items():
            isolation.kill_tree(pid)
            print(f"killed {key} (pid {pid})")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="orchestrate", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("server")
    sub.add_parser("host")
    sub.add_parser("probe")
    start = sub.add_parser("start")
    start.add_argument("run")
    start.add_argument("--tasks")
    start.add_argument("--job")
    start.add_argument("--base", default="origin/main")
    start.add_argument("--limits", help='JSON, e.g. {"run_usd": 5}')
    for name in ("status", "approve", "answer", "skip", "stop"):
        p = sub.add_parser(name)
        p.add_argument("run")
        if name == "approve":
            p.add_argument("--drop")
        if name in ("answer", "skip"):
            p.add_argument("task")
        if name == "answer":
            p.add_argument("text")
        if name == "stop":
            p.add_argument("--hard", action="store_true")
    args = parser.parse_args(argv)
    config = isolation.load_config()
    started = time.time()
    if args.command == "server":
        return cmd_server(config)
    if args.command == "host":
        return asyncio.run(cmd_host(config))
    if args.command == "probe":
        if not os.environ.get("ANTHROPIC_API_KEY"):
            print("ANTHROPIC_API_KEY is not set (D6).")
            return 2
        isolation.scrub_environment()
        return probe.main_probe(config)
    if args.command == "start":
        return asyncio.run(cmd_start(config, args))
    if args.command == "status":
        return asyncio.run(cmd_status(config, args.run))
    code = asyncio.run(cmd_signal(config, args))
    if args.command == "stop":
        print(f"({time.time() - started:.1f}s)")
    return code


if __name__ == "__main__":
    sys.exit(main())
