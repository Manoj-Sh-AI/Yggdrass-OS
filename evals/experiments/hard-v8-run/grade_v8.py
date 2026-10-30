"""Grade hard-v8 runs under the pre-registered rules and print the results table.

Grades: correct / partial / wrong. Partial exists only for v24 and y08. Traps are correct
only when the reply declines. Hand overrides come from overrides.json as
{file name: {id: ["correct"|"partial"|"wrong", note]}}.

Usage: python grade_v8.py <run dir> <brain demo-evals dir>
"""

import json
import statistics as st
import sys
from pathlib import Path

import yaml

run_dir, evals = Path(sys.argv[1]), Path(sys.argv[2])
PARTIAL_OK = {"v24", "y08"}
overrides = (
    json.loads((run_dir / "overrides.json").read_text(encoding="utf-8"))
    if (run_dir / "overrides.json").exists()
    else {}
)


def grade(row: dict, keys: list[str]) -> tuple[str, str]:
    if row["kind"] == "trap":
        return ("correct", "") if row["status"] == "not_in_brain" else ("wrong", "answered a trap")
    if row["status"] != "answer":
        return "wrong", "declined an answerable question"
    text = row["answer"].lower()
    have = [k for k in keys if k in text]
    if len(have) == len(keys):
        return "correct", ""
    if row["id"] in PARTIAL_OK and have:
        return "partial", f"has {len(have)}/{len(keys)}, lacks {[k for k in keys if k not in have]}"
    return "wrong", f"lacks {[k for k in keys if k not in text]}"


def ms_median(rows: list[dict]) -> float | None:
    return round(st.median(r["end_to_end_ms"] for r in rows) / 1000, 2) if rows else None


report = {}
for f in ("hard-v8", "held-out-v8"):
    qs = {
        q["id"]: q
        for q in yaml.safe_load((evals / f"{f}.yaml").read_text(encoding="utf-8"))["questions"]
    }
    for arm in ("whole", "pipeline"):
        runs = []
        for run in (1, 2, 3):
            path = run_dir / f"{f}-{arm}-{run}.json"
            if not path.exists():
                continue
            rows = json.loads(path.read_text(encoding="utf-8"))["rows"]
            for r in rows:
                keys = [str(k).lower() for k in qs[r["id"]].get("keys") or []]
                r["grade"], r["miss"] = grade(r, keys)
                o = overrides.get(path.name, {}).get(r["id"])
                if o:
                    r["grade"], r["miss"] = o
            path_g = path.with_suffix(".graded.json")
            path_g.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
            runs.append(rows)
        allr = [r for run in runs for r in run]
        if not allr:
            continue
        correct = sum(r["grade"] == "correct" for r in allr)
        cost = sum(r["cost_usd"] for r in allr)
        be = [r["billed_equiv_in"] for r in allr]
        hi = max(allr, key=lambda r: r["billed_equiv_in"])
        cold = [r for r in allr if r["cache"] == "cold"]
        warm = [r for r in allr if r["cache"] == "warm"]
        report[f"{f}/{arm}"] = {
            "score_per_run": [sum(r["grade"] == "correct" for r in run) for run in runs],
            "of": len(runs[0]),
            "cost_per_correct": round(cost / correct, 6) if correct else None,
            "billed_in_median": round(st.median(be)),
            "billed_in_highest": [round(hi["billed_equiv_in"]), hi["id"]],
            "e2e_median_s": ms_median(allr),
            "cost_per_run": [round(sum(r["cost_usd"] for r in run), 5) for run in runs],
            "cold": {
                "n": len(cold),
                "ids": [f"{r['id']}" for r in cold],
                "median_cost": round(st.median(r["cost_usd"] for r in cold), 6) if cold else None,
                "median_s": ms_median(cold),
            },
            "warm": {
                "n": len(warm),
                "median_cost": round(st.median(r["cost_usd"] for r in warm), 6) if warm else None,
                "median_s": ms_median(warm),
            },
            "partials": sorted({(r["id"], r["miss"]) for r in allr if r["grade"] == "partial"}),
            "misses": sorted({(r["id"], r["miss"]) for r in allr if r["grade"] == "wrong"}),
            "missed_every_run": sorted(
                {
                    r["id"]
                    for r in allr
                    if all(x["grade"] != "correct" for x in allr if x["id"] == r["id"])
                }
            ),
        }

for f in ("hard-v8", "held-out-v8"):
    sets = [set(v["missed_every_run"]) for k, v in report.items() if k.startswith(f)]
    report[f"{f}/missed_by_every_option"] = sorted(set.intersection(*sets)) if sets else []
(run_dir / "results.json").write_text(json.dumps(report, indent=2, default=list), encoding="utf-8")
print(json.dumps(report, indent=1, default=list))
