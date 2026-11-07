"""Arm B v3 on all 25 Apollo questions: v2 plus a forced pick, three reply forms, caching.

Changes from v2:
1. Pick never returns NONE: the best 1-2 slugs even if unsure.
2. The answer is exactly one of: an answer (slugs cited, [derived] flagged),
   "NOT IN BRAIN: <what is missing>", or "NEED: <slug>". Code accepts NEED only for a
   slug among the edges sent whose lines were not sent; any other NEED counts as
   NOT IN BRAIN. After one hop NEED is not offered, and a NEED reply counts as NOT IN BRAIN.
3. The pick instruction and signpost list sit in a cached system block.
Haiku 5.5, thinking off, streamed, questions one at a time. Nothing in the brain is
written. Grading is done by hand afterwards. Writes arm-b-v3.json here.
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

from arm_b_v2 import QUESTIONS, SLUG_RE, gather, signposts  # noqa: E402
from speed_test import load_map  # noqa: E402
from speed_test_v2 import FAST, MODEL, ms  # noqa: E402

PRICE_IN, PRICE_OUT = 0.10, 0.50  # $ per MTok, prompts under 100K tokens
CACHE_WRITE, CACHE_READ = 1.25, 0.10  # x input price, 5-minute TTL

PICK_INSTRUCTION = (
    "Pick the 1 or 2 nodes the question is about. Reply with their slugs only, one per line.\n"
    "Never reply NONE: if unsure, give your best 1 or 2 guesses."
)
ANSWER_FORMS = (
    "Reply in exactly one of these forms:\n"
    "1. An answer from these lines only, citing the slug for each point. Keep [derived] tags "
    "and say that part is an inference.\n"
    "2. NOT IN BRAIN: <what is missing> - when the lines do not contain the answer."
)
NEED_FORM = (
    "\n3. NEED: <slug> - only for a slug that appears in the Edges list and whose fact lines "
    "are not among the Fact lines."
)


def call(client: anthropic.Anthropic, user: str, system: list | None = None) -> dict:
    start = time.perf_counter()
    first = None
    kwargs = {"system": system} if system else {}
    with client.messages.stream(
        model=MODEL, max_tokens=2048, messages=[{"role": "user", "content": user}], **FAST, **kwargs
    ) as s:
        for text in s.text_stream:
            if first is None and text:
                first = time.perf_counter() - start
        final = s.get_final_message()
    u = final.usage
    uncached = u.input_tokens
    written = u.cache_creation_input_tokens or 0
    read = u.cache_read_input_tokens or 0
    billed_in = uncached + CACHE_WRITE * written + CACHE_READ * read
    return {
        "full_ms": ms(start),
        "first_word_ms": round(first * 1000, 3) if first is not None else None,
        "uncached_in": uncached,
        "cache_write": written,
        "cache_read": read,
        "total_in": uncached + written + read,
        "billed_equiv_in": billed_in,
        "output_tokens": u.output_tokens,
        "cost_usd": (billed_in * PRICE_IN + u.output_tokens * PRICE_OUT) / 1e6,
        "text": "".join(b.text for b in final.content if b.type == "text"),
    }


def answer_prompt(question: str, edge_lines: list[str], lines: list[str], allow_need: bool) -> str:
    return (
        f"{ANSWER_FORMS}{NEED_FORM if allow_need else ''}\n\nQuestion: {question}\n\nEdges:\n"
        + ("\n".join(edge_lines) or "(none)")
        + "\n\nFact lines:\n"
        + ("\n".join(lines) or "(none)")
    )


def form_of(text: str) -> str:
    t = text.strip()
    if t.startswith("NEED:"):
        return "need"
    if t.startswith("NOT IN BRAIN"):
        return "not_in_brain"
    return "answer"


def run_one(client: anthropic.Anthropic, m: dict, system: list, q: dict) -> dict:
    valid = {n["slug"] for n in m["graph"]["nodes"]}
    start = time.perf_counter()
    pick = call(client, f"Question: {q['question']}", system=system)
    picked = [s for s in dict.fromkeys(SLUG_RE.findall(pick["text"].lower())) if s in valid][:2]

    seen: set[str] = set()
    edge_lines, lines = gather(m, picked, seen)
    calls = [pick]
    final = call(client, answer_prompt(q["question"], edge_lines, lines, allow_need=True))
    calls.append(final)
    final_start = ms(start) - final["full_ms"]
    hops, need, need_status = 0, None, None

    if form_of(final["text"]) == "need":
        match = re.match(r"\s*NEED:\s*([a-z0-9-]+)", final["text"])
        need = match.group(1) if match else final["text"].strip()
        in_edges = bool(match) and f"({need})" in "\n".join(edge_lines)
        if in_edges and need not in seen:
            need_status = "accepted"
            hops = 1
            more_edges, more_lines = gather(m, [need], seen)
            edge_lines, lines = edge_lines + more_edges, lines + more_lines
            final_start = ms(start)
            final = call(client, answer_prompt(q["question"], edge_lines, lines, allow_need=False))
            calls.append(final)
        else:
            need_status = "rejected: " + ("not in edges sent" if not in_edges else "lines already sent")

    form = form_of(final["text"])
    if form == "need":  # rejected NEED, or NEED after the hop
        form = "not_in_brain (from NEED)"

    return {
        "id": q["id"],
        "question": q["question"],
        "expected": q["expected_answer"],
        "picked": picked,
        "pick_text": pick["text"],
        "pick_ms": pick["full_ms"],
        "need": need,
        "need_status": need_status,
        "hops": hops,
        "form": form,
        "lines_sent": len(lines),
        "calls": [{k: c[k] for k in ("uncached_in", "cache_write", "cache_read", "output_tokens")} for c in calls],
        "total_in": sum(c["total_in"] for c in calls),
        "cached_in": sum(c["cache_read"] for c in calls),
        "billed_equiv_in": round(sum(c["billed_equiv_in"] for c in calls), 1),
        "output_tokens": sum(c["output_tokens"] for c in calls),
        "cost_usd": sum(c["cost_usd"] for c in calls),
        "first_word_ms": round(final_start + final["first_word_ms"], 3),
        "end_to_end_ms": ms(start),
        "answer": final["text"],
    }


def main() -> None:
    client = anthropic.Anthropic()
    m = load_map()  # once, not counted
    posts, fallback = signposts(m)  # built once, not counted
    system = [{"type": "text", "text": f"{PICK_INSTRUCTION}\n\nNodes:\n{posts}", "cache_control": {"type": "ephemeral"}}]
    questions = yaml.safe_load(QUESTIONS.read_text(encoding="utf-8"))["questions"]
    rows = []
    for q in questions:
        row = run_one(client, m, system, q)
        rows.append(row)
        print(row["id"], row["picked"], row["form"], row["need_status"], row["calls"][0], flush=True)
    out = {"description_fallback": fallback, "rows": rows}
    (HERE / "arm-b-v3.json").write_text(json.dumps(out, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
