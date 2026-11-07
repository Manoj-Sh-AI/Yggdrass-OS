"""Link-recovery experiment, step 3: score Graphify runs with the pre-registered matching rule.

Usage (from the repo root):
    uv run --project app python evals/experiments/link-recovery/score.py <experiment dir>
"""

import json
import sys
from collections import Counter
from pathlib import Path

from yggdras.data.graph.structural import build_map, normalize

exp = Path(sys.argv[1])
key = json.loads((exp / "answer-key.json").read_text(encoding="utf-8"))
deleted = {frozenset(d["pair"]) for d in key["deleted_pairs"]}
stripped = build_map(exp / "brain-stripped")
remaining = {frozenset((e["from_slug"], e["to_slug"])) for e in stripped["edges"]}

# Rule 1: label -> brain node, by normalized slug, name or alias, only when unambiguous.
lookup: dict[str, set[str]] = {}
for n in stripped["nodes"]:
    for name in [n["slug"], n["name"], *n["aliases"]]:
        lookup.setdefault(normalize(name), set()).add(n["slug"])


def to_brain(label: str) -> str | None:
    hits = lookup.get(normalize(label), set())
    return next(iter(hits)) if len(hits) == 1 else None


def score(run: str) -> dict:
    g = json.loads((exp / f"{run}-graph.json").read_text(encoding="utf-8"))
    label = {n["id"]: n["label"] for n in g["nodes"]}
    mapped = {nid: to_brain(lab) for nid, lab in label.items()}
    proposals: dict[frozenset, list[dict]] = {}
    skipped = Counter()
    for e in g["links"]:
        if e.get("_origin") == "ast":
            skipped["ast"] += 1
            continue
        a, b = mapped.get(e["source"]), mapped.get(e["target"])
        if a is None or b is None:
            skipped["unmapped endpoint"] += 1
            continue
        if a == b:
            skipped["same node"] += 1
            continue
        proposals.setdefault(frozenset((a, b)), []).append(
            {"relation": e["relation"], "confidence": e["confidence"], "from": a, "to": b}
        )
    pairs = set(proposals)
    return {
        "graphify_nodes": len(g["nodes"]),
        "unmapped_labels": sorted(lab for nid, lab in label.items() if mapped[nid] is None),
        "graphify_edges": len(g["links"]),
        "skipped_edges": dict(skipped),
        "proposal_pairs": len(pairs),
        "refound": sorted(sorted(p) for p in pairs & remaining),
        "recovered": sorted(sorted(p) for p in pairs & deleted),
        "new": [
            {"pair": sorted(p), "edges": proposals[p]}
            for p in sorted(pairs - remaining - deleted, key=sorted)
        ],
        "relations": dict(Counter(x["relation"] for v in proposals.values() for x in v)),
        "_pairs": pairs,
    }


r1, r2 = score("run-1"), score("run-2")
p1, p2 = r1.pop("_pairs"), r2.pop("_pairs")
rec1, rec2 = {frozenset(p) for p in r1["recovered"]}, {frozenset(p) for p in r2["recovered"]}
new1, new2 = {frozenset(x["pair"]) for x in r1["new"]}, {frozenset(x["pair"]) for x in r2["new"]}
noise = {
    "proposal_pairs": {
        "run_1": len(p1),
        "run_2": len(p2),
        "both": len(p1 & p2),
        "only_run_1": len(p1 - p2),
        "only_run_2": len(p2 - p1),
        "overlap": round(len(p1 & p2) / max(len(p1 | p2), 1), 3),
    },
    "recovered": {
        "run_1": len(rec1),
        "run_2": len(rec2),
        "both": len(rec1 & rec2),
        "only_one_run": sorted(sorted(p) for p in rec1 ^ rec2),
    },
    "new_pairs": {
        "run_1": len(new1),
        "run_2": len(new2),
        "both": len(new1 & new2),
        "overlap": round(len(new1 & new2) / max(len(new1 | new2), 1), 3),
    },
}
result = {
    "run_1": r1,
    "run_2": r2,
    "noise": noise,
    "never_recovered": sorted(sorted(p) for p in deleted - rec1 - rec2),
}
(exp / "scores.json").write_text(
    json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
)
print(json.dumps(noise, indent=2))
for name, r in (("run 1", r1), ("run 2", r2)):
    print(
        f"\n{name}: {r['graphify_edges']} edges -> {r['proposal_pairs']} node pairs; "
        f"re-found {len(r['refound'])}, recovered {len(r['recovered'])}/20, new {len(r['new'])}; "
        f"skipped {r['skipped_edges']}; unmapped labels {r['unmapped_labels']}"
    )
