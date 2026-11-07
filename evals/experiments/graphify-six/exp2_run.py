"""Experiment 2 (and 3): answer arms over question files, one question at a time.

Arms:
  A        retrieve.py as is (pick, gather, cited answer)
  B        whole demo brain as cached search_result blocks, one cited answer call
  C        A plus one fallback: on a decline, a structured call picks up to 2 gathered
           nodes whose unsent neighbours are added; then a second cited answer call
  D        hybrid: graphify query --budget 2000 picks notes, our fact lines are sent
  D-strip  D with every _CONTEXT_HINTS word removed from the query text (experiment 3b)
  D-seed   our pick's notes as --seed for `graphify query "notes"`, plus `graphify
           explain` on each seed label; all names mapped to slugs (experiment 3c)

Usage (from the repo root):
    uv run --project app --with anthropic python evals/experiments/graphify-six/exp2_run.py \
        <arm> <run> <demo-brain> <graph.json> <retrieve.py dir> <out.json> <questions.yaml> [...]
"""

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import yaml

arm, run = sys.argv[1], int(sys.argv[2])
brain, graph_json, retrieve_dir, out = (Path(a) for a in sys.argv[3:7])
qfiles = sys.argv[7:]
sys.path.insert(0, str(retrieve_dir))

from retrieve import (  # noqa: E402
    MODEL,
    Retriever,
    answer,
    display_text,
    edges_of,
    fact_lines,
    ms,
    note_text,
    pick,
    search_results,
    status_of,
    usage_row,
)

from yggdras.data.graph.structural import normalize  # noqa: E402

HINT_WORDS = {
    "call", "calls", "called", "invoke", "invokes", "invoked",
    "import", "imports", "imported", "module", "modules",
    "field", "fields", "member", "members", "property", "properties",
    "parameter", "parameters", "param", "params", "argument", "arguments",
    "return", "returns", "returned",
    "generic", "generics", "template", "templates",
}  # 0.9.95 serve.py _CONTEXT_HINTS, copied verbatim
NODE_RE = re.compile(r"^NODE (?P<label>.+?) \[src=(?P<src>[^ ]+)")
EXPAND_INSTRUCTION = (
    "The answer to the question was not found in the notes listed below. Pick the 1 or 2 "
    "notes whose linked neighbours are most likely to hold the missing facts."
)

r = Retriever(brain)
by_slug = {n["slug"]: n for n in r.graph["nodes"]}
by_path = {n["path"]: n["slug"] for n in r.graph["nodes"]}
lookup: dict[str, set[str]] = {}
for n in r.graph["nodes"]:
    for name in [n["slug"], n["name"], *n["aliases"]]:
        lookup.setdefault(normalize(name), set()).add(n["slug"])


def block(slug: str, extra: list[str] | None = None, cache: bool = False) -> dict | None:
    lines = fact_lines(note_text(brain, by_slug[slug])) + (extra or [])
    if not lines:
        return None
    b = {
        "type": "search_result",
        "source": slug,
        "title": by_slug[slug]["name"],
        "content": [{"type": "text", "text": line} for line in lines],
        "citations": {"enabled": True},
    }
    if cache:
        b["cache_control"] = {"type": "ephemeral"}
    return b


def graphify(*args: str) -> tuple[str, float]:
    env = {**os.environ, "GRAPHIFY_QUERY_LOG_DISABLE": "1"}
    start = time.perf_counter()
    p = subprocess.run(["graphify", *args, "--graph", str(graph_json)], capture_output=True, text=True, encoding="utf-8", env=env)
    return p.stdout, ms(start)


def to_slug(label: str, src: str) -> str | None:
    hits = lookup.get(normalize(label), set())
    return next(iter(hits)) if len(hits) == 1 else by_path.get(src)


def slugs_from(output: str) -> list[str]:
    nodes = [m.groupdict() for line in output.splitlines() if (m := NODE_RE.match(line))]
    return list(dict.fromkeys(s for n in nodes if (s := to_slug(n["label"], n["src"]))))


WHOLE = [b for n in r.graph["nodes"] if (b := block(n["slug"], [f"Link: {e['line']}" for e in edges_of(r.graph, n)]))]
WHOLE[-1]["cache_control"] = {"type": "ephemeral"}


def finish(q: dict, start: float, calls: list[dict], ans: dict, first_from: float, **extra) -> dict:
    return {
        "id": q["id"],
        "set": Path(extra.pop("qfile")).stem,
        "question": q["question"],
        "status": status_of(ans["raw_answer"]),
        "answer": display_text(ans["raw_answer"]),
        "raw_answer": ans["raw_answer"],
        "cited_sources": sorted({c["source"] for c in ans["citations"]}),
        "total_in": sum(c["total_in"] for c in calls),
        "billed_equiv_in": round(sum(c["billed_equiv_in"] for c in calls), 1),
        "output_tokens": sum(c["output_tokens"] for c in calls),
        "cost_usd": sum(c["cost_usd"] for c in calls),
        "first_token_ms": round(first_from + ans["first_token_ms"], 3),
        "end_to_end_ms": ms(start),
        **extra,
    }


def run_question(q: dict, qfile: str) -> dict:
    start = time.perf_counter()
    question = q["question"]
    if arm == "A":
        res = r.ask(question)
        return {
            "id": q["id"], "set": Path(qfile).stem, "question": question, "picked": res["picked"],
            "status": res["status"], "answer": res["answer"], "raw_answer": res["raw_answer"],
            "cited_sources": sorted({c["source"] for c in res["citations"]}),
            "total_in": res["total_in"], "billed_equiv_in": res["billed_equiv_in"],
            "output_tokens": res["output_tokens"], "cost_usd": res["cost_usd"],
            "first_token_ms": res["first_token_ms"], "end_to_end_ms": res["end_to_end_ms"],
        }
    if arm == "B":
        ans = answer(r.client, question, WHOLE)
        return finish(q, start, [ans], ans, 0.0, qfile=qfile, notes_sent=len(WHOLE))
    if arm == "C":
        picked, pu = pick(r.client, r.system, r.slugs, question)
        blocks = search_results(brain, r.graph, picked)
        ans = answer(r.client, question, blocks)
        calls, turns, expanded = [pu, ans], 1, []
        first_from = pu["full_ms"]
        if status_of(ans["raw_answer"]) == "not_in_brain" and blocks:
            sent = [b["source"] for b in blocks]
            schema = {
                "type": "object",
                "properties": {"expand": {"type": "array", "items": {"type": "string", "enum": sent}}},
                "required": ["expand"], "additionalProperties": False,
            }
            listing = "\n".join(f"{s} | {by_slug[s]['name']}" for s in sent)
            t = time.perf_counter()
            with r.client.messages.stream(
                model=MODEL, max_tokens=256, thinking={"type": "disabled"},
                output_config={"effort": "low", "format": {"type": "json_schema", "schema": schema}},
                messages=[{"role": "user", "content": f"{EXPAND_INSTRUCTION}\n\nQuestion: {question}\n\nNotes:\n{listing}"}],
            ) as s:
                final = s.get_final_message()
            calls.append(usage_row(final.usage, t))
            expanded = list(dict.fromkeys(json.loads(final.content[0].text)["expand"]))[:2]
            new = [n for s_ in expanded for n in dict.fromkeys(e["neighbour"] for e in edges_of(r.graph, by_slug[s_])) if n not in sent]
            blocks = blocks + [b for n in dict.fromkeys(new) if (b := block(n))]
            first_from = ms(start)
            ans = answer(r.client, question, blocks)
            calls.append(ans)
            turns = 2
        return finish(q, start, calls, ans, first_from, qfile=qfile, picked=picked, turns=turns, expanded=expanded,
                      notes_sent=len(blocks))
    if arm in ("D", "D-strip"):
        text = question
        if arm == "D-strip":
            text = " ".join(w for w in question.split() if w.strip("?,.").lower() not in HINT_WORDS)
        output, qms = graphify("query", text, "--budget", "2000")
        header = output.splitlines()[0] if output else ""
        slugs = slugs_from(output)
        blocks = [b for s_ in slugs if (b := block(s_))]
        ans = answer(r.client, question, blocks)
        seeds = re.search(r"Start: \[(.*?)\]", header)
        return finish(q, start, [ans], ans, qms, qfile=qfile, query_text=text, query_header=header,
                      query_ms=qms, heuristic="(heuristic)" in header, notes_sent_slugs=[b["source"] for b in blocks],
                      start_seeds=seeds.group(1) if seeds else "")
    if arm == "D-seed":
        picked, pu = pick(r.client, r.system, r.slugs, question)
        args = ["query", "notes", "--budget", "2000"]
        for s_ in picked:
            args += ["--seed", by_slug[s_]["path"]]
        output, qms = graphify(*args)
        names = slugs_from(output)
        for s_ in picked:
            exp_out, ems = graphify("explain", by_slug[s_]["name"])
            qms += ems
            for line in exp_out.splitlines():
                m = re.search(r"(?:-->|<--|--)\s*(?P<label>[^\[\(]+?)\s*(?:\[|\(|$)", line)
                if m and (s2 := to_slug(m.group("label").strip(), "")):
                    names.append(s2)
        slugs = list(dict.fromkeys([*picked, *names]))
        blocks = [b for s_ in slugs if (b := block(s_))]
        ans = answer(r.client, question, blocks)
        header = output.splitlines()[0] if output else ""
        return finish(q, start, [pu, ans], ans, pu["full_ms"] + qms, qfile=qfile, picked=picked, query_header=header,
                      query_ms=qms, heuristic="(heuristic)" in header, notes_sent_slugs=[b["source"] for b in blocks])
    raise SystemExit(f"unknown arm {arm}")


rows = []
for qfile in qfiles:
    for q in yaml.safe_load(Path(qfile).read_text(encoding="utf-8"))["questions"]:
        row = run_question(q, qfile)
        rows.append(row)
        print(arm, run, row["id"], row["status"], round(row["billed_equiv_in"]), flush=True)
        out.write_text(json.dumps({"arm": arm, "run": run, "rows": rows}, indent=2, ensure_ascii=False), encoding="utf-8")
