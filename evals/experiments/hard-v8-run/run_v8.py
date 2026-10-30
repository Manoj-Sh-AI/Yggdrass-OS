"""Hard set v8: whole brain (cached) vs the pipeline (variant C), with cold/warm per question.

Usage (from the repo root):
    uv run --project app --with anthropic python evals/experiments/hard-v8-run/run_v8.py \
        <whole|pipeline> <run> <demo-brain> <retrieve.py dir> <out.json> <questions.yaml> \
        [--spent <so far>]
Stops before a question if total spend (so far + this run) passes $3.
"""

import json
import sys
import time
from pathlib import Path

import yaml

arm, run = sys.argv[1], int(sys.argv[2])
brain, retrieve_dir, out, qfile = (
    Path(sys.argv[3]),
    Path(sys.argv[4]),
    Path(sys.argv[5]),
    Path(sys.argv[6]),
)
spent = float(sys.argv[sys.argv.index("--spent") + 1]) if "--spent" in sys.argv else 0.0
CAP = 3.0
sys.path.insert(0, str(retrieve_dir))

from retrieve import (  # noqa: E402
    Retriever,
    answer,
    display_text,
    edges_of,
    fact_lines,
    note_text,
    pick,
    search_results,
    status_of,
)

r = Retriever(brain)


def whole_blocks() -> list[dict]:
    blocks = []
    for n in r.graph["nodes"]:
        lines = fact_lines(note_text(brain, n)) + [
            f"Link: {e['line']}" for e in edges_of(r.graph, n)
        ]
        if lines:
            blocks.append(
                {
                    "type": "search_result",
                    "source": n["slug"],
                    "title": n["name"],
                    "content": [{"type": "text", "text": line} for line in lines],
                    "citations": {"enabled": True},
                }
            )
    blocks[-1]["cache_control"] = {"type": "ephemeral"}
    return blocks


WHOLE = whole_blocks() if arm == "whole" else None
rows = []
for q in yaml.safe_load(qfile.read_text(encoding="utf-8"))["questions"]:
    if spent > CAP:
        print(f"cap ${CAP} passed (${spent:.3f}), stopping", flush=True)
        break
    start = time.perf_counter()
    if arm == "whole":
        calls = [answer(r.client, q["question"], WHOLE)]
        cached_call, ans, picked, first_from = calls[0], calls[0], None, 0.0
    else:
        picked, pu = pick(r.client, r.system, r.slugs, q["question"])
        ans = answer(r.client, q["question"], search_results(brain, r.graph, picked))
        calls, cached_call, first_from = [pu, ans], pu, pu["full_ms"]
    cost = sum(c["cost_usd"] for c in calls)
    spent += cost
    rows.append(
        {
            "id": q["id"],
            "kind": q["kind"],
            "question": q["question"],
            "picked": picked,
            "status": status_of(ans["raw_answer"]),
            "answer": display_text(ans["raw_answer"]),
            "raw_answer": ans["raw_answer"],
            "cited_sources": sorted({c["source"] for c in ans["citations"]}),
            "cache": "cold" if cached_call["cache_write"] > 0 else "warm",
            "cache_write": cached_call["cache_write"],
            "cache_read": cached_call["cache_read"],
            "total_in": sum(c["total_in"] for c in calls),
            "billed_equiv_in": round(sum(c["billed_equiv_in"] for c in calls), 1),
            "output_tokens": sum(c["output_tokens"] for c in calls),
            "cost_usd": cost,
            "first_token_ms": round(first_from + ans["first_token_ms"], 3),
            "end_to_end_ms": round((time.perf_counter() - start) * 1000, 3),
        }
    )
    print(
        arm,
        run,
        q["id"],
        rows[-1]["status"],
        rows[-1]["cache"],
        round(rows[-1]["billed_equiv_in"]),
        flush=True,
    )
    out.write_text(
        json.dumps(
            {"arm": arm, "run": run, "file": qfile.name, "spent_after": spent, "rows": rows},
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
