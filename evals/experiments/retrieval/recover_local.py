"""Recover this experiment's local evidence without changing Graphify or the brain."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from datetime import datetime, timezone

import yaml

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
BRAIN = Path(r"C:\Users\shman\yggdras-brain\demo-brain")
PROJECT = Path(r"C:\Users\shman\.claude\projects\C--Users-shman-OneDrive-Desktop-Yggdrass-OS-Yggdrass-OS")
OLD_SESSION = PROJECT / "3c0b9c67-90e7-4438-93e5-60bd1bf733ea"
FOLLOWUP_SESSION = PROJECT / "4def6ebb-4bae-4ed4-85d0-92ed32e7bd0c.jsonl"
GRAPH_DIR = HERE / "build" / "graphify-out"


def save(name, value):
    (HERE / name).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def records(path):
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            yield json.loads(line)


def text_content(value):
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(x.get("text", "") for x in value if isinstance(x, dict))
    return ""


def dt(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def recover_baseline(questions):
    by_question = {q["question"]: q["id"] for q in questions}
    found = {"R1": {}, "original_map": {}}
    for path in (OLD_SESSION / "subagents").glob("agent-*.jsonl"):
        lines = list(records(path))
        if not lines:
            continue
        prompt = text_content(lines[0].get("message", {}).get("content"))
        if not prompt.startswith("You are being evaluated on retrieving answers from a markdown knowledge base."):
            continue
        match = re.search(r"\nQuestion: (.*?)\n\nReply", prompt, re.S)
        if not match or match[1] not in by_question:
            continue
        condition = "original_map" if "brain's map" in prompt else "R1"
        qid = by_question[match[1]]
        messages = {}
        tools = []
        opened = []
        answers = []
        timestamps = []
        for row in lines:
            if row.get("timestamp"):
                timestamps.append(row["timestamp"])
            if row.get("type") != "assistant":
                continue
            message = row["message"]
            mid = message.get("id")
            if mid:
                messages[mid] = message
            for block in message.get("content", []):
                if block.get("type") == "tool_use":
                    if block.get("id") in {t["id"] for t in tools}:
                        continue
                    tools.append({"id": block.get("id"), "name": block.get("name"), "input": block.get("input")})
                    if block.get("name") == "Read":
                        opened.append(block["input"].get("file_path", ""))
                    elif block.get("name") == "SubagentHandback":
                        answers.append(block.get("input", {}))
                elif block.get("type") == "text" and block.get("text"):
                    answers.append(block["text"])
        usage = {key: sum(m.get("usage", {}).get(key, 0) for m in messages.values()) for key in
                 ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")}
        usage["total_tokens"] = sum(usage.values())
        models = sorted({m.get("model") for m in messages.values() if m.get("model")})
        notes = [p for p in opened if Path(p).name not in ("SKILL.md", "index.md", "graph.json")]
        result = {
            "id": qid, "question": match[1], "prompt": prompt, "source": str(path), "models": models,
            "usage": usage, "tool_calls": len(tools), "read_calls": sum(t["name"] == "Read" for t in tools),
            "notes_read": len(notes), "opened_paths": opened, "answer_records": answers,
            "start": min(timestamps), "end": max(timestamps),
            "time_s": (dt(max(timestamps)) - dt(min(timestamps))).total_seconds(),
            "estimated_cost_usd_at_recorded_rates": (
                4 * usage["input_tokens"] + 20 * usage["output_tokens"] +
                .2 * usage["cache_read_input_tokens"] + 5 * usage["cache_creation_input_tokens"]
            ) / 1e6,
            "cache_neutral_cost_usd_at_recorded_rates": (
                4 * (usage["input_tokens"] + usage["cache_read_input_tokens"] + usage["cache_creation_input_tokens"])
                + 20 * usage["output_tokens"]
            ) / 1e6,
        }
        if qid in found[condition]:
            raise RuntimeError(f"Ambiguous duplicate {condition}/{qid}; do not silently choose a run")
        found[condition][qid] = result
    for condition, values in found.items():
        if len(values) != 25:
            raise RuntimeError(f"Recovered {len(values)}/25 for {condition}")
    save("baseline-recovered.json", found)
    return found


def recover_prompts(questions, baseline):
    wiki = {}
    for row in records(FOLLOWUP_SESSION):
        if row.get("type") != "assistant":
            continue
        for block in row.get("message", {}).get("content", []):
            if block.get("type") != "tool_use" or block.get("name") != "Agent":
                continue
            agent = block.get("input", {})
            match = re.fullmatch(r"R2 ([a-z]\d\d)", agent.get("description", ""))
            if match:
                wiki[match[1]] = agent["prompt"]
    if len(wiki) != 20:
        raise RuntimeError(f"Expected 20 failed original R2 launch prompts, got {len(wiki)}")
    template = wiki["d01"]
    original_question = next(q["question"] for q in questions if q["id"] == "d01")
    output = []
    for q in questions:
        wiki_prompt = wiki.get(q["id"]) or template.replace("Question: " + original_question, "Question: " + q["question"])
        output.append({"id": q["id"], "question": q["question"], "R1": baseline["R1"][q["id"]]["prompt"],
                       "R2": wiki_prompt, "R2_source": "original launch" if q["id"] in wiki else "original template; question substituted"})
    save("prompts-recovered.json", output)


def audit_inputs():
    import graphify
    package = Path(graphify.__file__).parent
    manifest = json.loads((GRAPH_DIR / "manifest.json").read_text(encoding="utf-8"))
    current = {p.relative_to(BRAIN).as_posix(): p for p in BRAIN.rglob("*.md")}
    changed = []
    for rel, entry in manifest.items():
        p = BRAIN / rel
        actual = hashlib.md5(p.read_bytes(), usedforsecurity=False).hexdigest() if p.exists() else None
        if actual != entry.get("ast_hash"):
            changed.append(rel)
    graph = json.loads((GRAPH_DIR / "graph.json").read_text(encoding="utf-8"))
    sizes = {
        "brain_index_bytes": (BRAIN / "index.md").stat().st_size,
        "structural_graph_bytes": (BRAIN.parent / ".map" / "graph.json").stat().st_size,
        "graphify_graph_bytes": (GRAPH_DIR / "graph.json").stat().st_size,
        "wiki_index_bytes": (GRAPH_DIR / "wiki" / "index.md").stat().st_size,
        "wiki_total_bytes": sum(p.stat().st_size for p in (GRAPH_DIR / "wiki").glob("*.md")),
        "wiki_files": len(list((GRAPH_DIR / "wiki").glob("*.md"))),
    }
    cli = (package / "cli.py").read_text(encoding="utf-8")
    serve = (package / "serve.py").read_text(encoding="utf-8")
    install = (package / "install.py").read_text(encoding="utf-8")
    audit = {
        "checked_utc": datetime.now(timezone.utc).isoformat(),
        "installed_version": importlib.metadata.version("graphifyy"), "package": str(package),
        "package_source_sha256": {name: hashlib.sha256((package / name).read_bytes()).hexdigest()
                                   for name in ("serve.py", "cli.py", "install.py")},
        "corpus_manifest_files": len(manifest), "current_markdown_files": len(current),
        "changed_or_missing_since_build": changed, "added_since_build": sorted(set(current) - set(manifest)),
        "graph_reusable": not changed and set(current) == set(manifest),
        "corpus_sha256": {rel: hashlib.sha256(p.read_bytes()).hexdigest() for rel, p in current.items()},
        "gateway_sha256": hashlib.sha256((REPO / "skills" / "gateway" / "SKILL.md").read_bytes()).hexdigest(),
        "sizes": sizes, "graph_nodes": len(graph.get("nodes", [])),
        "graph_edges": len(graph.get("links", graph.get("edges", []))),
        "features": {
            "budgeted_BFS": "def _bfs(" in serve and "def _subgraph_to_text(" in serve and "token_budget" in serve,
            "query_budget": 'elif cmd == "query"' in cli and '"--budget"' in cli,
            "query_dfs": '"--dfs"' in cli, "path": 'elif cmd == "path"' in cli,
            "explain": 'elif cmd == "explain"' in cli,
            "MCP_tools": {name: name in serve for name in ("query_graph", "get_node", "get_neighbors", "shortest_path")},
            "serve_module_main": '__name__ == "__main__"' in serve,
            "export_wiki": '"wiki"' in cli,
        },
        "install_relevant_lines": [f"{i}: {line.strip()}" for i, line in enumerate(install.splitlines(), 1)
            if ("GRAPH_REPORT.md" in line and ("Read" in line or "read" in line)) or "first run `graphify query" in line],
        "constraint": "No Graphify, brain, plan, register, or scoping changes; no rebuild or upgrade.",
    }
    save("input-audit.json", audit)
    return audit


def probes(questions):
    output_dir = HERE / "query-probes"
    output_dir.mkdir(exist_ok=True)
    env = dict(os.environ, GRAPHIFY_QUERY_LOG_DISABLE="1", PYTHONIOENCODING="utf-8")
    results = []
    for budget in (2000, 500):
        selected = questions if budget == 2000 else [q for q in questions if q["id"] in ("d01", "d02", "m01", "p01", "n01")]
        for q in selected:
            started = time.perf_counter()
            result = subprocess.run([sys.executable, "-m", "graphify", "query", q["question"], "--budget", str(budget),
                                     "--graph", str(GRAPH_DIR / "graph.json")],
                                    capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, timeout=45)
            (output_dir / f"{q['id']}-{budget}.txt").write_text(result.stdout, encoding="utf-8")
            (output_dir / f"{q['id']}-{budget}.stderr.txt").write_text(result.stderr, encoding="utf-8")
            paths = re.findall(r"\[src=(.*?) loc=", result.stdout)
            results.append({"id": q["id"], "budget": budget, "exit_code": result.returncode,
                            "time_s": time.perf_counter() - started,
                            "characters": len(result.stdout), "approx_tokens_at_graphify_3_chars": len(result.stdout) / 3,
                            "truncated": "truncated" in result.stdout.lower(),
                            "over_budget_notice": "Complete answer over budget" in result.stdout,
                            "node_lines": len(paths), "unique_note_paths": list(dict.fromkeys(paths)),
                            "output": f"query-probes/{q['id']}-{budget}.txt"})
            print(f"Query probe {q['id']} / {budget}: {len(paths)} nodes, {len(result.stdout)} chars", flush=True)
    save("query-probes.json", results)
    return results


def main():
    questions = yaml.safe_load((BRAIN.parent / "demo-evals" / "questions.yaml").read_text(encoding="utf-8"))["questions"]
    baseline = recover_baseline(questions)
    recover_prompts(questions, baseline)
    audit = audit_inputs()
    print(json.dumps({"baseline_recovered": len(baseline["R1"]), "original_map_recovered": len(baseline["original_map"]),
                      "reusable_graph": audit["graph_reusable"], "sizes": audit["sizes"]}), flush=True)
    if "--probes" in sys.argv:
        if not audit["graph_reusable"]:
            raise RuntimeError("Corpus changed; do not run probes on a stale graph")
        probes(questions)


if __name__ == "__main__":
    main()
