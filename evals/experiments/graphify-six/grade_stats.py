"""Grade answer runs (experiments 2 and 3) and compute the pre-registered statistics.

Grading: a negative is correct when it declines; an answerable question is correct when it
does not decline and its answer holds every key term (v7 `keys`, or grade_v6.KEYS for the
old 35). Hand overrides are applied from overrides.json ({file: {id: [correct, note]}}).

Statistics per arm: correct per run; mean with a Wilson 95% interval over all
question-runs; paired difference vs a reference arm (per question, the mean over runs),
with a standard error clustered by the question's first gold note; $ per correct; billed
tokens median and highest; end to end median and slowest; $ and seconds per run.

Usage: python grade_stats.py <questions.yaml> <ref arm> <overrides.json> <arm>=<run files,comma> [...]
"""

import json
import math
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

import yaml

sys.path.insert(0, r"C:/Users/shman/OneDrive/Desktop/Yggdrass OS/Yggdrass-OS/evals/experiments/speed-test-one-query")
from grade_v6 import KEYS as OLD_KEYS  # noqa: E402
from grade_v6 import NEGATIVE as OLD_NEG  # noqa: E402

qfile, ref, ovr_path = sys.argv[1], sys.argv[2], Path(sys.argv[3])
questions = {q["id"]: q for f in qfile.split(",") for q in yaml.safe_load(Path(f).read_text(encoding="utf-8"))["questions"]}
overrides = json.loads(ovr_path.read_text(encoding="utf-8")) if ovr_path.exists() else {}


def keys_of(qid: str) -> list[str]:
    return [str(k).lower() for k in (questions[qid].get("keys") or OLD_KEYS.get(qid, []))]


def cluster_of(qid: str) -> str:
    q = questions[qid]
    if q.get("gold_notes"):
        return q["gold_notes"][0]
    nodes = [n for n in (q.get("expected_nodes") or []) if n != "index.md"]
    return nodes[0] if nodes else qid


def grade(row: dict) -> tuple[bool, str]:
    if row["id"] in OLD_NEG:
        ok = row["status"] == "not_in_brain"
        return ok, "" if ok else "answered a negative"
    if row["status"] != "answer":
        return False, "declined an answerable question"
    missing = [k for k in keys_of(row["id"]) if k not in row["answer"].lower()]
    return not missing, f"lacks {missing}" if missing else ""


def wilson(k: int, n: int) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    z, p = 1.96, k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (round(c - h, 3), round(c + h, 3))


arms: dict[str, list[list[dict]]] = {}
for arg in sys.argv[4:]:
    name, files = arg.split("=", 1)
    runs = []
    for f in files.split(","):
        rows = json.loads(Path(f).read_text(encoding="utf-8"))["rows"]
        for r in rows:
            r["correct"], r["miss"] = grade(r)
            o = overrides.get(Path(f).name, {}).get(r["id"])
            if o:
                r["correct"], r["miss"] = o[0], o[1]
        runs.append(rows)
    arms[name] = runs

per_q = {a: defaultdict(list) for a in arms}
report = {}
for a, runs in arms.items():
    allrows = [r for run in runs for r in run]
    for r in allrows:
        per_q[a][r["id"]].append(1.0 if r["correct"] else 0.0)
    k, n = sum(r["correct"] for r in allrows), len(allrows)
    cost = sum(r["cost_usd"] for r in allrows)
    be = [r["billed_equiv_in"] for r in allrows]
    e2e = [r["end_to_end_ms"] for r in allrows]
    hb = max(allrows, key=lambda r: r["billed_equiv_in"])
    sl = max(allrows, key=lambda r: r["end_to_end_ms"])
    report[a] = {
        "correct_per_run": [sum(r["correct"] for r in run) for run in runs],
        "of": len(runs[0]),
        "mean": round(k / n, 3),
        "wilson95": wilson(k, n),
        "cost_per_run": [round(sum(r["cost_usd"] for r in run), 5) for run in runs],
        "seconds_per_run": [round(sum(r["end_to_end_ms"] for r in run) / 1000, 1) for run in runs],
        "cost_per_correct": round(cost / k, 6) if k else None,
        "billed_in_median": round(st.median(be)),
        "billed_in_highest": [round(hb["billed_equiv_in"]), hb["id"]],
        "e2e_median_s": round(st.median(e2e) / 1000, 2),
        "e2e_slowest_s": [round(sl["end_to_end_ms"] / 1000, 2), sl["id"]],
        "misses": sorted({(r["id"], r["miss"]) for r in allrows if not r["correct"]}),
    }

for a in arms:
    if a == ref or ref not in arms:
        continue
    diffs = {q: st.mean(per_q[a][q]) - st.mean(per_q[ref][q]) for q in per_q[ref] if q in per_q[a]}
    n = len(diffs)
    mean = sum(diffs.values()) / n
    clusters = defaultdict(float)
    for q, d in diffs.items():
        clusters[cluster_of(q)] += d - mean
    g = len(clusters)
    se = math.sqrt(g / max(g - 1, 1) * sum(v * v for v in clusters.values())) / n
    report[a]["paired_vs_" + ref] = {
        "mean_diff": round(mean, 3),
        "clustered_se": round(se, 3),
        "ci95": [round(mean - 1.96 * se, 3), round(mean + 1.96 * se, 3)],
        "clusters": g,
        "beats_ref": mean - 1.96 * se > 0,
    }

for runs in arms.values():
    pass
print(json.dumps(report, indent=1, default=list))
