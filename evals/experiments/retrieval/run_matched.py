"""Local-only, matched Claude Explore retrieval runs; no brain or Graphify edits."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
CLI = Path(r"C:\Users\shman\AppData\Local\Claude-Data\claude_pzs8sxrjxfjjc\claude-code\2.1.308\c17a819afb40\claude.exe")
BRAIN = Path(r"C:\Users\shman\yggdras-brain\demo-brain")
GRAPH = HERE / "build" / "graphify-out" / "graph.json"
MODEL = "claude-opus-5-5"


def load_env():
    env = os.environ.copy()
    for line in (REPO / ".env").read_text(encoding="utf-8-sig").splitlines():
        if line.strip().startswith("ANTHROPIC_API_KEY="):
            env["ANTHROPIC_API_KEY"] = line.split("=", 1)[1].strip().strip("\"'")
    if not env.get("ANTHROPIC_API_KEY"):
        raise RuntimeError("No project API credential is configured")
    env["GRAPHIFY_QUERY_LOG_DISABLE"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["CLAUDE_CODE_DISABLE_AUTO_MEMORY"] = "1"
    return env


def redact(text, env):
    key = env.get("ANTHROPIC_API_KEY", "")
    if key:
        text = text.replace(key, "[REDACTED]")
    return re.sub(r"sk-ant-[A-Za-z0-9_-]+", "[REDACTED]", text)


def save(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def query_prompt(row):
    return (
        "You are being evaluated on retrieving answers from a markdown knowledge base. You start with no other context.\n\n"
        f"1. Read the skill file first: {REPO / 'skills' / 'gateway' / 'SKILL.md'}\n"
        "2. Follow it exactly, with one change: use graphify query as your navigation entry point instead of the brain's index. "
        "After reading the skill, call the Bash tool exactly once to run this command, using the question exactly as given:\n"
        f'graphify query "{row["question"]}" --budget 2000 --graph "{GRAPH.as_posix()}"\n'
        "Question logging is disabled by the environment. This query is local and does not call a model. "
        "Use only the note paths named by this query's NODE lines to choose the notes to read. "
        "Do not change the query, raise the budget, request other subgraphs, or work around an empty or truncated result. "
        "You may read index.md only if the query itself names it. "
        f"The brain root is: {BRAIN}\n"
        "3. Open files only with the Read tool, one file at a time, and only the skill file plus files inside the brain root "
        "that the query names. Do not use Glob, Grep, ls or any search across files or folders. "
        "Do not read graph.json, the wiki, or anything else. The Bash tool is allowed only for the single graphify query command above.\n\n"
        f"Question: {row['question']}\n\n"
        "Reply in exactly this shape:\n"
        "ANSWER: <your answer, from opened nodes only>\n"
        "FILES: <comma-separated paths you opened, relative to the brain root, in order>"
    )


def command(condition):
    args = [str(CLI), "--bare", "--agent", "Explore", "--model", MODEL,
            "--tools", "Read,Bash", "--allowedTools", "Read"]
    if condition == "R3":
        args += ["Bash(graphify query *)"]
    return args + ["--permission-mode", "dontAsk", "--strict-mcp-config", "--no-session-persistence",
                   "--add-dir", str(BRAIN), "--max-budget-usd", "1.00", "--output-format", "stream-json", "--verbose", "-p"]


def run_one(condition, row, out, env):
    qid = row["id"]
    started = time.perf_counter()
    start_utc = datetime.now(timezone.utc).isoformat()
    prompt = row[condition]
    events = []
    stdout_path = out / f"{qid}.events.jsonl"
    stderr_path = out / f"{qid}.stderr.txt"
    timed_out = False
    with stderr_path.open("w", encoding="utf-8") as err, stdout_path.open("w", encoding="utf-8") as log:
        # communicate() closes stdin so a noninteractive CLI never waits for an EOF.
        process = subprocess.Popen(command(condition), cwd=REPO, env=env, stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                   encoding="utf-8", errors="replace")
        try:
            stdout, stderr = process.communicate(prompt, timeout=240)
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate()
            timed_out = True
        stdout = redact(stdout, env)
        stderr = redact(stderr, env)
        err.write(stderr)
        for line in stdout.splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                event = {"unparsed_stdout": line}
            events.append(event)
            log.write(json.dumps(event, ensure_ascii=False) + "\n")
    final = next((e for e in reversed(events) if e.get("type") == "result"), {})
    calls = []
    seen = set()
    for event in events:
        if event.get("type") != "assistant":
            continue
        for block in event.get("message", {}).get("content", []):
            if block.get("type") != "tool_use" or block.get("id") in seen:
                continue
            seen.add(block.get("id"))
            calls.append({"name": block.get("name"), "input": block.get("input", {})})
    opened = [c["input"].get("file_path", "") for c in calls if c["name"] == "Read"]
    note_reads = []
    wiki_reads = []
    for path in opened:
        normalized = path.replace("\\", "/")
        if "/wiki/" in normalized:
            wiki_reads.append(path)
        elif normalized.startswith(BRAIN.as_posix() + "/") and Path(path).name != "index.md":
            note_reads.append(path)
    usage = final.get("usage", {})
    input_tokens = sum(usage.get(k, 0) for k in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"))
    output_tokens = usage.get("output_tokens", 0)
    metadata = {
        "id": qid, "condition": condition, "model": MODEL, "question": row["question"],
        "start_utc": start_utc, "end_utc": datetime.now(timezone.utc).isoformat(),
        "wall_time_s": time.perf_counter() - started, "cli_duration_s": final.get("duration_ms", 0) / 1000,
        "api_duration_s": final.get("duration_api_ms", 0) / 1000,
        "exit_code": process.returncode, "timed_out": timed_out,
        "success": process.returncode == 0 and not final.get("is_error", True) and bool(final.get("result")) and not timed_out,
        "terminal_reason": final.get("terminal_reason"), "subtype": final.get("subtype"),
        "answer": final.get("result", ""), "usage": usage, "total_tokens": input_tokens + output_tokens,
        "model_usage": final.get("modelUsage", {}), "actual_models": sorted(final.get("modelUsage", {})),
        "cost_usd_cli_reported": final.get("total_cost_usd"),
        "estimated_cost_usd_at_recorded_rates": (
            4 * usage.get("input_tokens", 0) + 20 * output_tokens +
            .2 * usage.get("cache_read_input_tokens", 0) + 5 * usage.get("cache_creation_input_tokens", 0)
        ) / 1e6,
        "cache_neutral_cost_usd_at_recorded_rates": (4 * input_tokens + 20 * output_tokens) / 1e6,
        "permission_denials": final.get("permission_denials", []), "tool_calls": calls,
        "tool_call_count": len(calls), "read_call_count": sum(c["name"] == "Read" for c in calls),
        "note_read_count": len(note_reads), "wiki_read_count": len(wiki_reads), "opened_paths": opened,
    }
    save(out / f"{qid}.json", metadata)
    return metadata


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("condition", choices=("pilot", "pilot-query", "R1", "R2", "R3"))
    parser.add_argument("--run-name", default="matched-run-1")
    options = parser.parse_args()
    env = load_env()
    rows = json.loads((HERE / "prompts-recovered.json").read_text(encoding="utf-8"))
    for row in rows:
        row["R3"] = query_prompt(row)
    if options.condition in ("pilot", "pilot-query"):
        is_query = options.condition == "pilot-query"
        out = HERE / ("runner-query-pilot" if is_query else "runner-tool-pilot")
        out.mkdir(exist_ok=False)
        row = {"id": "read-skill", "question": "Tool availability check", "R1": (
            f"Read this single file using the Read tool: {REPO / 'skills' / 'gateway' / 'SKILL.md'}. "
            "Reply only with its first heading. Do not run commands or open any other file.")}
        condition = "R1"
        if is_query:
            row = {"id": "query-check", "question": rows[0]["question"], "R3": (
                f'Read the skill file {REPO / "skills" / "gateway" / "SKILL.md"} first, then run exactly this Bash command:\n'
                f'graphify query "{rows[0]["question"]}" --budget 2000 --graph "{GRAPH.as_posix()}"\n'
                "Report only whether the command ran and how many nodes its header says it found. Do not open any other files.")}
            condition = "R3"
        result = run_one(condition, row, out, env)
        print(json.dumps(result), flush=True)
        return
    out = HERE / options.run_name / options.condition
    out.mkdir(parents=True, exist_ok=False)
    save(out / "prompts.json", [{"id": r["id"], "question": r["question"], "prompt": r[options.condition]} for r in rows])
    setup = {
        "model": MODEL, "agent": "Explore", "runner_version": "2.1.308", "bare": True,
        "tool_schema_for_every_condition": ["Read", "Bash"], "batch_sizes": [20, 5],
        "question_order": [r["id"] for r in rows], "question_timeout_s": 240, "question_budget_usd": 1.0,
        "privacy": {"query_logging_disabled": True, "session_persistence": False},
        "comparability": "R1 must be rerun: bare API runner has a different starting context from the original desktop subagents.",
        "gateway_sha256": hashlib.sha256((REPO / "skills" / "gateway" / "SKILL.md").read_bytes()).hexdigest(),
        "graph_sha256": hashlib.sha256(GRAPH.read_bytes()).hexdigest(),
    }
    save(out / "setup.json", setup)
    completed = []
    batches = []
    for batch_number, batch in enumerate((rows[:20], rows[20:]), 1):
        started = time.perf_counter()
        with ThreadPoolExecutor(max_workers=len(batch)) as executor:
            futures = {executor.submit(run_one, options.condition, row, out, env): row for row in batch}
            for future in as_completed(futures):
                value = future.result()
                completed.append(value)
                print(f"{options.condition} {value['id']}: success={value['success']}, notes={value['note_read_count']}, "
                      f"tools={value['tool_call_count']}, tokens={value['total_tokens']}, "
                      f"cost=${value['cost_usd_cli_reported']}, denied={len(value['permission_denials'])}", flush=True)
        batch_result = {"batch": batch_number, "questions": [r["id"] for r in batch], "wall_time_s": time.perf_counter() - started}
        batches.append(batch_result)
        save(out / "batches.json", batches)
        if any(not x["success"] or x["permission_denials"] or x["actual_models"] != [MODEL] for x in completed):
            raise RuntimeError("Incomplete run or tool/model mismatch; stop before starting the next batch")
    save(out / "results.json", sorted(completed, key=lambda x: [r["id"] for r in rows].index(x["id"])))


if __name__ == "__main__":
    main()
