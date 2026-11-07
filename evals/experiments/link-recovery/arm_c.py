"""Link-recovery follow-up, arm C: one model pass for links between notes in different batches.

Input: the roster tagged with run 2's batches, run 2's Graphify proposal pairs, and every
note's fact lines. Output: only cross-batch links not already proposed, each with a reason.

Usage (from the repo root, ANTHROPIC_API_KEY in the environment):
    uv run --project app --with anthropic==2.3.0 python \
        evals/experiments/link-recovery/arm_c.py <experiment dir> <run name>
"""

import json
import re
import sys
import time
from pathlib import Path

import anthropic

from yggdras.data.graph.structural import build_map, normalize

MODEL = "claude-sonnet-5-5"
PRICE = {"input": 3.0, "output": 15.0}  # USD per 1M tokens, Graphify's own Claude estimate
FACT = re.compile(r"^- \[(stated|observed|derived)\] ")

exp, run = Path(sys.argv[1]), sys.argv[2]
root = exp / "brain-stripped"
graph = build_map(root)
nodes = {n["slug"]: n for n in graph["nodes"]}
batch_of = {}
for i, files in enumerate(
    json.loads((exp / "run-2-batches.json").read_text(encoding="utf-8"))["batches"]
):
    for f in files:
        batch_of.update({n["slug"]: "AB"[i] for n in graph["nodes"] if n["path"] == f})

# Run 2's proposal pairs, by the same label rule as score.py.
lookup: dict[str, set[str]] = {}
for n in graph["nodes"]:
    for name in [n["slug"], n["name"], *n["aliases"]]:
        lookup.setdefault(normalize(name), set()).add(n["slug"])
g = json.loads((exp / "run-2-graph.json").read_text(encoding="utf-8"))
mapped = {}
for n in g["nodes"]:
    hits = lookup.get(normalize(n["label"]), set())
    mapped[n["id"]] = next(iter(hits)) if len(hits) == 1 else None
proposed = sorted(
    {
        tuple(sorted((mapped.get(e["source"]), mapped.get(e["target"]))))
        for e in g["links"]
        if mapped.get(e["source"])
        and mapped.get(e["target"])
        and mapped[e["source"]] != mapped[e["target"]]
    }
)

roster = "\n".join(
    f"{s} | batch {batch_of[s]} | {n['name']} | also: {', '.join(n['aliases']) or '-'}"
    for s, n in sorted(nodes.items())
)
notes = "\n\n".join(
    f"### {s} (batch {batch_of[s]})\n"
    + "\n".join(
        line
        for line in (root / n["path"]).read_text(encoding="utf-8").splitlines()
        if FACT.match(line)
    )
    for s, n in sorted(nodes.items())
)
system = (
    "You find missing links in a personal knowledge base. The notes were processed in two "
    "batches, A and B, by an extractor that only saw one batch at a time, so links between a "
    "batch-A note and a batch-B note were likely missed. Propose only links between one "
    "batch-A note and one batch-B note that are not already in the proposed list. Propose a "
    "link only when a fact line states or clearly implies a relation between the two notes. "
    "Each link needs a one-sentence reason that quotes the supporting fact. Output only JSON: "
    '{"links":[{"from":"<slug>","to":"<slug>","reason":"..."}]}'
)
user = (
    f"## Roster (slug | batch | name | aliases)\n{roster}\n\n"
    f"## Already proposed (do not repeat)\n"
    + "\n".join(f"{a} -- {b}" for a, b in proposed)
    + "\n\n"
    f"## Notes (fact lines only)\n{notes}\n"
)

start = time.perf_counter()
resp = anthropic.Anthropic().messages.create(
    model=MODEL, max_tokens=8000, system=system, messages=[{"role": "user", "content": user}]
)
seconds = round(time.perf_counter() - start, 1)
text = "".join(b.text for b in resp.content if b.type == "text")
raw = json.loads(text[text.find("{") : text.rfind("}") + 1])["links"]

kept, dropped = [], []
for x in raw:
    a, b = x.get("from"), x.get("to")
    ok = (
        a in nodes
        and b in nodes
        and batch_of[a] != batch_of[b]
        and tuple(sorted((a, b))) not in proposed
    )
    (kept if ok else dropped).append(x)
cost = (resp.usage.input_tokens * PRICE["input"] + resp.usage.output_tokens * PRICE["output"]) / 1e6
out = {
    "arm": "C",
    "run": run,
    "model": resp.model,
    "stop_reason": resp.stop_reason,
    "seconds": seconds,
    "tokens": {"input": resp.usage.input_tokens, "output": resp.usage.output_tokens},
    "cost_usd": round(cost, 4),
    "dropped": dropped,
    "proposals": kept,
}
(exp / f"arm-c-{run}-proposals.json").write_text(
    json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
)
print(
    f"arm C {run}: {len(kept)} kept, {len(dropped)} dropped, {seconds} s, "
    f"${cost:.4f}, stop {resp.stop_reason}"
)
