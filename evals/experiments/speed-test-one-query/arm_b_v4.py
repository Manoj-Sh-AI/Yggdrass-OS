"""Arm B v4: v3 with structured (JSON schema) replies, all 25 questions, 3 runs.

Pick: {"notes": [slugs]}, items restricted to the map's slugs by enum. The schema
can't bound array length, so code takes the first 2 and retries once on an empty list.
Answer: {"status": "answer" | "not_in_brain" | "need", "text": ..., "need": slug | null}.
NEED rules as v3: accepted only for a slug among the edges sent whose lines were not
sent; otherwise treated as not_in_brain. After one hop "need" is not in the enum.
Haiku 5.5, thinking off, streamed, questions one at a time, signpost block cached.
Nothing in the brain is written. Grading is by hand. Writes arm-b-v4.json here.
"""

import json
import sys
import time
from pathlib import Path

import anthropic
import yaml

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))  # run with python -I, which drops the script dir

from arm_b_v2 import QUESTIONS, gather, signposts  # noqa: E402
from arm_b_v3 import CACHE_READ, CACHE_WRITE, PRICE_IN, PRICE_OUT  # noqa: E402
from speed_test import load_map  # noqa: E402
from speed_test_v2 import MODEL, ms  # noqa: E402

RUNS = 3
PICK_INSTRUCTION = (
    "Pick the 1 or 2 nodes the question is about, as slugs from the list. "
    "Always give at least one: if unsure, give your best guess."
)
ANSWER_FORMS = (
    "Reply with a status and text:\n"
    "- answer: the answer from these lines only, citing the slug for each point. Keep [derived] "
    "tags and say that part is an inference.\n"
    "- not_in_brain: say what is missing - when the lines do not contain the answer."
)
NEED_FORM = (
    "\n- need: put the slug in \"need\" - only for a slug that appears in the Edges list and "
    "whose fact lines are not among the Fact lines."
)


def pick_schema(slugs: list[str]) -> dict:
    return {
        "type": "object",
        "properties": {"notes": {"type": "array", "items": {"type": "string", "enum": slugs}}},
        "required": ["notes"],
        "additionalProperties": False,
    }


def answer_schema(slugs: list[str], allow_need: bool) -> dict:
    statuses = ["answer", "not_in_brain", *(["need"] if allow_need else [])]
    need = {"anyOf": [{"type": "string", "enum": slugs}, {"type": "null"}]} if allow_need else {"type": "null"}
    return {
        "type": "object",
        "properties": {"status": {"type": "string", "enum": statuses}, "text": {"type": "string"}, "need": need},
        "required": ["status", "text", "need"],
        "additionalProperties": False,
    }


def call(client: anthropic.Anthropic, user: str, schema: dict, system: list | None = None) -> dict:
    start = time.perf_counter()
    first = None
    kwargs = {"system": system} if system else {}
    with client.messages.stream(
        model=MODEL,
        max_tokens=2048,
        thinking={"type": "disabled"},
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": schema}},
        messages=[{"role": "user", "content": user}],
        **kwargs,
    ) as s:
        for text in s.text_stream:
            if first is None and text:
                first = time.perf_counter() - start
        final = s.get_final_message()
    u = final.usage
    written, read = u.cache_creation_input_tokens or 0, u.cache_read_input_tokens or 0
    billed_in = u.input_tokens + CACHE_WRITE * written + CACHE_READ * read
    return {
        "full_ms": ms(start),
        "first_token_ms": round(first * 1000, 3) if first is not None else None,
        "uncached_in": u.input_tokens,
        "cache_write": written,
        "cache_read": read,
        "total_in": u.input_tokens + written + read,
        "billed_equiv_in": billed_in,
        "output_tokens": u.output_tokens,
        "cost_usd": (billed_in * PRICE_IN + u.output_tokens * PRICE_OUT) / 1e6,
        "stop_reason": final.stop_reason,
        "data": json.loads("".join(b.text for b in final.content if b.type == "text")),
    }


def answer_prompt(question: str, edge_lines: list[str], lines: list[str], allow_need: bool) -> str:
    return (
        f"{ANSWER_FORMS}{NEED_FORM if allow_need else ''}\n\nQuestion: {question}\n\nEdges:\n"
        + ("\n".join(edge_lines) or "(none)")
        + "\n\nFact lines:\n"
        + ("\n".join(lines) or "(none)")
    )


def run_one(client: anthropic.Anthropic, m: dict, system: list, slugs: list[str], q: dict) -> dict:
    start = time.perf_counter()
    calls, pick_retries = [], 0
    while True:
        pick = call(client, f"Question: {q['question']}", pick_schema(slugs), system=system)
        calls.append(pick)
        picked = [s for s in dict.fromkeys(pick["data"]["notes"]) if s in slugs][:2]
        if picked or pick_retries == 1:
            break
        pick_retries += 1
    pick_ms = ms(start)

    seen: set[str] = set()
    edge_lines, lines = gather(m, picked, seen)
    final = call(client, answer_prompt(q["question"], edge_lines, lines, True), answer_schema(slugs, True))
    calls.append(final)
    final_start = ms(start) - final["full_ms"]
    hops, need, need_status = 0, None, None

    if final["data"]["status"] == "need":
        need = final["data"]["need"]
        in_edges = need is not None and f"({need})" in "\n".join(edge_lines)
        if in_edges and need not in seen:
            need_status, hops = "accepted", 1
            more_edges, more_lines = gather(m, [need], seen)
            edge_lines, lines = edge_lines + more_edges, lines + more_lines
            final_start = ms(start)
            final = call(client, answer_prompt(q["question"], edge_lines, lines, False), answer_schema(slugs, False))
            calls.append(final)
        else:
            need_status = "rejected: " + ("not in edges sent" if not in_edges else "lines already sent")

    status = final["data"]["status"]
    if status == "need":
        status = "not_in_brain (from rejected need)"
    return {
        "id": q["id"],
        "question": q["question"],
        "expected": q["expected_answer"],
        "picked": picked,
        "pick_retries": pick_retries,
        "pick_ms": pick_ms,
        "need": need,
        "need_status": need_status,
        "hops": hops,
        "status": status,
        "lines_sent": len(lines),
        "calls": [{k: c[k] for k in ("uncached_in", "cache_write", "cache_read", "output_tokens", "stop_reason")} for c in calls],
        "total_in": sum(c["total_in"] for c in calls),
        "cached_in": sum(c["cache_read"] for c in calls),
        "billed_equiv_in": round(sum(c["billed_equiv_in"] for c in calls), 1),
        "output_tokens": sum(c["output_tokens"] for c in calls),
        "cost_usd": sum(c["cost_usd"] for c in calls),
        "first_token_ms": round(final_start + final["first_token_ms"], 3),
        "end_to_end_ms": ms(start),
        "answer": final["data"]["text"],
    }


def main() -> None:
    client = anthropic.Anthropic()
    m = load_map()  # once, not counted
    slugs = sorted(n["slug"] for n in m["graph"]["nodes"])
    posts, fallback = signposts(m)  # built once, not counted
    system = [{"type": "text", "text": f"{PICK_INSTRUCTION}\n\nNodes:\n{posts}", "cache_control": {"type": "ephemeral"}}]
    questions = yaml.safe_load(QUESTIONS.read_text(encoding="utf-8"))["questions"]
    runs = []
    for run in range(1, RUNS + 1):
        rows = []
        for q in questions:
            row = run_one(client, m, system, slugs, q)
            rows.append(row)
            print(run, row["id"], row["picked"], row["status"], row["need_status"], flush=True)
        runs.append(rows)
        (HERE / "arm-b-v4.json").write_text(json.dumps({"runs": runs}, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
