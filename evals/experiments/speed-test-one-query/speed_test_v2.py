"""Speed test v2 for one query: lookup, model edge pick, gather, streamed answer.

1a (no model) finds the noun and lists its edges. 1b (Haiku, thinking off) picks
the edges that fit the question, as neighbour names. 1c (no model) gathers the
noun's fact lines plus every fact line of a picked neighbour that names the noun.
2 (Haiku, thinking off, streamed) answers from those lines. Nothing in the brain
is written. No line limits. Writes result-v2.json here.
"""

import json
import re
import sys
import time
from pathlib import Path

import anthropic

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))  # run with python -I, which drops the script dir

from speed_test import BRAIN, QUESTION, load_map, norm  # noqa: E402
MODEL = "claude-haiku-5-5"
PRICE_IN, PRICE_OUT = 0.10, 0.50  # $ per MTok, prompts under 100K tokens
FAST = {"thinking": {"type": "disabled"}, "output_config": {"effort": "low"}}
PICK_INSTRUCTION = "Return the neighbours whose edge fits the question, names only, one per line."
ANSWER_INSTRUCTION = "Answer the question from these lines only; cite the node slug for each point."


def ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 3)


def find_noun(m: dict, question: str) -> dict | None:
    q = f" {norm(question)} "
    for name, node in m["names"]:  # longest name first
        if f" {name} " in q:
            return node
    return None


def stage1a(m: dict, noun: dict) -> list[dict]:
    edges = []
    for e in m["graph"]["edges"]:
        if noun["id"] == e["from"]:
            other, text = m["by_id"][e["to"]], f"{noun['name']} {e['reason']} {{n}}"
        elif noun["id"] == e["to"]:
            other, text = m["by_id"][e["from"]], f"{{n}} {e['reason']} {noun['name']}"
        else:
            continue
        edges.append({"neighbour": other["slug"], "line": text.format(n=f"{other['name']} ({other['slug']})")})
    return edges


def fact_lines(path: str) -> list[str]:
    text = (BRAIN / path).read_text(encoding="utf-8")
    if "## Facts" not in text:
        return []
    section = text.split("## Facts", 1)[1].split("\n## ", 1)[0]
    return [line for line in section.splitlines() if line.startswith("- [")]


def stage1c(m: dict, noun: dict, picked: list[str]) -> list[dict]:
    names = [norm(n) for n in {noun["name"], noun["slug"], *noun.get("aliases", [])}]
    lines = [{"from": noun["slug"], "line": f} for f in fact_lines(noun["path"])]
    by_slug = {n["slug"]: n for n in m["graph"]["nodes"]}
    for slug in picked:
        for f in fact_lines(by_slug[slug]["path"]):
            if any(f" {n} " in f" {norm(f)} " for n in names):
                lines.append({"from": slug, "line": f})
    return lines


def call(client: anthropic.Anthropic, prompt: str, stream: bool) -> dict:
    start = time.perf_counter()
    first = None
    with client.messages.stream(
        model=MODEL, max_tokens=2048, messages=[{"role": "user", "content": prompt}], **FAST
    ) as s:
        for text in s.text_stream:
            if first is None and text:
                first = time.perf_counter() - start
        final = s.get_final_message()
    u = final.usage
    out = {
        "full_ms": ms(start),
        "input_tokens": u.input_tokens,
        "output_tokens": u.output_tokens,
        "cost_usd": (u.input_tokens * PRICE_IN + u.output_tokens * PRICE_OUT) / 1e6,
        "text": "".join(b.text for b in final.content if b.type == "text"),
        "stop_reason": final.stop_reason,
    }
    if stream:
        out["first_word_ms"] = round(first * 1000, 3) if first is not None else None
    return out


def main() -> None:
    client = anthropic.Anthropic()
    m = load_map()  # once, not counted
    result: dict = {"question": QUESTION, "model": MODEL}
    run_start = time.perf_counter()

    t = time.perf_counter()
    noun = find_noun(m, QUESTION)
    edges = stage1a(m, noun) if noun else []
    result["1a"] = {"ms": ms(t), "noun": noun and noun["slug"], "edges": [e["line"] for e in edges]}
    if not noun:
        result["stopped"] = "Stage 1a found no node in the question"
        (HERE / "result-v2.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result, indent=2))
        return

    pick_prompt = f"{PICK_INSTRUCTION}\n\nQuestion: {QUESTION}\n\nEdges:\n" + "\n".join(
        f"- {e['line']}" for e in edges
    )
    r1b = call(client, pick_prompt, stream=False)
    neighbours = list(dict.fromkeys(e["neighbour"] for e in edges))
    tokens = set(re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)*", r1b["text"].lower()))
    picked = [n for n in neighbours if n in tokens]
    result["1b"] = {**r1b, "prompt": pick_prompt, "picked": picked}

    t = time.perf_counter()
    lines = stage1c(m, noun, picked)
    result["1c"] = {"ms": ms(t), "line_count": len(lines), "lines": lines}

    answer_prompt = f"{ANSWER_INSTRUCTION}\n\nQuestion: {QUESTION}\n\n" + "\n".join(
        f"[{x['from']}] {x['line']}" for x in lines
    )
    r2 = call(client, answer_prompt, stream=True)
    result["2"] = {**r2, "prompt": answer_prompt}

    result["total"] = {
        "end_to_end_ms": ms(run_start),
        "input_tokens": r1b["input_tokens"] + r2["input_tokens"],
        "output_tokens": r1b["output_tokens"] + r2["output_tokens"],
        "cost_usd": r1b["cost_usd"] + r2["cost_usd"],
    }
    (HERE / "result-v2.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
