"""Arm B v2 on all 25 Apollo questions: noun picked by meaning, one optional extra hop.

1. Pick: one call with the question and a signpost list (slug, name, aliases, one-line
   description; first fact line when a note has no description) returns 1-2 slugs.
2. Gather (no model): the chosen nodes' fact lines and edges, plus all fact lines of
   all their neighbours.
3. Answer from those lines, or reply "NEED: <slug>".
4. On NEED: add that node's fact lines plus its neighbours' lines, answer again. At most
   one extra hop.
Haiku 5.5, thinking off, streamed, questions one at a time. Nothing in the brain is
written. Grading is done by hand afterwards. Writes arm-b-v2.json here.
"""

import json
import re
import sys
import time
from pathlib import Path

import anthropic
import yaml

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))  # run with python -I, which drops the script dir

from speed_test import BRAIN, BRAIN_REPO, load_map  # noqa: E402
from speed_test_v2 import call, fact_lines, ms, stage1a  # noqa: E402

QUESTIONS = BRAIN_REPO / "demo-evals" / "questions.yaml"
PICK_INSTRUCTION = (
    "Pick the 1 or 2 nodes this question is about. Reply with their slugs only, "
    "one per line, or NONE if no node fits."
)
ANSWER_INSTRUCTION = (
    "Answer from these lines only, cite the slug.\n"
    "Keep [derived] tags and say that part is an inference.\n"
    "If a needed fact is missing, reply only \"NEED: <slug>\" naming the neighbour to open "
    "(from the slugs in the lines)."
)
SLUG_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


def signposts(m: dict) -> tuple[str, int]:
    """One line per node; returns the list and how many needed the first-fact fallback."""
    rows, fallback = [], 0
    for n in m["graph"]["nodes"]:
        text = (BRAIN / n["path"]).read_text(encoding="utf-8")
        front = yaml.safe_load(text.split("---", 2)[1]) if text.startswith("---") else {}
        desc = (front or {}).get("description")
        if not desc:
            fallback += 1
            facts = fact_lines(n["path"])
            desc = facts[0][2:] if facts else ""
        aliases = ", ".join(a for a in n.get("aliases", []) if a != n["name"])
        rows.append(f"{n['slug']} | {n['name']}" + (f" | aka {aliases}" if aliases else "") + f" | {desc}")
    return "\n".join(rows), fallback


def gather(m: dict, slugs: list[str], seen: set[str]) -> tuple[list[str], list[str]]:
    """Fact lines of each node and of all its neighbours, skipping nodes already sent."""
    by_slug = {n["slug"]: n for n in m["graph"]["nodes"]}
    edge_lines, lines = [], []
    for slug in slugs:
        edges = stage1a(m, by_slug[slug])
        edge_lines += [f"- {e['line']}" for e in edges]
        for s in [slug, *dict.fromkeys(e["neighbour"] for e in edges)]:
            if s not in seen:
                seen.add(s)
                lines += [f"[{s}] {f}" for f in fact_lines(by_slug[s]["path"])]
    return edge_lines, lines


def answer_prompt(question: str, edge_lines: list[str], lines: list[str]) -> str:
    return (
        f"{ANSWER_INSTRUCTION}\n\nQuestion: {question}\n\nEdges:\n"
        + ("\n".join(edge_lines) or "(none)")
        + "\n\nFact lines:\n"
        + ("\n".join(lines) or "(none)")
    )


def run_one(client: anthropic.Anthropic, m: dict, posts: str, q: dict) -> dict:
    valid = {n["slug"] for n in m["graph"]["nodes"]}
    start = time.perf_counter()
    pick = call(client, f"{PICK_INSTRUCTION}\n\nQuestion: {q['question']}\n\nNodes:\n{posts}", stream=True)
    picked = [s for s in dict.fromkeys(SLUG_RE.findall(pick["text"].lower())) if s in valid][:2]

    seen: set[str] = set()
    edge_lines, lines = gather(m, picked, seen)
    calls = [pick]
    first_ans = call(client, answer_prompt(q["question"], edge_lines, lines), stream=True)
    calls.append(first_ans)
    final, hops, need, need_in_lines = first_ans, 0, None, None
    t_final_start = ms(start) - first_ans["full_ms"]  # when the final answer call began

    match = re.match(r"\s*NEED:\s*([a-z0-9-]+)", first_ans["text"])
    if match:
        need = match.group(1)
        need_in_lines = need in "\n".join(edge_lines + lines)
        if need in valid:
            hops = 1
            more_edges, more_lines = gather(m, [need], seen)
            edge_lines, lines = edge_lines + more_edges, lines + more_lines
            t_final_start = ms(start)
            final = call(client, answer_prompt(q["question"], edge_lines, lines), stream=True)
            calls.append(final)

    return {
        "id": q["id"],
        "question": q["question"],
        "expected": q["expected_answer"],
        "picked": picked or "no noun",
        "pick_text": pick["text"],
        "pick_ms": pick["full_ms"],
        "need": need,
        "need_in_lines": need_in_lines,
        "hops": hops,
        "lines_sent": len(lines),
        "input_tokens": sum(c["input_tokens"] for c in calls),
        "output_tokens": sum(c["output_tokens"] for c in calls),
        "cost_usd": sum(c["cost_usd"] for c in calls),
        "first_word_ms": round(t_final_start + final["first_word_ms"], 3),
        "end_to_end_ms": ms(start),
        "first_answer": first_ans["text"] if hops else None,
        "answer": final["text"],
    }


def main() -> None:
    client = anthropic.Anthropic()
    m = load_map()  # once, not counted
    posts, fallback = signposts(m)  # built once, not counted
    questions = yaml.safe_load(QUESTIONS.read_text(encoding="utf-8"))["questions"]
    rows = []
    for q in questions:
        row = run_one(client, m, posts, q)
        rows.append(row)
        print(row["id"], row["picked"], row["need"], row["input_tokens"], flush=True)
    out = {"signpost_nodes": len(m["graph"]["nodes"]), "description_fallback": fallback, "rows": rows}
    (HERE / "arm-b-v2.json").write_text(json.dumps(out, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
