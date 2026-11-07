"""Experiment 5: score Graphify builds with link-recovery's rule (score_arms.py graphify_pairs).

Usage (from the repo root):
    uv run --project app python evals/experiments/graphify-six/exp5_score.py \
        <link-recovery dir> <out.json> <name>=<graph.json> [...]
"""

import json
import sys
from collections import Counter
from pathlib import Path

from yggdras.data.graph.structural import build_map, normalize

GENERIC = {"conceptually_related_to", "semantically_similar_to", "references", "related_to"}
exp, out = Path(sys.argv[1]), Path(sys.argv[2])
key = json.loads((exp / "answer-key.json").read_text(encoding="utf-8"))
deleted = {frozenset(d["pair"]) for d in key["deleted_pairs"]}
stripped = build_map(exp / "brain-stripped")
remaining = {frozenset((e["from_slug"], e["to_slug"])) for e in stripped["edges"]}
lookup: dict[str, set[str]] = {}
for n in stripped["nodes"]:
    for name in [n["slug"], n["name"], *n["aliases"]]:
        lookup.setdefault(normalize(name), set()).add(n["slug"])

result, sets = {}, {}
for arg in sys.argv[3:]:
    name, path = arg.split("=", 1)
    g = json.loads(Path(path).read_text(encoding="utf-8"))
    mapped = {}
    for n in g["nodes"]:
        hits = lookup.get(normalize(n["label"]), set())
        mapped[n["id"]] = next(iter(hits)) if len(hits) == 1 else None
    pairs: dict[frozenset, list[str]] = {}
    rel = Counter()
    for e in g["links"]:
        rel[e["relation"]] += 1
        a, b = mapped.get(e["source"]), mapped.get(e["target"])
        if e.get("_origin") != "ast" and a and b and a != b:
            pairs.setdefault(frozenset((a, b)), []).append(e["relation"])
    p = set(pairs)
    sets[name] = p
    total = sum(rel.values())
    result[name] = {
        "nodes": len(g["nodes"]),
        "edges": total,
        "relations": dict(rel.most_common()),
        "generic_share": round(sum(c for r, c in rel.items() if r in GENERIC) / max(total, 1), 3),
        "conceptually_related_share": round(rel.get("conceptually_related_to", 0) / max(total, 1), 3),
        "rationale_nodes": sum(1 for n in g["nodes"] if n.get("rationale")),
        "pairs": len(p),
        "refound": len(p & remaining),
        "recovered": sorted(sorted(x) for x in p & deleted),
        "new": [{"pair": sorted(x), "relations": pairs[x]} for x in sorted(p - remaining - deleted, key=sorted)],
    }
for base in {k.rsplit("-", 1)[0] for k in sets}:
    a, b = sets.get(f"{base}-1"), sets.get(f"{base}-2")
    if a is not None and b is not None:
        result[f"{base}-noise"] = {
            "overlap": round(len(a & b) / max(len(a | b), 1), 3),
            "recovered_flips": sorted(sorted(x) for x in (a & deleted) ^ (b & deleted)),
        }
out.write_text(json.dumps(result, indent=2), encoding="utf-8")
for k, v in result.items():
    if "recovered" in v:
        print(k, "recovered", len(v["recovered"]), "new", len(v["new"]), "generic", v["generic_share"], "rationale", v["rationale_nodes"], "edges", v["edges"])
    else:
        print(k, v)
