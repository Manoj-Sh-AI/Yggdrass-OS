"""Extract exact child usage, tool calls, answers and timing from forwarded events."""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime
import json
from pathlib import Path

from run_matched import BRAIN, HERE, MODEL, save


def dt(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def collect(run_name, condition):
    directory = HERE / run_name / condition
    setup = json.loads((directory / "setup.json").read_text(encoding="utf-8"))
    state = Path(setup["state_directory"]).resolve()
    # Claude's nested project/session paths exceed Windows' ordinary path cap.
    long_state = Path("\\\\?\\" + str(state))
    raw_files = {p.stem.removeprefix("agent-"): p for p in long_state.glob("projects/**/subagents/agent-*.jsonl")}
    jobs = json.loads((directory / "jobs.json").read_text(encoding="utf-8"))
    expected = {j["description"]: j for j in jobs}
    groups = defaultdict(list)
    launches = {}
    notifications = []
    events = []
    for line in (directory / "dispatcher.events.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            events.append(json.loads(line))
    for event in events:
        parent_id = event.get("parent_tool_use_id")
        if parent_id:
            groups[parent_id].append(event)
        elif event.get("type") == "assistant":
            for block in event.get("message", {}).get("content", []):
                if block.get("type") == "tool_use" and block.get("name") in ("Agent", "Task"):
                    launches[block["id"]] = block["input"]
        elif event.get("type") == "system" and event.get("subtype") == "task_notification":
            notifications.append(event)
    results = []
    for parent_id, launch in launches.items():
        description = launch.get("description", "")
        job = expected.get(description)
        rows = groups.get(parent_id, [])
        agent_id = next((e.get("agent_id") for e in rows if e.get("agent_id")), None)
        raw_file = raw_files.get(agent_id)
        # Forwarded streaming tool calls have provisional output-token usage.
        # Only finalized on-disk child messages give the exact counts requested.
        if raw_file:
            raw_text = raw_file.read_text(encoding="utf-8")
            rows = [json.loads(line) for line in raw_text.splitlines() if line.strip()]
            transcripts = directory / "transcripts"
            transcripts.mkdir(exist_ok=True)
            (transcripts / f"{description.split()[-1]}.jsonl").write_text(raw_text, encoding="utf-8")
        child_messages = {}
        calls = {}
        timestamps = []
        answers = []
        errors = []
        for event in rows:
            if event.get("timestamp"):
                timestamps.append(event["timestamp"])
            message = event.get("message", {})
            if event.get("type") == "assistant":
                if message.get("id"):
                    child_messages[message["id"]] = message
                for block in message.get("content", []):
                    if block.get("type") == "tool_use":
                        calls[block.get("id")] = {"name": block.get("name"), "input": block.get("input", {})}
                    elif block.get("type") == "text" and block.get("text"):
                        answers.append(block["text"])
            elif event.get("type") == "user" and isinstance(message.get("content"), list):
                for block in message["content"]:
                    if block.get("type") == "tool_result" and block.get("is_error"):
                        errors.append(block.get("content"))
        usage = {k: sum(m.get("usage", {}).get(k, 0) for m in child_messages.values()) for k in
                 ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")}
        inputs = usage["input_tokens"] + usage["cache_read_input_tokens"] + usage["cache_creation_input_tokens"]
        outputs = usage["output_tokens"]
        ordered_calls = list(calls.values())
        opened = [c["input"].get("file_path", "") for c in ordered_calls if c["name"] == "Read"]
        note_reads = []
        wiki_reads = []
        for path in opened:
            normalized = path.replace("\\", "/")
            if "/wiki/" in normalized:
                wiki_reads.append(path)
            elif normalized.startswith(BRAIN.as_posix() + "/") and normalized.rsplit("/", 1)[-1] != "index.md":
                note_reads.append(path)
        models = sorted({m.get("model") for m in child_messages.values() if m.get("model")})
        result = {
            "id": description.split()[-1], "condition": condition, "description": description,
            "model": models, "prompt_exact": bool(job) and launch.get("prompt") == job["prompt"],
            "subagent_type": launch.get("subagent_type"), "launch_model": launch.get("model"),
            "prompt": launch.get("prompt"), "source": str(directory / "transcripts" / f"{description.split()[-1]}.jsonl"),
            "finalized_transcript_available": bool(raw_file), "agent_id": agent_id,
            "start_utc": min(timestamps) if timestamps else None, "end_utc": max(timestamps) if timestamps else None,
            "time_s": (dt(max(timestamps)) - dt(min(timestamps))).total_seconds() if timestamps else None,
            "usage": usage, "total_tokens": inputs + outputs,
            "cost_usd_at_recorded_rates": (4 * usage["input_tokens"] + 20 * outputs + .2 * usage["cache_read_input_tokens"]
                                           + 5 * usage["cache_creation_input_tokens"]) / 1e6,
            "cache_neutral_cost_usd": (4 * inputs + 20 * outputs) / 1e6,
            "tool_calls": ordered_calls, "tool_call_count": len(ordered_calls),
            "note_read_count": len(note_reads), "wiki_read_count": len(wiki_reads), "opened_paths": opened,
            "answers": answers, "answer": next((s for s in reversed(answers) if "ANSWER:" in s), ""),
            "tool_errors": errors,
        }
        save(directory / f"{result['id']}.json", result)
        results.append(result)
    order = [j["description"].split()[-1] for j in jobs]
    results.sort(key=lambda x: order.index(x["id"]) if x["id"] in order else len(order))
    save(directory / "results.json", results)
    anomalies = []
    if len(results) != len(jobs):
        anomalies.append(f"Launched {len(results)} of {len(jobs)} jobs")
    for r in results:
        if not r["finalized_transcript_available"]:
            anomalies.append(f"{r['id']}: missing finalized transcript; forwarded usage is provisional")
        if not r["prompt_exact"]:
            anomalies.append(f"{r['id']}: prompt differs")
        if r["model"] != [MODEL]:
            anomalies.append(f"{r['id']}: models {r['model']}")
        if not r["answer"] and condition != "pilot":
            anomalies.append(f"{r['id']}: no formatted answer")
        expected_no_match = condition == "R3" and r["tool_errors"] and all(
            "No matching nodes found" in str(error) for error in r["tool_errors"]
        )
        r["expected_query_no_match"] = bool(expected_no_match)
        if r["tool_errors"] and not expected_no_match:
            anomalies.append(f"{r['id']}: tool error")
        disallowed = [c["name"] for c in r["tool_calls"] if c["name"] not in ("Read", "Bash")]
        if disallowed:
            anomalies.append(f"{r['id']}: other tools {disallowed}")
    batches = []
    for number, batch in enumerate((results[:20], results[20:]), 1):
        if batch and all(r["start_utc"] and r["end_utc"] for r in batch):
            start = min(r["start_utc"] for r in batch)
            end = max(r["end_utc"] for r in batch)
            points = [(dt(r["start_utc"]), 1) for r in batch] + [(dt(r["end_utc"]), -1) for r in batch]
            count = peak = 0
            for _, change in sorted(points):
                count += change
                peak = max(peak, count)
            batches.append({"batch": number, "count": len(batch), "start": start, "end": end,
                            "span_s": (dt(end) - dt(start)).total_seconds(), "peak_active": peak})
    if len(batches) == 2 and batches[1]["start"] < batches[0]["end"]:
        anomalies.append("Second batch overlapped the first")
    summary = {
        "condition": condition, "count": len(results), "expected_count": len(jobs), "anomalies": anomalies,
        "notes_read": sum(r["note_read_count"] for r in results), "wiki_reads": sum(r["wiki_read_count"] for r in results),
        "tool_calls": sum(r["tool_call_count"] for r in results), "tokens": sum(r["total_tokens"] for r in results),
        "sum_question_time_s": sum(r["time_s"] or 0 for r in results),
        "answering_cost_usd_at_recorded_rates": sum(r["cost_usd_at_recorded_rates"] for r in results),
        "cache_neutral_answering_cost_usd": sum(r["cache_neutral_cost_usd"] for r in results),
        "batches": batches,
    }
    save(directory / "summary.json", summary)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("condition", choices=("pilot", "R1", "R2", "R3"))
    parser.add_argument("--run-name", default="matched-subagents-3")
    opts = parser.parse_args()
    collect(opts.run_name, opts.condition)
