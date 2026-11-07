"""Link-recovery follow-up: score every arm with the pre-registered matching rule.

Reads Graphify output (`{run}-graph.json`) or our own proposals (`{run}-proposals.json`),
reduces both to unordered brain-node pairs, and writes `scores-arms.json`.

Usage (from the repo root):
    uv run --project app python evals/experiments/link-recovery/score_arms.py <experiment dir>
"""

import json
import sys
from pathlib import Path

from yggdras.data.graph.structural import build_map, normalize

exp = Path(sys.argv[1])
key = json.loads((exp / "answer-key.json").read_text(encoding="utf-8"))
deleted = {frozenset(d["pair"]) for d in key["deleted_pairs"]}
stripped = build_map(exp / "brain-stripped")
remaining = {frozenset((e["from_slug"], e["to_slug"])) for e in stripped["edges"]}
slugs = {n["slug"] for n in stripped["nodes"]}
lookup: dict[str, set[str]] = {}
for n in stripped["nodes"]:
    for name in [n["slug"], n["name"], *n["aliases"]]:
        lookup.setdefault(normalize(name), set()).add(n["slug"])


def graphify_pairs(path: Path) -> dict[frozenset, list[str]]:
    """Same rule as score.py: unambiguous label mapping, model edges only."""
    g = json.loads(path.read_text(encoding="utf-8"))
    mapped = {}
    for n in g["nodes"]:
        hits = lookup.get(normalize(n["label"]), set())
        mapped[n["id"]] = next(iter(hits)) if len(hits) == 1 else None
    pairs: dict[frozenset, list[str]] = {}
    for e in g["links"]:
        a, b = mapped.get(e["source"]), mapped.get(e["target"])
        if e.get("_origin") != "ast" and a and b and a != b:
            pairs.setdefault(frozenset((a, b)), []).append(e["relation"])
    return pairs


def own_pairs(path: Path) -> dict[frozenset, list[str]]:
    pairs: dict[frozenset, list[str]] = {}
    for p in json.loads(path.read_text(encoding="utf-8"))["proposals"]:
        if p["from"] in slugs and p["to"] in slugs and p["from"] != p["to"]:
            pairs.setdefault(frozenset((p["from"], p["to"])), []).append(p["reason"])
    return pairs


def load(run: str) -> dict[frozenset, list[str]]:
    g, o = exp / f"{run}-graph.json", exp / f"{run}-proposals.json"
    return graphify_pairs(g) if g.exists() else own_pairs(o)


def summary(pairs: dict[frozenset, list[str]]) -> dict:
    p = set(pairs)
    return {
        "proposal_pairs": len(p),
        "refound": len(p & remaining),
        "recovered": sorted(sorted(x) for x in p & deleted),
        "new": [
            {"pair": sorted(x), "evidence": pairs[x]}
            for x in sorted(p - remaining - deleted, key=sorted)
        ],
    }


def noise(a: set, b: set) -> dict:
    ra, rb = a & deleted, b & deleted
    return {
        "pairs_both": len(a & b),
        "pairs_one_run_only": len(a ^ b),
        "overlap": round(len(a & b) / max(len(a | b), 1), 3),
        "recovered_both": len(ra & rb),
        "recovered_flips": sorted(sorted(x) for x in ra ^ rb),
    }


arms = {
    "original": ("run-1", "run-2"),
    "A": ("arm-a-run-1", "arm-a-run-2"),
    "B": ("arm-b-run-1", "arm-b-run-2"),
    "C": ("arm-c-run-1", "arm-c-run-2"),
}
result = {}
loaded = {}
for arm, runs in arms.items():
    if not all(
        (exp / f"{r}-graph.json").exists() or (exp / f"{r}-proposals.json").exists() for r in runs
    ):
        continue
    one, two = (load(r) for r in runs)
    loaded[arm] = (one, two)
    result[arm] = {"run_1": summary(one), "run_2": summary(two), "noise": noise(set(one), set(two))}

# Arm C adds to run 2 of the original; also score the combination.
if "C" in loaded:
    base = load("run-2")
    combined = [{**base, **c} for c in loaded["C"]]
    result["original_run_2_plus_C"] = {
        "run_1": summary(combined[0]),
        "run_2": summary(combined[1]),
        "noise": noise(set(combined[0]), set(combined[1])),
    }

(exp / "scores-arms.json").write_text(
    json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
)
for arm, r in result.items():
    one, two = r["run_1"], r["run_2"]
    print(
        f"{arm}: recovered {len(one['recovered'])}/20 and {len(two['recovered'])}/20, "
        f"new {len(one['new'])} and {len(two['new'])}, "
        f"pairs {one['proposal_pairs']} and {two['proposal_pairs']}, noise {r['noise']}"
    )
