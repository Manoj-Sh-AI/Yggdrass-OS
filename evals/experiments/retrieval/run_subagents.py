"""Use one Claude process with fresh Explore children, matching the original layout."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import time

from run_matched import BRAIN, CLI, HERE, MODEL, REPO, load_env, query_prompt, redact, save


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("condition", choices=("pilot", "R1", "R2", "R3"))
    parser.add_argument("--run-name", default="matched-subagents-3")
    options = parser.parse_args()
    env = load_env()
    out = HERE / options.run_name / options.condition
    out.mkdir(parents=True, exist_ok=False)
    state = HERE / "build" / "runner-state" / options.run_name / options.condition
    state.mkdir(parents=True, exist_ok=False)
    env["CLAUDE_CONFIG_DIR"] = str(state)
    rows = json.loads((HERE / "prompts-recovered.json").read_text(encoding="utf-8"))
    for row in rows:
        row["R3"] = query_prompt(row)
    condition = options.condition
    if condition == "pilot":
        rows = [{"id": "tool-check", "question": "Tool check", "pilot": (
            f"Read this single file using the Read tool: {REPO / 'skills' / 'gateway' / 'SKILL.md'}. "
            "Reply only with its first heading. Do not run commands or open any other file.")}]
    jobs = [{"description": f"{condition} {r['id']}", "subagent_type": "Explore", "model": "opus", "prompt": r[condition]} for r in rows]
    save(out / "jobs.json", jobs)
    prompt_prefix = (
        "Execute a retrieval experiment. You are the dispatcher, not an answering agent or grader. "
        "For each job below call the Agent tool with its description, subagent_type, model, and prompt exactly as supplied. "
        "Every question must get a separate fresh Explore agent; never resume or reuse a child. "
        "The child model is opus; the current pinned primary model is claude-opus-5-5. "
        "Dispatch every job in this message as one parallel batch (all Agent calls in one response). "
        "This message contains exactly one batch; an external runner starts any subsequent batch only after this process exits. "
        "Use foreground Agent calls, not background jobs. Do not answer the questions yourself, grade answers, inspect results from other runs, "
        "or read any files. Do not retry failed jobs or change a prompt. Child tool permissions allow Read and the exact Graphify query command only. "
        "After every child finishes, return a short completion count; do not repeat their answers.\n\n"
        "Jobs:\n"
    )
    save(out / "setup.json", {"model": MODEL, "runner_version": "2.1.308", "agent_type": "Explore",
                              "one_parent_process_per_batch": True, "bare": False, "state_directory": str(state),
                              "batch_barrier": "External Python runner waits for the first dispatcher process to exit before starting the second.",
                              "batch_sizes": [20, 5] if condition != "pilot" else [1],
                              "no_prior_session": True, "query_logging_disabled": True,
                              "baseline_rerun_reason": "Fresh API parent context differs from the previous desktop session."})
    args = [str(CLI), "--model", MODEL, "--tools", "default", "--allowedTools", "Agent", "Read", "Bash(graphify query *)",
            "--setting-sources", "", "--disable-slash-commands",
            "--permission-mode", "dontAsk", "--strict-mcp-config", "--add-dir", str(BRAIN),
            "--max-budget-usd", "15.00", "--output-format", "stream-json", "--verbose", "--forward-subagent-text", "-p"]
    start = time.perf_counter()
    begin = datetime.now(timezone.utc).isoformat()
    batches = [jobs] if condition == "pilot" else [jobs[:20], jobs[20:]]
    batch_results = []
    with (out / "dispatcher.stderr.txt").open("w", encoding="utf-8") as err, (out / "dispatcher.events.jsonl").open("w", encoding="utf-8") as log:
        for number, batch in enumerate(batches, 1):
            batch_start = time.perf_counter()
            batch_begin = datetime.now(timezone.utc).isoformat()
            prompt = prompt_prefix + json.dumps(batch, ensure_ascii=False)
            proc = subprocess.Popen(args, cwd=REPO, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                    stderr=err, text=True, encoding="utf-8", errors="replace", bufsize=1)
            proc.stdin.write(prompt)
            proc.stdin.close()
            final = {}
            for line in proc.stdout:
                clean = redact(line, env)
                log.write(clean)
                log.flush()
                try:
                    event = json.loads(clean)
                except json.JSONDecodeError:
                    continue
                if event.get("type") == "result" and not event.get("parent_tool_use_id"):
                    final = event
                if event.get("type") == "assistant":
                    for block in event.get("message", {}).get("content", []):
                        if block.get("type") == "tool_use" and block.get("name") == "Agent":
                            print(f"Dispatched {block.get('input', {}).get('description', 'Explore job')}", flush=True)
                if event.get("type") == "system" and event.get("subtype") in ("task_notification", "task_started"):
                    print(json.dumps({k: event[k] for k in ("subtype", "description", "status", "usage") if k in event}), flush=True)
            code = proc.wait()
            batch_results.append({"batch": number, "question_count": len(batch), "exit_code": code,
                                  "start_utc": batch_begin, "end_utc": datetime.now(timezone.utc).isoformat(),
                                  "wall_time_s": time.perf_counter() - batch_start, "result": final})
            save(out / "dispatcher-batches.json", batch_results)
            stats = final.get("subagent_stats", {})
            if code != 0 or stats.get("spawned") != len(batch) or stats.get("completed") != len(batch) or stats.get("failed"):
                raise RuntimeError("Dispatcher did not complete exactly this batch; do not continue")
    save(out / "dispatcher-result.json", {"exit_code": code, "start_utc": begin,
        "end_utc": datetime.now(timezone.utc).isoformat(), "wall_time_s": time.perf_counter() - start,
        "batch_results": batch_results, "total_cost_usd": sum(b["result"].get("total_cost_usd", 0) for b in batch_results)})
    print(json.dumps({"exit_code": code, "condition": condition, "completed": sum(b["question_count"] for b in batch_results),
                      "total_cost_usd": sum(b["result"].get("total_cost_usd", 0) for b in batch_results)}), flush=True)


if __name__ == "__main__":
    main()
