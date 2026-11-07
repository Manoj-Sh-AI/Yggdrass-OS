"""Link-recovery experiment, step 1: copy the Apollo demo brain and delete 20 linked pairs.

Reproducible: fixed seed, strata fixed in advance, original brain never touched.

Usage (from the repo root):
    uv run --project app python evals/experiments/link-recovery/sample.py \
        <path to yggdras-brain/demo-brain> evals/experiments/link-recovery
"""

import json
import random
import shutil
import sys
from collections import defaultdict
from pathlib import Path

from yggdras.data.graph.structural import build_map

SEED = 20261025
HUB = 7  # a hub has at least this many distinct neighbours
QUOTA = {"leaf": 2, "hub": 1, "hub-mid": 5, "mid": 12}  # 20 pairs, weighted away from hubs

src, exp = Path(sys.argv[1]), Path(sys.argv[2])
dst = exp / "brain-stripped"
if dst.exists():
    sys.exit(f"{dst} already exists; delete it deliberately to resample")

graph = build_map(src)
assert not graph["errors"] and not graph["dangling"], "source brain must be clean"
nbr = defaultdict(set)
for e in graph["edges"]:
    nbr[e["from_slug"]].add(e["to_slug"])
    nbr[e["to_slug"]].add(e["from_slug"])
pairs = sorted({tuple(sorted((e["from_slug"], e["to_slug"]))) for e in graph["edges"]})


def stratum(pair):
    lo, hi = sorted(len(nbr[s]) for s in pair)
    if lo == 1:
        return "leaf"
    if lo >= HUB:
        return "hub"
    return "hub-mid" if hi >= HUB else "mid"


by_stratum = defaultdict(list)
for p in pairs:
    by_stratum[stratum(p)].append(p)
rng = random.Random(SEED)
chosen = []
for name in ("leaf", "hub", "hub-mid", "mid"):
    chosen += [(name, p) for p in rng.sample(by_stratum[name], QUOTA[name])]

# Copy, then delete every link line between each chosen pair, in both directions.
shutil.copytree(src, dst)
removals = defaultdict(set)  # relative path -> line numbers
answer = []
for name, (a, b) in chosen:
    lines = [e for e in graph["edges"] if {e["from_slug"], e["to_slug"]} == {a, b}]
    for e in lines:
        path = next(n["path"] for n in graph["nodes"] if n["slug"] == e["from_slug"])
        removals[path].add(e["line"])
    answer.append({
        "pair": [a, b],
        "stratum": name,
        "neighbours": {a: len(nbr[a]), b: len(nbr[b])},
        "removed_links": [
            {"from": e["from_slug"], "to": e["to_slug"], "reason": e["reason"], "line": e["line"]} for e in lines
        ],
    })
for rel, numbers in removals.items():
    path = dst / rel
    kept = [line for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1) if i not in numbers]
    path.write_text("\n".join(kept) + "\n", encoding="utf-8", newline="\n")

key = {
    "seed": SEED,
    "hub_threshold": HUB,
    "quota": QUOTA,
    "source_pairs": len(pairs),
    "strata_sizes": {k: len(v) for k, v in sorted(by_stratum.items())},
    "deleted_pairs": answer,
}
(exp / "answer-key.json").write_text(json.dumps(key, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(f"deleted {len(answer)} pairs ({sum(len(a['removed_links']) for a in answer)} link lines) into {dst}")
