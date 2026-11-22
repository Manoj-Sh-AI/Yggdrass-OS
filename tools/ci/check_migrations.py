"""Migration safety for a PR (planning/agentic-engineering.md items 30-31).

The project uses numbered SQL files in app/api/migrations, not Alembic, so "single head"
becomes "no two migrations share a number". Checks, against the PR base:
  1. two migrations share a number                      -> fail
  2. a migration that exists on the base was edited/removed -> fail (applied ones are checksummed)
  3. a new migration has destructive DDL (DROP, RENAME, SET NOT NULL, ADD COLUMN ... NOT NULL
     without DEFAULT)                                    -> fail unless the hand-applied label
     `destructive-migration-approved` is present (expand-contract, AGENTS.md)

Usage: python tools/ci/check_migrations.py <base-ref>   (labels from env LABELS, comma-separated)
"""

from __future__ import annotations

import os
import re
import subprocess
import sys

MIGRATIONS = "app/api/migrations/"
LABEL = "destructive-migration-approved"
DESTRUCTIVE = [
    (re.compile(r"\bDROP\s+(TABLE|COLUMN|SCHEMA|TYPE|VIEW|INDEX)\b", re.I), "DROP"),
    (re.compile(r"\bRENAME\b", re.I), "RENAME"),
    (re.compile(r"\bSET\s+NOT\s+NULL\b", re.I), "SET NOT NULL"),
    (re.compile(r"\bADD\s+COLUMN\b(?:(?!;|DEFAULT).)*\bNOT\s+NULL\b(?:(?!;|DEFAULT).)*(;|$)", re.I | re.S),
     "ADD COLUMN ... NOT NULL without DEFAULT"),
    (re.compile(r"\bTRUNCATE\b", re.I), "TRUNCATE"),
]


def strip_comments(sql: str) -> str:
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.S)
    return re.sub(r"--[^\n]*", " ", sql)


def destructive(sql: str) -> list[str]:
    body = strip_comments(sql)
    return [name for pattern, name in DESTRUCTIVE if pattern.search(body)]


def problems(names: list[str], changed_existing: list[str], added: dict[str, str],
             labels: set[str]) -> list[str]:  # fmt: skip
    found = []
    numbers = [n.split("_", 1)[0] for n in names if n.endswith(".sql")]
    for number in sorted({n for n in numbers if numbers.count(n) > 1}):
        found.append(f"Two migrations share number {number}; renumber the new one.")
    for path in changed_existing:
        found.append(f"{path} exists on the base branch and was edited or removed; "
                     "add a new migration instead (applied migrations are checksummed).")  # fmt: skip
    if LABEL not in labels:
        for path, sql in sorted(added.items()):
            kinds = destructive(sql)
            if kinds:
                found.append(f"{path}: destructive DDL ({', '.join(kinds)}). Expand-contract "
                             "(AGENTS.md): ship the expand step first and the contract step in a "
                             f"later release, or a human applies the label {LABEL}.")  # fmt: skip
    return found


def git(*args: str) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout


def main(base: str) -> int:
    names = [p.rsplit("/", 1)[-1] for p in git("ls-files", MIGRATIONS).split() if p.endswith(".sql")]
    status = [line.split("\t") for line in git("diff", "--name-status", f"{base}...HEAD", "--", MIGRATIONS).splitlines()]
    changed_existing = [parts[1] for parts in status if parts[0][0] in "MDR"]
    added = {parts[1]: open(parts[1], encoding="utf-8").read() for parts in status if parts[0] == "A"}
    labels = {label.strip() for label in os.environ.get("LABELS", "").split(",") if label.strip()}
    found = problems(names, changed_existing, added, labels)
    for line in found:
        print(f"::error::{line}")
    print(f"migrations: {len(names)} files, {len(added)} new, {len(found)} problems")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "origin/main"))
