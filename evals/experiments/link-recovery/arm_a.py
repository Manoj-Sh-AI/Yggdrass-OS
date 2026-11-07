"""Link-recovery follow-up, arm A: free baseline, no model.

Scans each fact line for other nodes' slugs, names and aliases and proposes a link,
with the fact line as its reason.

Usage (from the repo root):
    uv run --project app python evals/experiments/link-recovery/arm_a.py <experiment dir> <run name>
"""

import json
import re
import sys
import time
from pathlib import Path

from yggdras.data.graph.structural import build_map, normalize

FACT = re.compile(r"^- \[(stated|observed|derived)\] (.*)$")

exp, run = Path(sys.argv[1]), sys.argv[2]
root = exp / "brain-stripped"
start = time.perf_counter()
graph = build_map(root)

# Roster: normalized name -> slugs. A name shared by two nodes is ambiguous and skipped.
roster: dict[str, set[str]] = {}
for n in graph["nodes"]:
    for name in {n["slug"], n["name"], *n["aliases"]}:
        if normalize(name):
            roster.setdefault(normalize(name), set()).add(n["slug"])
names = sorted((k for k, v in roster.items() if len(v) == 1), key=lambda k: (-len(k.split("-")), k))


def matches(text: str) -> list[str]:
    """Slugs named in text, longest roster names first, no overlapping matches."""
    tokens = normalize(text).split("-")
    taken = [False] * len(tokens)
    found = []
    for name in names:
        parts = name.split("-")
        for i in range(len(tokens) - len(parts) + 1):
            if tokens[i : i + len(parts)] == parts and not any(taken[i : i + len(parts)]):
                taken[i : i + len(parts)] = [True] * len(parts)
                found.append(next(iter(roster[name])))
    return found


proposals = []
for n in graph["nodes"]:
    lines = (root / n["path"]).read_text(encoding="utf-8").splitlines()
    for number, line in enumerate(lines, 1):
        m = FACT.match(line)
        if not m:
            continue
        body = m.group(2)
        cut = body.rfind(" (src:")
        fact = body[:cut] if cut != -1 else body
        for slug in dict.fromkeys(matches(fact)):
            if slug != n["slug"]:
                proposals.append({"from": n["slug"], "to": slug, "reason": line, "line": number})

out = {
    "arm": "A",
    "run": run,
    "seconds": round(time.perf_counter() - start, 3),
    "cost_usd": 0.0,
    "proposals": proposals,
}
(exp / f"arm-a-{run}-proposals.json").write_text(
    json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
)
print(f"arm A {run}: {len(proposals)} proposals in {out['seconds']} s")
