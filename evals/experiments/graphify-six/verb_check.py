"""Experiment 1b: Haiku checks fixed Arm A's candidate links and picks a verb, or rejects.

One item per ordered (from, to) candidate pair, in batches of 20. Each item carries the
candidate's reason line and both notes' fact lines. The verb list is every distinct link
reason in the original demo brain. Structured output per item: accept with a verb from
the list (from -> to) and a verbatim fact line, or reject.

Usage (from the repo root):
    uv run --project app --with anthropic python evals/experiments/graphify-six/verb_check.py \
        <brain-stripped dir> <demo-brain dir> <a-after proposals.json> <out.json>
"""

import json
import sys
import time
from pathlib import Path

import anthropic

from yggdras.data.graph.structural import build_map

MODEL = "claude-haiku-5-5"
PRICE_IN, PRICE_OUT = 0.10, 0.50
BATCH = 20
INSTRUCTION = (
    "You check proposed links between notes in a personal knowledge base. For each item, "
    "accept only if a fact line in the two notes directly states a relation between the "
    "FROM note's subject and the TO note's subject. If you accept, choose the one verb from "
    "the list that reads naturally as 'FROM <verb> TO', and quote the supporting fact line "
    "exactly as written. Otherwise reject, with verb null and an empty quote."
)

stripped, brain, cand_path, out = (Path(a) for a in sys.argv[1:5])
graph = build_map(stripped)
by_slug = {n["slug"]: n for n in graph["nodes"]}
verbs = sorted({e["reason"] for e in build_map(brain)["edges"]})


def facts(slug: str) -> list[str]:
    text = (stripped / by_slug[slug]["path"]).read_text(encoding="utf-8")
    section = text.split("## Facts", 1)[1].split("\n## ", 1)[0] if "## Facts" in text else ""
    return [line for line in section.splitlines() if line.startswith("- [")]


candidates: dict[tuple[str, str], str] = {}
for p in json.loads(cand_path.read_text(encoding="utf-8"))["proposals"]:
    candidates.setdefault((p["from"], p["to"]), p["reason"])
items = [{"id": i, "from": f, "to": t, "reason": r} for i, ((f, t), r) in enumerate(candidates.items())]

schema = {
    "type": "object",
    "properties": {
        "decisions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "decision": {"type": "string", "enum": ["accept", "reject"]},
                    "verb": {"anyOf": [{"type": "string", "enum": verbs}, {"type": "null"}]},
                    "quote": {"type": "string"},
                },
                "required": ["id", "decision", "verb", "quote"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["decisions"],
    "additionalProperties": False,
}


def render(item: dict) -> str:
    f, t = by_slug[item["from"]], by_slug[item["to"]]
    return (
        f"## Item {item['id']}: FROM {f['name']} ({f['slug']}) TO {t['name']} ({t['slug']})\n"
        f"Candidate reason: {item['reason']}\n"
        f"FROM fact lines:\n" + "\n".join(facts(f["slug"])) + "\n"
        f"TO fact lines:\n" + "\n".join(facts(t["slug"])) + "\n"
    )


client = anthropic.Anthropic()
start = time.perf_counter()
cost, tokens_in, tokens_out = 0.0, 0, 0
decided: dict[int, dict] = {}
for b in range(0, len(items), BATCH):
    batch = items[b : b + BATCH]
    prompt = f"{INSTRUCTION}\n\nVerb list: {', '.join(verbs)}\n\n" + "\n".join(render(i) for i in batch)
    with client.messages.stream(
        model=MODEL,
        max_tokens=8000,
        thinking={"type": "disabled"},
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": schema}},
        messages=[{"role": "user", "content": prompt}],
    ) as s:
        final = s.get_final_message()
    u = final.usage
    tokens_in, tokens_out = tokens_in + u.input_tokens, tokens_out + u.output_tokens
    cost += (u.input_tokens * PRICE_IN + u.output_tokens * PRICE_OUT) / 1e6
    data = json.loads("".join(x.text for x in final.content if x.type == "text"))
    ids = {i["id"] for i in batch}
    for d in data["decisions"]:
        if d["id"] in ids:
            decided[d["id"]] = d

for item in items:
    d = decided.get(item["id"])
    item.update(d if d else {"decision": "reject", "verb": None, "quote": "", "missing": True})
    item["quote_verbatim"] = bool(item["quote"]) and any(
        item["quote"].strip() in line for line in facts(item["from"]) + facts(item["to"])
    )

result = {
    "seconds": round(time.perf_counter() - start, 3),
    "cost_usd": cost,
    "tokens_in": tokens_in,
    "tokens_out": tokens_out,
    "verbs": verbs,
    "items": items,
}
out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
acc = sum(i["decision"] == "accept" for i in items)
print(f"{out.name}: {len(items)} items, {acc} accepted, ${cost:.4f}, {result['seconds']} s")
