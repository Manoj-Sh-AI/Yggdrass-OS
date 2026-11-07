"""Experiment 1 scoring: link-recovery's matching rule, plus checker decisions and verbs.

For a proposals file (Arm A output) or a checker file (verb_check.py output, which
holds A's candidates plus decisions), reduce to unordered pairs and report: recovered of
20, refound, new pairs, and, for checker files, accepted pairs only and verb accuracy
against the original brain's link lines in the proposed direction.

Usage (from the repo root):
    uv run --project app python evals/experiments/graphify-six/exp1_score.py \
        <link-recovery dir> <demo-brain dir> <file.json> [...]
"""

import json
import sys
from pathlib import Path

from yggdras.data.graph.structural import build_map

exp, brain = Path(sys.argv[1]), Path(sys.argv[2])
key = json.loads((exp / "answer-key.json").read_text(encoding="utf-8"))
deleted = {frozenset(d["pair"]) for d in key["deleted_pairs"]}
stripped = build_map(exp / "brain-stripped")
remaining = {frozenset((e["from_slug"], e["to_slug"])) for e in stripped["edges"]}
original = build_map(brain)
gold: dict[tuple[str, str], set[str]] = {}
for e in original["edges"]:
    gold.setdefault((e["from_slug"], e["to_slug"]), set()).add(e["reason"])
linked = {frozenset(k) for k in gold}

for name in sys.argv[3:]:
    data = json.loads(Path(name).read_text(encoding="utf-8"))
    items = data.get("items") or data["proposals"]
    accepted = [i for i in items if i.get("decision", "accept") == "accept"]
    pairs = {frozenset((i["from"], i["to"])) for i in accepted}
    new = sorted(sorted(p) for p in pairs - linked)
    result = {
        "file": name,
        "candidates": len(items),
        "accepted": len(accepted),
        "pairs": len(pairs),
        "recovered": sorted(sorted(p) for p in pairs & deleted),
        "refound": len(pairs & remaining),
        "new_pairs": new,
    }
    if "items" in data:
        with_gold = [i for i in accepted if (i["from"], i["to"]) in gold]
        right = [i for i in with_gold if i.get("verb") in gold[(i["from"], i["to"])]]
        result["verb_scored"] = len(with_gold)
        result["verb_correct"] = len(right)
        result["verb_wrong"] = [
            {"from": i["from"], "to": i["to"], "verb": i.get("verb"), "gold": sorted(gold[(i["from"], i["to"])])}
            for i in with_gold
            if i not in right
        ]
        lost = {frozenset((i["from"], i["to"])) for i in items} & deleted - pairs
        result["recovered_candidates_rejected"] = sorted(sorted(p) for p in lost)
        result["seconds"], result["cost_usd"] = data.get("seconds"), data.get("cost_usd")
    out = Path(name).with_suffix(".score.json")
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(
        f"{name}: recovered {len(result['recovered'])}/20, new {len(new)}, accepted {result['accepted']}"
        + (f", verbs {result['verb_correct']}/{result['verb_scored']}" if "verb_scored" in result else "")
    )
