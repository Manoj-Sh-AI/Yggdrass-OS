"""Speed test v3: two arms for the Mattingly question, plus an Apollo 13 hub worst case.

Arm A (two calls): edge pick as in v2, then ALL fact lines of the picked neighbours
(no name filter) plus all of the noun's own fact lines, then the streamed answer.
Arm B (one call): no pick; the noun's fact lines, its edge list and ALL fact lines
of ALL its neighbours go into one streamed answer call.
Haiku 5.5, thinking off, streamed throughout. Nothing in the brain is written.
Writes result-v3.json here.
"""

import json
import re
import sys
import time
from pathlib import Path

import anthropic

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))  # run with python -I, which drops the script dir

from speed_test import QUESTION, load_map  # noqa: E402
from speed_test_v2 import PICK_INSTRUCTION, call, fact_lines, find_noun, ms, stage1a  # noqa: E402

ANSWER_INSTRUCTION = "Answer from these lines only, cite the slug."
HUB_SLUG = "apollo-13"
HUB_QUESTION = "Why was Apollo 13's command module pilot changed?"


def gather(m: dict, noun: dict, neighbours: list[str]) -> list[dict]:
    """All of the noun's fact lines, then all fact lines of each listed neighbour."""
    by_slug = {n["slug"]: n for n in m["graph"]["nodes"]}
    lines = [{"from": noun["slug"], "line": f} for f in fact_lines(noun["path"])]
    for slug in neighbours:
        lines += [{"from": slug, "line": f} for f in fact_lines(by_slug[slug]["path"])]
    return lines


def render(lines: list[dict]) -> str:
    return "\n".join(f"[{x['from']}] {x['line']}" for x in lines)


def totals(calls: list[dict], start: float) -> dict:
    return {
        "end_to_end_ms": ms(start),
        "input_tokens": sum(c["input_tokens"] for c in calls),
        "output_tokens": sum(c["output_tokens"] for c in calls),
        "cost_usd": sum(c["cost_usd"] for c in calls),
    }


def arm_a(client: anthropic.Anthropic, m: dict, question: str) -> dict:
    start = time.perf_counter()
    noun = find_noun(m, question)
    edges = stage1a(m, noun)
    pick_prompt = f"{PICK_INSTRUCTION}\n\nQuestion: {question}\n\nEdges:\n" + "\n".join(
        f"- {e['line']}" for e in edges
    )
    pick = call(client, pick_prompt, stream=True)
    neighbours = list(dict.fromkeys(e["neighbour"] for e in edges))
    tokens = set(re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)*", pick["text"].lower()))
    picked = [n for n in neighbours if n in tokens]
    lines = gather(m, noun, picked)
    answer = call(client, f"{ANSWER_INSTRUCTION}\n\nQuestion: {question}\n\n{render(lines)}", stream=True)
    return {
        "noun": noun["slug"],
        "picked": picked,
        "line_count": len(lines),
        "lines": lines,
        "pick": pick,
        "answer": answer,
        # first word of the final answer, measured from the start of the run
        "first_word_from_start_ms": round(pick["full_ms"] + answer["first_word_ms"], 3),
        "total": totals([pick, answer], start),
    }


def arm_b(client: anthropic.Anthropic, m: dict, question: str, noun: dict | None = None) -> dict:
    start = time.perf_counter()
    noun = noun or find_noun(m, question)
    edges = stage1a(m, noun)
    neighbours = list(dict.fromkeys(e["neighbour"] for e in edges))
    lines = gather(m, noun, neighbours)
    prompt = (
        f"{ANSWER_INSTRUCTION}\n\nQuestion: {question}\n\nEdges of {noun['slug']}:\n"
        + "\n".join(f"- {e['line']}" for e in edges)
        + f"\n\nFact lines:\n{render(lines)}"
    )
    gather_ms = ms(start)
    answer = call(client, prompt, stream=True)
    return {
        "noun": noun["slug"],
        "neighbour_count": len(neighbours),
        "edge_count": len(edges),
        "line_count": len(lines),
        "lines": lines,
        "gather_ms": gather_ms,
        "answer": answer,
        "first_word_from_start_ms": round(gather_ms + answer["first_word_ms"], 3),
        "total": totals([answer], start),
    }


def main() -> None:
    client = anthropic.Anthropic()
    m = load_map()  # once, not counted
    by_slug = {n["slug"]: n for n in m["graph"]["nodes"]}
    result = {
        "question": QUESTION,
        "arm_a": arm_a(client, m, QUESTION),
        "arm_b": arm_b(client, m, QUESTION),
        "hub": {"question": HUB_QUESTION, **arm_b(client, m, HUB_QUESTION, by_slug[HUB_SLUG])},
    }
    (HERE / "result-v3.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
