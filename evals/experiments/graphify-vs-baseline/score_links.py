"""Score Graphify's edges (built from a links-free copy) against the demo brain's links.

Matching rule, as in the link-recovery experiment: a Graphify node maps to a brain node
when its label, normalized by the D02 rule, equals the normalized slug, name or alias of
exactly one brain node. Edges between two different mapped nodes are compared as
unordered pairs with the brain's linked pairs. Relations are split into generic
(references, related_to and the like) and specific verbs.

Usage (from the repo root):
    uv run --project app python evals/experiments/graphify-vs-baseline/score_links.py \
        <demo-brain> <graphify graph.json> <out.json>
"""

import json
import sys
from collections import Counter
from pathlib import Path

from yggdras.data.graph.structural import build_map, normalize

GENERIC = {
    "references",
    "related_to",
    "conceptually_related_to",
    "semantically_similar_to",
    "mentions",
    "associated_with",
    "relates_to",
    "part_of_context",
}

brain, graph_path, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
original = build_map(brain)
links = {frozenset((e["from_slug"], e["to_slug"])) for e in original["edges"]}
lookup: dict[str, set[str]] = {}
for n in original["nodes"]:
    for name in [n["slug"], n["name"], *n["aliases"]]:
        lookup.setdefault(normalize(name), set()).add(n["slug"])

g = json.loads(graph_path.read_text(encoding="utf-8"))
to_brain = {}
for n in g["nodes"]:
    hits = lookup.get(normalize(n["label"]), set())
    to_brain[n["id"]] = next(iter(hits)) if len(hits) == 1 else None

edges = g.get("links") or g.get("edges") or []
relations = Counter(e.get("relation") for e in edges)
pairs: dict[frozenset, list[str]] = {}
unmapped = 0
for e in edges:
    a, b = to_brain.get(e["source"]), to_brain.get(e["target"])
    if not a or not b or a == b:
        unmapped += 1
        continue
    pairs.setdefault(frozenset((a, b)), []).append(e.get("relation"))

recovered = {p: r for p, r in pairs.items() if p in links}
new = {p: r for p, r in pairs.items() if p not in links}
result = {
    "brain_links_directed": len(original["edges"]),
    "brain_linked_pairs": len(links),
    "graphify_nodes": len(g["nodes"]),
    "graphify_nodes_mapped": sum(1 for v in to_brain.values() if v),
    "graphify_nodes_unmapped": sorted(n["label"] for n in g["nodes"] if not to_brain[n["id"]]),
    "graphify_edges": len(edges),
    "edges_not_between_two_brain_nodes": unmapped,
    "pairs_proposed": len(pairs),
    "pairs_recovered": len(recovered),
    "pairs_new": len(new),
    "relations": dict(relations.most_common()),
    "edges_generic": sum(c for r, c in relations.items() if r in GENERIC),
    "edges_specific": sum(c for r, c in relations.items() if r not in GENERIC),
    "recovered": sorted([sorted(p), r] for p, r in recovered.items()),
    "new_pairs_to_judge": sorted([sorted(p), r] for p, r in new.items()),
}
out.write_text(json.dumps(result, indent=2), encoding="utf-8")
print(json.dumps({k: v for k, v in result.items() if k not in ("recovered",)}, indent=1))
