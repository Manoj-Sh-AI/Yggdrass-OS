"""Speed test for one query: map lookup (no model), then one streamed Haiku call.

Stage 1 loads .map/graph.json once (load not counted), finds the question's noun by
node name, alias or slug, and returns its edges plus the fact lines of its note.
Stage 2 sends a 2-line instruction, the question and Stage 1's output to the
smallest fast model, streamed. Nothing in the brain is written. Writes result.json here.
"""

import json
import re
import statistics
import time
import unicodedata
from pathlib import Path

import anthropic

HERE = Path(__file__).parent
BRAIN_REPO = Path(r"C:\Users\shman\yggdras-brain")
BRAIN = BRAIN_REPO / "demo-brain"
MAP = BRAIN_REPO / ".map" / "graph.json"
QUESTION = "Who replaced Ken Mattingly on Apollo 13, and why?"
MODEL = "claude-haiku-5-5"
PRICE_IN, PRICE_OUT = 0.10, 0.50  # $ per MTok, prompts under 100K tokens
INSTRUCTION = (
    "Answer the question using only the links and facts below; add nothing of your own.\n"
    "Cite the node slug for each point; if they don't contain the answer, say \"I don't have that\"."
)
WARM_RUNS = 100


def norm(s: str) -> str:
    """D02 matching rule (lowercase, strip accents, space/'_'/'-' alike), plus punctuation as space."""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def load_map() -> dict:
    g = json.loads(MAP.read_text(encoding="utf-8"))
    names = []  # (normalized name, node), longest first so the most specific name wins
    for n in g["nodes"]:
        for name in {n["name"], n["slug"], *n.get("aliases", [])}:
            names.append((norm(name), n))
    names.sort(key=lambda x: -len(x[0]))
    return {"graph": g, "names": names, "by_id": {n["id"]: n for n in g["nodes"]}}


def stage1(m: dict, question: str) -> dict:
    q = f" {norm(question)} "
    matches = []  # every node named in the question, longest name first
    for name, node in m["names"]:
        if f" {name} " in q and node not in [x[1] for x in matches]:
            matches.append((name, node))
    if not matches:
        return {"noun": None, "other_matches": [], "edges": [], "facts": []}
    noun = matches[0][1]
    edges = [
        f"{e['from_slug']} --{e['reason']}--> {e['to_slug']}"
        for e in m["graph"]["edges"]
        if noun["id"] in (e["from"], e["to"])
    ]
    text = (BRAIN / noun["path"]).read_text(encoding="utf-8")
    facts_section = text.split("## Facts", 1)[1].split("\n## ", 1)[0]
    facts = [line for line in facts_section.splitlines() if line.startswith("- [")]
    return {
        "noun": noun["slug"],
        "matched_as": matches[0][0],
        "other_matches": [n["slug"] for _, n in matches[1:]],
        "edges": edges,
        "facts": facts,
    }


def render(s1: dict) -> str:
    return (
        f"Node: {s1['noun']}\n\nLinks:\n" + "\n".join(f"- {e}" for e in s1["edges"])
        + f"\n\nFacts from {s1['noun']}:\n" + "\n".join(s1["facts"])
    )


def stage2(prompt: str) -> dict:
    client = anthropic.Anthropic()
    start = time.perf_counter()
    first = None
    with client.messages.stream(
        model=MODEL,
        max_tokens=2048,
        output_config={"effort": "low"},
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        for text in stream.text_stream:
            if first is None and text:
                first = time.perf_counter() - start
        final = stream.get_final_message()
    total = time.perf_counter() - start
    u = final.usage
    return {
        "model": final.model,
        "first_word_s": round(first, 3) if first is not None else None,
        "full_s": round(total, 3),
        "usage": u.model_dump(),
        "cost_usd": (u.input_tokens * PRICE_IN + u.output_tokens * PRICE_OUT) / 1e6,
        "answer": "".join(b.text for b in final.content if b.type == "text"),
    }


def main() -> None:
    t = time.perf_counter()
    m = load_map()
    load_ms = (time.perf_counter() - t) * 1000

    t = time.perf_counter()
    s1 = stage1(m, QUESTION)
    first_ms = (time.perf_counter() - t) * 1000
    warm = []
    for _ in range(WARM_RUNS):
        t = time.perf_counter()
        stage1(m, QUESTION)
        warm.append((time.perf_counter() - t) * 1000)

    result = {
        "question": QUESTION,
        "map_load_ms_not_counted": round(load_ms, 2),
        "stage1": {
            "first_run_ms": round(first_ms, 3),
            "warm_median_ms": round(statistics.median(warm), 3),
            "warm_max_ms": round(max(warm), 3),
            "output": s1,
        },
    }
    if s1["noun"] is None:
        result["stage2"] = "skipped: Stage 1 found no node in the question"
    else:
        prompt = f"{INSTRUCTION}\n\nQuestion: {QUESTION}\n\n{render(s1)}"
        result["stage2_prompt"] = prompt
        result["stage2"] = stage2(prompt)
    (HERE / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
