"""Variant A, kept for reference only: v5's structured answer instead of citations.

Same pick and gather as retrieve.py. The answer step sends the gathered lines as plain
text and forces a JSON reply {"text": ..., "status": "answer" | "not_in_brain"}, text
first. This is v5 with the NEED form removed; NEED never fired in any run, because the
gather already sends the lines of every neighbour named in the edges it sends.
--no-cache drops the cache marker on the pick block (variant B, the cold-cache case).

Usage (from the repo root):
    uv run --project app --with anthropic python \
        evals/experiments/speed-test-one-query/variant_a.py \
        <demo-brain> <out.json> <questions.yaml> [...] [--no-cache]
"""

import json
import sys
import time
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent))

from retrieve import (  # noqa: E402
    MODEL,
    Retriever,
    edges_of,
    fact_lines,
    ms,
    note_text,
    pick,
    usage_row,
)

ANSWER_FORMS = (
    "Reply with a status and text:\n"
    "- answer: the answer from these lines only, citing the slug for each point. Keep [derived] "
    "tags and say that part is an inference.\n"
    "- not_in_brain: say what is missing - when the lines do not contain the answer."
)
SCHEMA = {
    "type": "object",
    "properties": {
        "text": {"type": "string"},
        "status": {"type": "string", "enum": ["answer", "not_in_brain"]},
    },
    "required": ["text", "status"],
    "additionalProperties": False,
}


def gather_lines(brain: Path, graph: dict, picked: list[str]) -> tuple[list[str], list[str]]:
    by_slug = {n["slug"]: n for n in graph["nodes"]}
    edge_lines, lines, seen = [], [], set()
    for slug in picked:
        edges = edges_of(graph, by_slug[slug])
        edge_lines += [f"- {e['line']}" for e in edges]
        for s in [slug, *dict.fromkeys(e["neighbour"] for e in edges)]:
            if s not in seen:
                seen.add(s)
                lines += [f"[{s}] {f}" for f in fact_lines(note_text(brain, by_slug[s]))]
    return edge_lines, lines


def ask_a(r: Retriever, question: str) -> dict:
    start = time.perf_counter()
    picked, pick_usage = pick(r.client, r.system, r.slugs, question)
    edge_lines, lines = gather_lines(r.brain, r.graph, picked)
    prompt = (
        f"{ANSWER_FORMS}\n\nQuestion: {question}\n\nEdges:\n"
        + ("\n".join(edge_lines) or "(none)")
        + "\n\nFact lines:\n"
        + ("\n".join(lines) or "(none)")
    )
    t = time.perf_counter()
    first = None
    with r.client.messages.stream(
        model=MODEL,
        max_tokens=2048,
        thinking={"type": "disabled"},
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
        messages=[{"role": "user", "content": prompt}],
    ) as s:
        for text in s.text_stream:
            if first is None and text:
                first = time.perf_counter() - t
        final = s.get_final_message()
    data = json.loads("".join(b.text for b in final.content if b.type == "text"))
    ans = usage_row(final.usage, t)
    calls = [pick_usage, ans]
    return {
        "question": question,
        "picked": picked,
        "status": data["status"],
        "answer": data["text"],
        "lines_sent": len(lines),
        "first_token_ms": round(pick_usage["full_ms"] + first * 1000, 3),
        "end_to_end_ms": ms(start),
        "total_in": sum(c["total_in"] for c in calls),
        "billed_equiv_in": round(sum(c["billed_equiv_in"] for c in calls), 1),
        "output_tokens": sum(c["output_tokens"] for c in calls),
        "cost_usd": sum(c["cost_usd"] for c in calls),
    }


def main(argv: list[str]) -> int:
    no_cache = "--no-cache" in argv
    args = [a for a in argv if a != "--no-cache"]
    if len(args) < 3:
        print(__doc__, file=sys.stderr)
        return 2
    r, out = Retriever(Path(args[0])), Path(args[1])
    if no_cache:
        r.system = [{k: v for k, v in r.system[0].items() if k != "cache_control"}]
    rows = []
    for qfile in args[2:]:
        for q in yaml.safe_load(Path(qfile).read_text(encoding="utf-8"))["questions"]:
            row = {"id": q["id"], "set": Path(qfile).stem, **ask_a(r, q["question"])}
            rows.append(row)
            print(row["id"], row["picked"], row["status"], flush=True)
            out.write_text(
                json.dumps({"variant": "B" if no_cache else "A", "rows": rows}, indent=2),
                encoding="utf-8",
            )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
