"""Arm B v6: v5 baseline vs cold cache vs citations, on 35 questions (25 old + 10 held out).

Variants (pick: `python arm_b_v6.py A|B|C [run]`):
  A  v5 exactly: structured pick and answer, signpost block cached.
  B  v5 with caching off (no cache_control on the signpost block).
  C  v5's pick (cached), then the answer step without structured output: each gathered
     node is a search_result block (source = slug, title = node name, content = one text
     block per line; a picked node's block also holds its edge lines), citations on.
     A reply starting with "NOT IN BRAIN" is a decline. No NEED step.
Haiku 5.5, thinking off, streamed, questions one at a time. Nothing in the brain is
written. Grading is by hand. Writes arm-b-v6-<variant>-<run>.json here.
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

import arm_b_v4  # noqa: E402
import arm_b_v5  # noqa: E402,F401  (installs v5's answer schema into arm_b_v4)
from arm_b_v2 import QUESTIONS, fact_lines, signposts  # noqa: E402
from arm_b_v3 import CACHE_READ, CACHE_WRITE, PRICE_IN, PRICE_OUT  # noqa: E402
from speed_test import BRAIN_REPO, load_map  # noqa: E402
from speed_test_v2 import MODEL, ms, stage1a  # noqa: E402

HELD_OUT = BRAIN_REPO / "demo-evals" / "held-out-v6.yaml"
C_INSTRUCTION = (
    "Answer the question from these search results only, citing them. "
    'If the answer is not present, start your reply with exactly "NOT IN BRAIN".'
)
SENTENCE_RE = re.compile(r"[^.!?\n]+(?:[.!?]+|$)")


def load_questions() -> list[dict]:
    old = yaml.safe_load(QUESTIONS.read_text(encoding="utf-8"))["questions"]
    new = yaml.safe_load(HELD_OUT.read_text(encoding="utf-8"))["questions"]
    return [{**q, "set": "old"} for q in old] + [{**q, "set": "new"} for q in new]


def search_results(m: dict, picked: list[str]) -> list[dict]:
    """One search_result per gathered node, in v5's gather order."""
    by_slug = {n["slug"]: n for n in m["graph"]["nodes"]}
    blocks, seen = [], set()
    for slug in picked:
        edges = stage1a(m, by_slug[slug])
        for s in [slug, *dict.fromkeys(e["neighbour"] for e in edges)]:
            if s in seen:
                continue
            seen.add(s)
            lines = list(fact_lines(by_slug[s]["path"]))
            if s == slug:
                lines += [f"Link: {e['line']}" for e in edges]
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
    return blocks


def citation_stats(content: list) -> dict:
    """Share of answer sentences that overlap a cited text block; uncited sentences listed."""
    text, spans, pos = "", [], 0
    for b in content:
        if b.type != "text":
            continue
        if b.citations:
            spans.append((pos, pos + len(b.text)))
        text += b.text
        pos += len(b.text)
    sentences = [(mt.start(), mt.end(), mt.group().strip()) for mt in SENTENCE_RE.finditer(text)]
    sentences = [s for s in sentences if len(s[2]) > 3]
    cited = [s for s in sentences if any(a < s[1] and s[0] < b for a, b in spans)]
    return {
        "sentences": len(sentences),
        "cited": len(cited),
        "uncited": [s[2] for s in sentences if s not in cited],
        "sources": sorted({c.source for b in content if b.type == "text" and b.citations for c in b.citations}),
    }


def answer_c(client: anthropic.Anthropic, question: str, blocks: list[dict]) -> dict:
    start = time.perf_counter()
    first = None
    content = [*blocks, {"type": "text", "text": f"{C_INSTRUCTION}\n\nQuestion: {question}"}]
    with client.messages.stream(
        model=MODEL,
        max_tokens=2048,
        thinking={"type": "disabled"},
        output_config={"effort": "low"},
        messages=[{"role": "user", "content": content}],
    ) as s:
        for text in s.text_stream:
            if first is None and text:
                first = time.perf_counter() - start
        final = s.get_final_message()
    u = final.usage
    written, read = u.cache_creation_input_tokens or 0, u.cache_read_input_tokens or 0
    billed_in = u.input_tokens + CACHE_WRITE * written + CACHE_READ * read
    text = "".join(b.text for b in final.content if b.type == "text")
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
        "text": text,
        "citations": citation_stats(final.content),
    }


def run_c(client: anthropic.Anthropic, m: dict, system: list, slugs: list[str], q: dict) -> dict:
    start = time.perf_counter()
    pick = arm_b_v4.call(client, f"Question: {q['question']}", arm_b_v4.pick_schema(slugs), system=system)
    picked = [s for s in dict.fromkeys(pick["data"]["notes"]) if s in slugs][:2]
    blocks = search_results(m, picked)
    ans = answer_c(client, q["question"], blocks)
    calls = [pick, ans]
    return {
        "id": q["id"],
        "question": q["question"],
        "expected": q["expected_answer"],
        "picked": picked,
        "pick_ms": pick["full_ms"],
        "need": None,
        "need_status": None,
        "hops": 0,
        "status": "not_in_brain" if ans["text"].lstrip().startswith("NOT IN BRAIN") else "answer",
        "lines_sent": sum(len(b["content"]) for b in blocks),
        "calls": [{k: c[k] for k in ("uncached_in", "cache_write", "cache_read", "output_tokens", "stop_reason")} for c in calls],
        "total_in": sum(c["total_in"] for c in calls),
        "cached_in": sum(c["cache_read"] for c in calls),
        "billed_equiv_in": round(sum(c["billed_equiv_in"] for c in calls), 1),
        "output_tokens": sum(c["output_tokens"] for c in calls),
        "cost_usd": sum(c["cost_usd"] for c in calls),
        "first_token_ms": round(pick["full_ms"] + ans["first_token_ms"], 3),
        "end_to_end_ms": ms(start),
        "answer": ans["text"],
        "citations": ans["citations"],
    }


def main() -> None:
    variant, run = sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 1
    client = anthropic.Anthropic()
    m = load_map()  # once, not counted
    slugs = sorted(n["slug"] for n in m["graph"]["nodes"])
    posts, _ = signposts(m)  # built once, not counted
    block = {"type": "text", "text": f"{arm_b_v4.PICK_INSTRUCTION}\n\nNodes:\n{posts}"}
    if variant != "B":
        block["cache_control"] = {"type": "ephemeral"}
    system = [block]
    rows = []
    for q in load_questions():
        if variant == "C":
            row = run_c(client, m, system, slugs, q)
        else:
            row = arm_b_v4.run_one(client, m, system, slugs, q)
        row["set"] = q["set"]
        rows.append(row)
        print(variant, run, row["id"], row["picked"], row["status"], row["need"], row["need_status"], flush=True)
        out = HERE / f"arm-b-v6-{variant}-{run}.json"
        out.write_text(json.dumps({"variant": variant, "run": run, "rows": rows}, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
