"""Experiment 1a: link-recovery Arm A with two logged fixes (or without, via --no-fix).

Same as link-recovery/arm_a.py: scan each fact line (text before "(src:") for other nodes'
slugs, names and aliases, longest first, at hyphen-token boundaries, without overlap.
Fixes, both off with --no-fix:
1. A possessive 's / ’s is stripped before normalizing ("Apollo 11's" -> "Apollo 11").
2. The place names in BLOCKED (not nodes) are masked before matching, so "Kennedy" no
   longer matches john-f-kennedy inside them.

Usage (from the repo root):
    uv run --project app python evals/experiments/graphify-six/arm_a_fixed.py \
        <brain-stripped dir> <out.json> [--no-fix]
"""

import json
import re
import sys
import time
from pathlib import Path

from yggdras.data.graph.structural import build_map, normalize

FACT = re.compile(r"^- \[(stated|observed|derived)\] (.*)$")
POSSESSIVE = re.compile(r"(?<=\w)['’]s\b")
BLOCKED = ["Cape Kennedy", "Kennedy Space Center"]

args = [a for a in sys.argv[1:] if a != "--no-fix"]
fix = "--no-fix" not in sys.argv
root, out = Path(args[0]), Path(args[1])
start = time.perf_counter()
graph = build_map(root)

roster: dict[str, set[str]] = {}
for n in graph["nodes"]:
    for name in {n["slug"], n["name"], *n["aliases"]}:
        if normalize(name):
            roster.setdefault(normalize(name), set()).add(n["slug"])
names = sorted((k for k, v in roster.items() if len(v) == 1), key=lambda k: (-len(k.split("-")), k))
blocked = [normalize(b).split("-") for b in BLOCKED]


def matches(text: str) -> list[str]:
    if fix:
        text = POSSESSIVE.sub("", text)
    tokens = normalize(text).split("-")
    taken = [False] * len(tokens)
    if fix:
        for parts in blocked:
            for i in range(len(tokens) - len(parts) + 1):
                if tokens[i : i + len(parts)] == parts:
                    taken[i : i + len(parts)] = [True] * len(parts)
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

result = {
    "fixed": fix,
    "seconds": round(time.perf_counter() - start, 3),
    "cost_usd": 0.0,
    "proposals": proposals,
}
out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(f"arm A fixed={fix}: {len(proposals)} proposals in {result['seconds']} s")
