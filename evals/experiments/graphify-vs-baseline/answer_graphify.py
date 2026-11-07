"""Answer the 35 Apollo questions from Graphify's own query route, one Haiku call each.

For each question: `graphify query "<question>" --budget 2000 --graph <graph.json>`
(query logging off), then one fresh Haiku 5.5 call (thinking off, streamed) that sees
only the instruction, the question and what the query returned. A reply starting with
"NOT IN BRAIN" is a decline. One run, questions one at a time. Writes answers.json.

Usage: python answer_graphify.py <graph.json> <out.json> <questions.yaml> [...]
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import anthropic
import yaml

MODEL = "claude-haiku-5-5"
PRICE_IN, PRICE_OUT = 0.10, 0.50  # $ per MTok
BUDGET = 2000
INSTRUCTION = (
    "Answer the question from this knowledge-graph query output only. "
    'If the answer is not present, start your reply with exactly "NOT IN BRAIN".'
)


def ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 3)


def query(graph: Path, question: str) -> tuple[str, float]:
    env = {**os.environ, "GRAPHIFY_QUERY_LOG_DISABLE": "1"}
    start = time.perf_counter()
    p = subprocess.run(
        ["graphify", "query", question, "--budget", str(BUDGET), "--graph", str(graph)],
        capture_output=True, text=True, encoding="utf-8", env=env,
    )
    return (p.stdout + (f"\n[stderr] {p.stderr.strip()}" if p.stderr.strip() else "")).strip(), ms(start)


def main() -> None:
    graph, out = Path(sys.argv[1]), Path(sys.argv[2])
    client = anthropic.Anthropic()
    rows = []
    for qfile in sys.argv[3:]:
        for q in yaml.safe_load(Path(qfile).read_text(encoding="utf-8"))["questions"]:
            start = time.perf_counter()
            returned, query_ms = query(graph, q["question"])
            t = time.perf_counter()
            first = None
            with client.messages.stream(
                model=MODEL,
                max_tokens=2048,
                thinking={"type": "disabled"},
                output_config={"effort": "low"},
                messages=[{"role": "user", "content": f"{INSTRUCTION}\n\nQuestion: {q['question']}\n\n{returned}"}],
            ) as s:
                for text in s.text_stream:
                    if first is None and text:
                        first = time.perf_counter() - t
                final = s.get_final_message()
            u = final.usage
            text = "".join(b.text for b in final.content if b.type == "text")
            rows.append({
                "id": q["id"],
                "set": "old" if Path(qfile).stem == "questions" else "new",
                "question": q["question"],
                "expected": q["expected_answer"],
                "query_ms": query_ms,
                "query_output": returned,
                "query_chars": len(returned),
                "status": "not_in_brain" if text.lstrip().startswith("NOT IN BRAIN") else "answer",
                "answer": text,
                "total_in": u.input_tokens,
                "billed_equiv_in": u.input_tokens,
                "output_tokens": u.output_tokens,
                "cost_usd": (u.input_tokens * PRICE_IN + u.output_tokens * PRICE_OUT) / 1e6,
                "first_token_ms": round(query_ms + first * 1000, 3),
                "end_to_end_ms": ms(start),
            })
            print(q["id"], rows[-1]["status"], u.input_tokens, round(query_ms), flush=True)
            out.write_text(json.dumps({"variant": "graphify", "rows": rows}, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
