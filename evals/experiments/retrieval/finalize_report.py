"""Write the local comparison, including measured protocol deviations."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

import yaml

from run_matched import BRAIN, GRAPH, HERE, MODEL, REPO, save

RUN = "matched-subagents-3"
LABELS = {"R1": "Plain index", "R2": "Wiki first", "R3": "Query, budget 2000"}


def normalized(value):
    return re.sub(r"/+", "/", value.replace("\\", "/")).casefold()


def source_path(value):
    prefix = normalized(str(BRAIN)) + "/"
    path = normalized(value)
    return path[len(prefix):] if path.startswith(prefix) else None


def tool_text(value):
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(x.get("text", "") for x in value if isinstance(x, dict))
    return ""


def audit_question(condition, row, question):
    transcript = Path(row["source"])
    records = [json.loads(line) for line in transcript.read_text(encoding="utf-8").splitlines() if line.strip()]
    message_reads = defaultdict(set)
    bash_ids = set()
    query_output = ""
    for event in records:
        message = event.get("message", {})
        if event.get("type") == "assistant":
            for block in message.get("content", []):
                if block.get("type") != "tool_use":
                    continue
                if block.get("name") == "Read":
                    message_reads[message["id"]].add(block["id"])
                elif block.get("name") == "Bash":
                    bash_ids.add(block["id"])
        elif event.get("type") == "user" and isinstance(message.get("content"), list):
            for block in message["content"]:
                if block.get("type") == "tool_result" and block.get("tool_use_id") in bash_ids:
                    query_output += tool_text(block.get("content", ""))
    source_notes = {p for value in row["opened_paths"] if (p := source_path(value))}
    required = {p.casefold() for p in question.get("expected_nodes", []) if p != "index.md"}
    missing = sorted(required - source_notes)
    parallel = [len(value) for value in message_reads.values() if len(value) > 1]
    violations = []
    skill = normalized(str(REPO / "skills" / "gateway" / "SKILL.md"))
    if not row["opened_paths"] or normalized(row["opened_paths"][0]) != skill:
        violations.append("First opened file was not the gateway skill")
    wiki_root = normalized(str(HERE / "build" / "graphify-out" / "wiki")) + "/"
    for value in row["opened_paths"]:
        n = normalized(value)
        if n == skill or source_path(value) is not None or (condition == "R2" and n.startswith(wiki_root)):
            continue
        violations.append("Read outside permitted roots: " + value)
    commands = [c["input"].get("command", "") for c in row["tool_calls"] if c["name"] == "Bash"]
    if condition == "R3":
        expected_command = f'graphify query "{question["question"]}" --budget 2000 --graph "{GRAPH.as_posix()}"'
        if commands != [expected_command]:
            violations.append("Query command/count differs from the fixed one-query condition")
        named = set(re.findall(r"\[src=(.*?) loc=", query_output))
        if not named and "nodes" not in query_output and row["id"] != "m05":
            violations.append("Query output was unavailable for path verification")
        not_named = sorted(source_notes - {p.casefold() for p in named})
        if not_named:
            violations.append("Read notes not named by query: " + ", ".join(not_named))
    elif commands:
        violations.append("Bash used outside query condition")
    if any(c["name"] not in ("Read", "Bash") for c in row["tool_calls"]):
        violations.append("Other tool used")
    return {"missing_required_note_paths": missing, "parallel_read_request_sizes": parallel,
            "access_or_query_violations": violations,
            "query_named_paths": sorted(set(re.findall(r"\[src=(.*?) loc=", query_output))) if condition == "R3" else [],
            "query_no_match": condition == "R3" and "No matching nodes found" in query_output}


def main():
    questions = yaml.safe_load((BRAIN.parent / "demo-evals" / "questions.yaml").read_text(encoding="utf-8"))["questions"]
    qmap = {q["id"]: q for q in questions}
    comparison = {"created_utc": datetime.now(timezone.utc).isoformat(), "run": RUN,
                  "grading": "Assistant semantic review against supplied expected_answer and required_facts; required-note and tool audits reported separately. Not an owner-issued release-gate verdict.",
                  "conditions": {}, "per_question": []}
    failure_notes = {
        "d02": "Refused: the query's import-context heuristic returned five seed notes but omitted areas/beech-aircraft.md. The oxygen note's link names Beech, but its facts do not identify the builder.",
        "d09": "Refused: the Launch Complex 34 / 1967-01-27 question returned only an Apollo 11 alarms/report subgraph, with no Apollo 1 note.",
        "m04": "Refused: retrieved Apollo 8/program notes, but not the Saturn V or Wernher von Braun note needed to identify the developer and centre.",
        "m05": "Refused: the unchanged question returned 'No matching nodes found' (CLI exit 4); no notes could be read.",
    }
    all_rows = {}
    for condition in ("R1", "R2", "R3"):
        directory = HERE / RUN / condition
        summary = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
        assert not summary["anomalies"], (condition, summary["anomalies"])
        rows = json.loads((directory / "results.json").read_text(encoding="utf-8"))
        assert len(rows) == 25
        dispatcher = json.loads((directory / "dispatcher-result.json").read_text(encoding="utf-8"))
        all_rows[condition] = {r["id"]: r for r in rows}
        summary["answer_content_correct"] = 0
        summary["required_source_check_passed"] = 0
        summary["parallel_read_questions"] = []
        summary["dispatcher_wall_time_s"] = dispatcher["wall_time_s"]
        summary["answering_plus_dispatcher_cost_usd"] = dispatcher["total_cost_usd"]
        summary["dispatcher_cost_usd"] = dispatcher["total_cost_usd"] - summary["answering_cost_usd_at_recorded_rates"]
        summary["cache_neutral_answering_plus_dispatcher_cost_usd"] = sum(
            (4 * (m["inputTokens"] + m["cacheReadInputTokens"] + m["cacheCreationInputTokens"]) + 20 * m["outputTokens"]) / 1e6
            for batch in dispatcher["batch_results"] for m in batch["result"]["modelUsage"].values()
        )
        for row in rows:
            assert row["model"] == [MODEL] and row["prompt_exact"]
            audit = audit_question(condition, row, qmap[row["id"]])
            assert not audit["access_or_query_violations"], (condition, row["id"], audit)
            correct = not (condition == "R3" and row["id"] in failure_notes)
            if qmap[row["id"]]["kind"] != "negative":
                refused = bool(re.search(r"ANSWER:\s*I (?:don't|do not) have that", row["answer"], re.I))
                assert refused == (not correct), (condition, row["id"], "Refusal and manual verdict disagree")
            evidence = correct and not audit["missing_required_note_paths"]
            summary["answer_content_correct"] += int(correct)
            summary["required_source_check_passed"] += int(evidence)
            if audit["parallel_read_request_sizes"]:
                summary["parallel_read_questions"].append(row["id"])
            notes = []
            if not correct:
                notes.append(failure_notes[row["id"]])
            if condition == "R2" and row["id"] == "m01":
                notes.append("Correct name, but the commander claim came from a link/index description; people/jim-lovell.md was not opened. Violates the gateway's facts-only grounding rule.")
            if condition == "R2" and row["id"] == "m03":
                notes.append("Required answer facts were supported, but the extra thermostatic-switch explanation was taken from frontmatter description rather than an opened fact line.")
            if audit["parallel_read_request_sizes"]:
                notes.append("Multiple Read requests in one model message, contrary to one-file-at-a-time instruction.")
            comparison["per_question"].append({"condition": condition, "id": row["id"], "answer_content_correct": correct,
                "required_source_check_passed": evidence, "grading_notes": notes, "audit": audit,
                "metrics": {k: row[k] for k in ("note_read_count", "wiki_read_count", "tool_call_count", "total_tokens", "time_s", "cost_usd_at_recorded_rates", "cache_neutral_cost_usd")}})
        comparison["conditions"][condition] = summary
    audit = json.loads((HERE / "input-audit.json").read_text(encoding="utf-8"))
    current_paths = {p.relative_to(BRAIN).as_posix() for p in BRAIN.rglob("*.md")}
    unchanged = current_paths == set(audit["corpus_sha256"]) and all(
        hashlib.sha256((BRAIN / rel).read_bytes()).hexdigest() == value for rel, value in audit["corpus_sha256"].items())
    package = Path(audit["package"])
    graphify_unchanged = all(hashlib.sha256((package / rel).read_bytes()).hexdigest() == value for rel, value in audit["package_source_sha256"].items())
    comparison["final_integrity"] = {"corpus_unchanged": unchanged, "graphify_source_unchanged": graphify_unchanged,
        "graph_matches_pre_run_hash": hashlib.sha256(GRAPH.read_bytes()).hexdigest() == json.loads(
            (HERE / "matched-run-1" / "R1" / "setup.json").read_text(encoding="utf-8"))["graph_sha256"],
        "gateway_unchanged": hashlib.sha256((REPO / "skills" / "gateway" / "SKILL.md").read_bytes()).hexdigest() == audit["gateway_sha256"]}
    assert all(comparison["final_integrity"].values())
    probes = json.loads((HERE / "query-probes.json").read_text(encoding="utf-8"))
    comparison["query_probes"] = probes
    save(HERE / "comparison.json", comparison)
    summaries = comparison["conditions"]
    baseline = summaries["R1"]
    lines = ["# Retrieval follow-up — Apollo demo, 25 October 2026", "",
        "Neither alternative beat the plain-index baseline at equal answer quality in this run. Wiki-first kept answer content correct but added cost and reads; query-first lost four answerable questions. Query-first's small token saving came with lower accuracy and higher observed cost and time.", "",
        "**Protocol caveat:** this is not a clean replication of strict one-file-at-a-time execution. Some agents requested two Read calls in a single message despite the unchanged instruction. These are retained and flagged, not silently rerun. Content correctness is separate from grounding and instruction compliance. No condition is being declared to have passed the full project release gate.", "",
        "## Measured comparison", "",
        "All scores below were reviewed against the existing answer key. Rates are the same recorded Opus 5.5 rates used previously: $4/M input, $20/M output, $0.20/M cache reads, $5/M cache writes. Cost is answering agents only in the first table.", "",
        "| Condition | Correct content | Required-source check | Brain notes read | Tool calls | Tokens processed | Sum of question times | Observed cost | No-cache cost |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for c, s in summaries.items():
        lines.append(f"| {c}: {LABELS[c]} | {s['answer_content_correct']}/25 | {s['required_source_check_passed']}/25 | {s['notes_read']} | {s['tool_calls']} | {s['tokens']:,} | {s['sum_question_time_s']:.1f} s | ${s['answering_cost_usd_at_recorded_rates']:.3f} | ${s['cache_neutral_answering_cost_usd']:.3f} |")
    lines += ["", "Notes exclude the skill, brain index, graph, and wiki. Wiki-first additionally read 49 wiki files, including index reads. Tool calls count all actual Read/Bash requests. Tokens include all cache reads; usage comes from finalized child transcripts, deduplicated by message ID. Streaming event usage is provisional and was not used for the totals.", "",
        "| Alternative versus R1 | Tokens | Observed answering cost | No-cache answering cost | Sum of question times |",
        "|---|---:|---:|---:|---:|"]
    for c in ("R2", "R3"):
        s = summaries[c]
        ratios = [100 * (s[k] / baseline[k] - 1) for k in ("tokens", "answering_cost_usd_at_recorded_rates", "cache_neutral_answering_cost_usd", "sum_question_time_s")]
        lines.append(f"| {c} | " + " | ".join(f"{v:+.1f}%" for v in ratios) + " |")
    lines += ["", "### Changed answers and grounding", "",
        "- R3 d02: could not verify Beech Aircraft as the tank builder. The query chose an `import` context and omitted the builder note, even though an opened note's link named it. The agent correctly refused to treat that link as a fact.",
        "- R3 d09: could not answer the Apollo 1 fire question because it received only Apollo 11 alarm/report nodes for Launch Complex 34 and 1967-01-27. It opened no unrelated notes.",
        "- R3 m04: could not identify Wernher von Braun or Marshall Space Flight Center because neither supporting note was returned.",
        "- R3 m05: returned `No matching nodes found` (exit 4) for the capsule-communicator question, so it could not establish Charlie Duke/Apollo 16. This is a retrieval outcome, not an infrastructure failure to retry.",
        "- R2 m01: Jim Lovell was the correct answer, but the agent explicitly relied on a link and index description and did not open his fact note. Thus 25/25 content does **not** mean 25/25 grounded retrieval.",
        "- R2 m03: the core answer was supported; an extra explanation about thermostatic switches came from frontmatter description rather than fact lines.",
        "- All three flagged d08 as an agent's inference, and all three refused all five negative questions. Other required answers retained their meaning; wording and extra context varied.", "",
        "Full answers and expected facts: [answers.md](answers.md). Exact per-question metrics and audits: [comparison.json](comparison.json).",
        "", "## Step 0: installed code", "",
        "The installed pin is **graphifyy 0.9.95**. Its source already contains budgeted BFS and the requested retrieval paths, so the premise that these necessarily require a later version does not hold for this installation. No upgrade was needed or attempted; no newer pin or migration cost is proposed.", "",
        "| Capability | Installed result |", "|---|---|",
        "| Budgeted BFS | Present in `serve.py`: `_bfs`, `_subgraph_to_text`, `_query_graph_text` |",
        "| `query --budget`, `query --dfs`, `path`, `explain` | CLI branches present |",
        "| Wiki | `graphify export wiki`; `--wiki` is a Graphify skill flag rather than a standalone CLI switch |",
        "| Serve / MCP | `python -m graphify.serve <graph>` and `graphify-mcp`; `--mcp` is a skill flag. No literal `graphify serve` CLI branch |",
        "| MCP tools | `query_graph`, `get_node`, `get_neighbors`, `shortest_path` present |",
        "| Report-first text | Main navigation guidance is query-first. A leftover Kilo plugin reminder still says to read the report before searching (`install.py:1562`); not every installer surface is fixed |", "",
        "Source locations, hashes, and relevant installer lines are saved in [input-audit.json](input-audit.json). Graphify was not edited.", "",
        "## Reused graph and wiki sizes", "",
        "The already rebuilt graph matches all 43 current markdown files against its manifest: no additions, changes, or missing files. It has 78 nodes and 112 edges. It was reused without another paid rebuild or wiki regeneration. The existing build log estimates its earlier extraction at $0.4000; that is not a new charge from this resumption.", "",
        "| Artifact | Bytes |", "|---|---:|"]
    for key, label in (("brain_index_bytes", "Brain index"), ("wiki_index_bytes", "Wiki index"), ("wiki_total_bytes", "Entire wiki, 21 files"), ("graphify_graph_bytes", "Graphify graph.json"), ("structural_graph_bytes", "Yggdras structural graph.json")):
        lines.append(f"| {label} | {audit['sizes'][key]:,} |")
    lines += ["", "The wiki index is small, but it often requires an article and then a fallback to the brain index; a smaller first file did not produce a cheaper complete route.", "",
        "## Budget behavior, without workarounds", "",
        "All 25 unchanged questions were probed at budget 2000; five were also probed at 500. None of the 2000-budget probes truncated node lines. Instead, **16/25 exceeded the requested budget**: once all nodes fit, this installation retains every edge as well. Four of the five 500-budget probes cut nodes, with an explicit warning.", "",
        "| Example | Result | Evidence |", "|---|---|---|",
        "| d01, 2000 | 41 nodes; 8,530 output characters including header/warning. Body reports about 2,665 tokens and retains all nodes/edges | [raw output](query-probes/d01-2000.txt) |",
        "| d02, 2000 | Five seed nodes under an `import` heuristic; no builder note | [raw output](query-probes/d02-2000.txt) |",
        "| d09, 2000 | Apollo 11 alarms/report subgraph for an Apollo 1 question | [raw output](query-probes/d09-2000.txt) |",
        "| m04, 2000 | Returned paths omit the needed Saturn V/developer notes | [raw output](query-probes/m04-2000.txt) |",
        "| m05, 2000 | No matching nodes | [raw output](query-probes/m05-2000.txt) |",
        "| d01, 500 | 15/41 nodes shown, 26 cut; unrelated Apollo 1/13 and crew-swap seeds consume space | [raw output](query-probes/d01-500.txt) |",
        "| p01, 500 | 13/51 nodes shown, 38 cut; the required report-chunk seed is retained, alongside Apollo 13/board and other seeds | [raw output](query-probes/p01-500.txt) |", "",
        "The reported 2k truncation was not reproduced on these inputs. Oversized responses, code-oriented context selection, irrelevant seeds, and missing required notes were observed. No seeds, filters, larger budgets, revised questions, extra queries, or fallback reads were used to rescue R3. The 500-budget runs are navigation probes only, not additional scored answering-agent conditions.", "",
        "## Comparability, timing, and costs", "",
        "The original desktop runner was not authenticated in this process. A bundled Claude Code 2.1.308 runner was located and used with the project's configured Anthropic key. Its starting context differs from the old desktop session, so R1 was rerun rather than mixing old absolute token/cost figures into this comparison. Every scored question used a fresh Explore child, verified as `claude-opus-5-5`, with the same gateway skill. R1 and R2 launch prompts match the recovered originals exactly; the final five R2 prompts substitute only their question into the recovered template. R3 uses one unchanged-question query followed only by note paths it returns.", "",
        "Each condition uses the same first 20 questions, followed by the same five negatives. A process barrier enforces that batch two starts after batch one finishes. The dispatcher streams child launches: the measured first-batch peak was six active children for each condition, not 20 simultaneously. Final-batch peaks were 3/4/5. Thus batching matches, but latency still includes different launch overlap and cannot be read as a tightly controlled algorithm benchmark. Per-batch spans and peaks are in the summaries.", "",
        "The one-file-at-a-time instruction was not perfectly obeyed: R1 m03, R2 m03, and R3 m01/n04 requested pairs of Read calls in the same model message. R3 m01 did so twice. These observations are saved in the audit and weaken strict protocol claims; the alternatives still did not achieve a better equal-quality result.", "",
        "| Condition | End-to-end wall time, including dispatch | Answering + dispatch cost | No-cache answering + dispatch cost |",
        "|---|---:|---:|---:|"]
    for c, s in summaries.items():
        lines.append(f"| {c} | {s['dispatcher_wall_time_s']:.1f} s | ${s['answering_plus_dispatcher_cost_usd']:.3f} | ${s['cache_neutral_answering_plus_dispatcher_cost_usd']:.3f} |")
    lines += ["", f"The three completed comparison conditions cost ${sum(s['answering_plus_dispatcher_cost_usd'] for s in summaries.values()):.3f} including dispatch, of which ${sum(s['answering_cost_usd_at_recorded_rates'] for s in summaries.values()):.3f} was answering agents. These are observed API/list-rate costs, not an account-invoice reconciliation. Cache-neutral cost reprices every processed input token, including cache reads/writes, at $4/M.", "",
        "Excluded setup attempts are preserved: a tiny model check, Read/query tool checks, a 20-native-process batch with ten startup exits, a minimal-mode dispatcher with no Agent tool, and a dispatcher-only run that overlapped the second batch by a few seconds. No failed/overlapped attempt was spliced into the scored comparison. Their reported costs total about $2.636; some timed-out connection checks returned no usage, so their billing is unknown. The retained comparison uses one measured run per condition; there are no repeated-run confidence estimates.", "",
        "## Files and state", "",
        "- [Final condition data](matched-subagents-3/) contains exact jobs, dispatcher traces, finalized per-question child transcripts, usage, answers, and batch summaries.",
        "- [Recovered old baseline](baseline-recovered.json) preserves the original 25 no-map and 25 whole-map transcripts' aggregates for reference; it is not the control for this new runner.",
        "- [Recovered original prompts](prompts-recovered.json) preserve the R1 prompts and the failed R2 launch prompts/template.",
        "- [Query probes](query-probes.json) retain measured sizes, paths, truncation, timings, and links to raw outputs.",
        "- Brain facts, gateway skill, installed Graphify, decision register, plan, and existing scoping edit were not changed. No commits, PRs, merges, upgrades, or new graph builds were made.", ""]
    (HERE / "README.md").write_text("\n".join(lines), encoding="utf-8")
    answers = ["# Answer review", "", "Content grading and protocol observations are separate. The answer key is unchanged.", ""]
    for q in questions:
        answers += [f"## {q['id']}: {q['question']}", "", "Expected: " + q["expected_answer"], ""]
        for c in ("R1", "R2", "R3"):
            answers += [f"### {c}: {LABELS[c]}", "", all_rows[c][q["id"]]["answer"], ""]
    (HERE / "answers.md").write_text("\n".join(answers), encoding="utf-8")
    print(json.dumps({"conditions": summaries, "integrity": comparison["final_integrity"]}, indent=2))


if __name__ == "__main__":
    main()
