"""Hybrid arm: Graphify's query picks the notes, our fact lines answer.

For each question: `graphify query "<question>" --budget 2000` on the links-free build
(query logging off). Each returned NODE line is mapped to a brain slug by label (D02
normalization against slug, name and aliases, unambiguous only), falling back to its
src= path. Those notes' fact lines go to one Haiku 5.5 call as search_result blocks with
citations on, exactly as in variant C (retrieve.py). No Graphify text reaches the model.
A reply starting with "NOT IN BRAIN" is a decline. Questions one at a time.

Usage (from the repo root):
    uv run --project app --with anthropic python \
        evals/experiments/graphify-vs-baseline/answer_hybrid.py \
        <demo-brain> <graph.json> <retrieve.py dir> <out.json> <questions.yaml> [...]
"""

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import anthropic
import yaml

from yggdras.data.graph.structural import build_map, normalize

brain, graph, retrieve_dir, out = (Path(a) for a in sys.argv[1:5])
sys.path.insert(0, str(retrieve_dir))
from retrieve import answer, display_text, fact_lines, note_text, status_of  # noqa: E402

BUDGET = 2000
NODE_RE = re.compile(r"^NODE (?P<label>.+?) \[src=(?P<src>[^ ]+)")


def ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 3)


def query(question: str) -> tuple[str, float]:
    env = {**os.environ, "GRAPHIFY_QUERY_LOG_DISABLE": "1"}
    start = time.perf_counter()
    p = subprocess.run(
        ["graphify", "query", question, "--budget", str(BUDGET), "--graph", str(graph)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
    )
    return p.stdout, ms(start)


def main() -> None:
    m = build_map(brain)
    by_slug = {n["slug"]: n for n in m["nodes"]}
    by_path = {n["path"]: n["slug"] for n in m["nodes"]}
    lookup: dict[str, set[str]] = {}
    for n in m["nodes"]:
        for name in [n["slug"], n["name"], *n["aliases"]]:
            lookup.setdefault(normalize(name), set()).add(n["slug"])

    def to_slug(label: str, src: str) -> str | None:
        hits = lookup.get(normalize(label), set())
        return next(iter(hits)) if len(hits) == 1 else by_path.get(src)

    client = anthropic.Anthropic()
    rows = []
    for qfile in sys.argv[5:]:
        for q in yaml.safe_load(Path(qfile).read_text(encoding="utf-8"))["questions"]:
            start = time.perf_counter()
            returned, query_ms = query(q["question"])
            nodes = [mt.groupdict() for line in returned.splitlines() if (mt := NODE_RE.match(line))]
            slugs = list(dict.fromkeys(s for n in nodes if (s := to_slug(n["label"], n["src"]))))
            blocks = []
            for s in slugs:
                lines = fact_lines(note_text(brain, by_slug[s]))
                if lines:
                    blocks.append(
                        {
                            "type": "search_result",
                            "source": s,
                            "title": by_slug[s]["name"],
                            "content": [{"type": "text", "text": line} for line in lines],
                            "citations": {"enabled": True},
                        }
                    )
            ans = answer(client, q["question"], blocks)
            rows.append(
                {
                    "id": q["id"],
                    "set": "old" if Path(qfile).stem == "questions" else "new",
                    "question": q["question"],
                    "expected": q["expected_answer"],
                    "query_ms": query_ms,
                    "query_header": returned.splitlines()[0] if returned else "",
                    "nodes_returned": len(nodes),
                    "notes_sent": [b["source"] for b in blocks],
                    "lines_sent": sum(len(b["content"]) for b in blocks),
                    "status": status_of(ans["raw_answer"]),
                    "answer": display_text(ans["raw_answer"]),
                    "raw_answer": ans["raw_answer"],
                    "citations": ans["citations"],
                    "total_in": ans["total_in"],
                    "billed_equiv_in": ans["billed_equiv_in"],
                    "output_tokens": ans["output_tokens"],
                    "cost_usd": ans["cost_usd"],
                    "first_token_ms": round(query_ms + ans["first_token_ms"], 3),
                    "end_to_end_ms": ms(start),
                }
            )
            print(q["id"], rows[-1]["status"], len(blocks), ans["total_in"], flush=True)
            out.write_text(json.dumps({"variant": "hybrid", "rows": rows}, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
