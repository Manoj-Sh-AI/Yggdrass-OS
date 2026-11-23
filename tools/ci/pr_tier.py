"""Review tier of a PR (planning/agentic-engineering.md items 51-52, the tier table).

tier1 (mechanical): only docs/markdown, .test_durations, lockfiles, .changes entries
tier3 (risky): any risky path, or > 400 changed lines, > 10 files, > 5 top-level dirs
tier2 (ordinary): everything else

Tier 3 is "merge by hand": the workflow never arms auto-merge for it and fails the
`tier` check until a human applies the label `tier3-reviewed` (a label alone is not the
control; the owner merging by hand is, because a GitHub App token can set labels).
The risky-path list is the plan's minimum; the final list is the owner's decision.

Usage: git diff --numstat BASE...HEAD | python tools/ci/pr_tier.py   (prints tier on the last line)
"""

from __future__ import annotations

import fnmatch
import os
import sys

MAX_LINES, MAX_FILES, MAX_DIRS = 400, 10, 5
MECHANICAL = ["*.md", "docs/*", ".test_durations", "*/.test_durations", "*package-lock.json",
              "*uv.lock", ".changes/*"]  # fmt: skip
RISKY = [
    "app/api/migrations/*", "*auth*", "*permission*", "*webhook*", "*security*",
    "app/api/src/yggdress_app/brain.py", "app/api/src/yggdress_app/notes_proxy.py",
    "app/api/src/yggdress_app/runtime_grants.py", "app/api/src/yggdress_app/temporal*",
    ".github/*", ".claude/*", "tools/ci/*", "railway.*", "Dockerfile*",
]  # fmt: skip


def matches(path: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(path, p) for p in patterns)


def classify(numstat: list[tuple[int, int, str]]) -> tuple[str, list[str]]:
    if not numstat:
        return "tier1", ["empty diff"]
    paths = [p for _, _, p in numstat]
    lines = sum(a + d for a, d, _ in numstat)
    dirs = {p.split("/", 1)[0] if "/" in p else "." for p in paths}
    reasons = [f"risky path: {p}" for p in paths if matches(p, RISKY)]
    if lines > MAX_LINES:
        reasons.append(f"{lines} changed lines > {MAX_LINES}")
    if len(paths) > MAX_FILES:
        reasons.append(f"{len(paths)} files > {MAX_FILES}")
    if len(dirs) > MAX_DIRS:
        reasons.append(f"{len(dirs)} top-level dirs > {MAX_DIRS}")
    if reasons:
        return "tier3", reasons
    if all(matches(p, MECHANICAL) for p in paths):
        return "tier1", ["mechanical paths only"]
    return "tier2", [f"{lines} lines, {len(paths)} files"]


def parse(text: str) -> list[tuple[int, int, str]]:
    rows = []
    for line in text.splitlines():
        parts = line.split("\t")
        if len(parts) == 3:
            added, deleted, path = parts
            rows.append((int(added) if added.isdigit() else 0, int(deleted) if deleted.isdigit() else 0, path))
    return rows


def main() -> int:
    tier, reasons = classify(parse(sys.stdin.read()))
    for reason in reasons:
        print(f"- {reason}")
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as handle:
            handle.write(f"tier={tier}\n")
    print(tier)
    return 0


if __name__ == "__main__":
    sys.exit(main())
