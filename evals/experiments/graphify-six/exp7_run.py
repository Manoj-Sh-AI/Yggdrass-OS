"""Experiment 7: one fresh headless Claude Code session per question, per arm, per run.

Each session: `claude -p` on claude-haiku-5-5 in a scratch copy, project settings only, no
MCP servers, no session persistence, stream-json output. Records the answer, tokens (all
models, subagents included), tool calls, seconds and total_cost_usd.

Usage: python exp7_run.py <part: code|brain> <arm: A|B> <run> <workdir> <out.json> \
    [--cap <dollars>] [--ids id,id,...] <questions file>
The questions file is JSON: [{"id": ..., "question": ...}, ...].
"""

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

part, arm, run, workdir, out = sys.argv[1], sys.argv[2], int(sys.argv[3]), Path(sys.argv[4]), Path(sys.argv[5])
rest = sys.argv[6:]
cap = float(rest[rest.index("--cap") + 1]) if "--cap" in rest else None
questions = json.loads(Path(rest[-1]).read_text(encoding="utf-8"))
if "--ids" in rest:
    wanted = rest[rest.index("--ids") + 1].split(",")
    questions = [q for q in questions if q["id"] in wanted]

GRAPHIFY_CODE = (
    "A Graphify knowledge graph of this code is at graphify-out/graph.json. Use "
    '`graphify query "<question>"`, `graphify explain "<name>"` and `graphify path "<A>" "<B>"` '
    "first, then read only the files you need. "
)
GRAPHIFY_BRAIN = (
    "A Graphify knowledge graph of these notes is at graphify-out/graph.json. Use "
    '`graphify query "<question>"` and `graphify explain "<name>"` first to find the notes, '
    "then read them. "
)


def prompt(q: str) -> str:
    if part == "code":
        return (
            "Answer this question about the codebase in the current directory. "
            + (GRAPHIFY_CODE if arm == "A" else "")
            + "You may use subagents. Do not edit any file.\n\n"
            f"Question: {q}\n\nReply with ANSWER: <your answer> and then FILES: <files you read>."
        )
    return (
        "Answer the question from the markdown notes in the current directory only, never from "
        "your own knowledge. "
        + (GRAPHIFY_BRAIN if arm == "A" else "")
        + 'If the notes do not contain the answer, start your reply with "NOT IN BRAIN". '
        "You may use subagents. Do not edit any file.\n\n"
        f"Question: {q}\n\nReply with ANSWER: <your answer> and then FILES: <notes you read>."
    )


tools = ["Read", "Grep", "Glob", "Task", "Agent"] + (["Bash(graphify:*)"] if arm == "A" else [])
# Call the native binary, not the npm .cmd shim: cmd.exe cuts multi-line arguments.
npm_root = Path(shutil.which("claude.cmd") or shutil.which("claude")).parent
claude = str(npm_root / "node_modules" / "@anthropic-ai" / "claude-code" / "bin" / "claude.exe")
rows, spent = [], 0.0
for q in questions:
    if cap is not None and spent > cap:
        print(f"cap ${cap} passed (${spent:.3f}), stopping", flush=True)
        break
    cmd = [
        claude, "-p", "--model", "claude-haiku-5-5",
        "--allowedTools", *tools,
        "--setting-sources", "project", "--strict-mcp-config", "--no-session-persistence",
        "--output-format", "stream-json", "--verbose",
    ]
    start = time.perf_counter()
    p = subprocess.run(cmd, cwd=workdir, input=prompt(q["question"]), capture_output=True, text=True, encoding="utf-8")
    seconds = round(time.perf_counter() - start, 2)
    events = [json.loads(line) for line in p.stdout.splitlines() if line.strip().startswith("{")]
    result = next((e for e in reversed(events) if e.get("type") == "result"), {})
    tool_calls, tool_names = 0, {}
    for e in events:
        if e.get("type") == "assistant":
            for c in e.get("message", {}).get("content", []):
                if c.get("type") == "tool_use":
                    tool_calls += 1
                    tool_names[c["name"]] = tool_names.get(c["name"], 0) + 1
    tokens = 0
    for m in (result.get("modelUsage") or {}).values():
        tokens += sum(m.get(k, 0) for k in ("inputTokens", "outputTokens", "cacheReadInputTokens", "cacheCreationInputTokens"))
    cost = result.get("total_cost_usd") or 0.0
    spent += cost
    rows.append({
        "id": q["id"], "question": q["question"], "answer": result.get("result", ""),
        "is_error": result.get("is_error"), "subtype": result.get("subtype"),
        "num_turns": result.get("num_turns"), "tool_calls": tool_calls, "tool_names": tool_names,
        "tokens_total": tokens, "model_usage": result.get("modelUsage"), "cost_usd": cost,
        "seconds": seconds, "stderr": p.stderr[-2000:],
    })
    (out.parent / f"{out.stem}-{q['id']}.events.jsonl").write_text(p.stdout, encoding="utf-8")
    print(part, arm, run, q["id"], f"${cost:.4f}", tokens, tool_calls, seconds, flush=True)
    out.write_text(json.dumps({"part": part, "arm": arm, "run": run, "spent": spent, "rows": rows}, indent=2), encoding="utf-8")
