"""Experiment 4: compare `graphify update` (no backend) with our structural pass.

For each copy: map Graphify nodes to brain slugs by source_file (page nodes, plus heading
nodes folded onto their file), take edges between two different files as unordered pairs,
and compare with build_map() on the same copy. Also reports relation counts, edges whose
target is not a brain file (dangling), and whether two runs of the same corpus agree.

Usage (from the repo root):
    uv run --project app python evals/experiments/graphify-six/exp4_score.py <out.json> <copy dir> [...]
"""

import json
import sys
from collections import Counter
from pathlib import Path

from yggdras.data.graph.structural import build_map

result = {}
for d in map(Path, sys.argv[2:]):
    ours = build_map(d)
    by_path = {n["path"]: n["slug"] for n in ours["nodes"]}
    our_pairs = {frozenset((e["from_slug"], e["to_slug"])) for e in ours["edges"]}
    g = json.loads((d / "graphify-out" / "graph.json").read_text(encoding="utf-8"))
    file_of = {n["id"]: (n.get("source_file") or "").replace("\\", "/") for n in g["nodes"]}
    edges = g.get("links") or g.get("edges") or []
    pairs, dangling, rel = {}, [], Counter()
    for e in edges:
        rel[e.get("relation")] += 1
        a, b = by_path.get(file_of.get(e["source"], "")), by_path.get(file_of.get(e["target"], ""))
        if a and b and a != b:
            pairs.setdefault(frozenset((a, b)), set()).add(e.get("relation"))
        elif a and not b:
            dangling.append({"from": a, "target": e["target"], "relation": e.get("relation")})
    gp = set(pairs)
    result[d.name] = {
        "graphify_nodes": len(g["nodes"]),
        "graphify_edges": len(edges),
        "relations": dict(rel.most_common()),
        "our_pairs": len(our_pairs),
        "our_dangling": len(ours["dangling"]),
        "graphify_pairs": len(gp),
        "agree": len(gp & our_pairs),
        "missing": sorted(sorted(p) for p in our_pairs - gp),
        "extra": sorted(sorted(p) for p in gp - our_pairs),
        "pair_relations": Counter(r for rs in pairs.values() for r in rs),
        "dangling": dangling,
        "pairs": sorted(sorted(p) for p in gp),
    }
for corpus in ("intact", "stripped"):
    one, two = result.get(f"{corpus}-1"), result.get(f"{corpus}-2")
    if one and two:
        result[f"{corpus}-repeatable"] = one["pairs"] == two["pairs"] and one["graphify_edges"] == two["graphify_edges"]
Path(sys.argv[1]).write_text(json.dumps(result, indent=2, default=list), encoding="utf-8")
for k, v in result.items():
    if isinstance(v, dict):
        print(k, {x: v[x] for x in ("graphify_nodes", "graphify_edges", "relations", "our_pairs", "graphify_pairs", "agree")},
              "missing", len(v["missing"]), "extra", len(v["extra"]), "dangling", len(v["dangling"]))
    else:
        print(k, v)
