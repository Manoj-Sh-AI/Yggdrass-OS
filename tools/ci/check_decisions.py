"""Decision-record names (planning/agentic-engineering.md item 53).

New records in rationale/decisions are named YYYYMMDD-slug.md, so two agents on two
branches can never claim the same number. Existing D-numbered and slug-only records are
kept as they are (the register cites them as D13, D44 ...). Fails on:
  - a NEW record whose name is not YYYYMMDD-slug.md (e.g. 0043-foo.md, D46-foo.md)
  - two records sharing a slug (the residual same-topic-same-day collision)

Usage: python tools/ci/check_decisions.py <base-ref>
"""

from __future__ import annotations

import re
import subprocess
import sys

FOLDER = "rationale/decisions/"
DATED = re.compile(r"^(\d{8})-([a-z0-9]+(?:-[a-z0-9]+)*)\.md$")
OLD = re.compile(r"^(?:D?\d+-)?([a-z0-9-]+)\.md$", re.I)
EXEMPT = {"_template.md", "README.md"}
# Records that existed when the date-slug rule was adopted (2026-11-22). Frozen: never add
# to this list; a new record takes a YYYYMMDD- name instead.
LEGACY = frozenset("""
0001-project-setup.md D02-node-identity.md D32-own-viewer.md D33-button-first-approval.md
D35-one-lia.md D36-lia-write-tools.md D37-uploads.md D38-restore.md D39-frontend-prototype.md
D40-routine-application-boundary.md D41-phase-1-revised-boundaries.md
D42-phase-2-shared-planning.md D43-brain-postgres-schema.md D44-database-is-the-brain.md
D45-notes-http-proxy.md android-release-signing.md android-self-update.md
bounded-application-agents.md chat-conductor.md connected-workspace-foundation.md
connector-directory.md connector-skill-catalogs.md mobile-open-air.md
nature-glass-presentation.md note-work-bridge.md separated-note-handoff.md
shared-postgresql.md signal-workspace.md supabase-database.md temporal-agent-execution.md
voice-reminders.md windows-desktop-host.md
""".split())


def slug(name: str) -> str:
    dated = DATED.match(name)
    if dated:
        return dated.group(2)
    old = OLD.match(name)
    return (old.group(1) if old else name).lower()


def problems(all_names: list[str], new_names: list[str]) -> list[str]:
    found = []
    for name in new_names:
        if name not in EXEMPT and name not in LEGACY and not DATED.match(name):
            found.append(f"{FOLDER}{name}: new decision records are named YYYYMMDD-slug.md "
                         "(no sequence numbers; AGENTS.md 'Branches and shared counters').")  # fmt: skip
    slugs: dict[str, list[str]] = {}
    for name in all_names:
        if name not in EXEMPT:
            slugs.setdefault(slug(name), []).append(name)
    for key, names in sorted(slugs.items()):
        if len(names) > 1 and any(n in new_names for n in names):
            found.append(f"Decision records share the slug '{key}': {', '.join(sorted(names))}.")
    return found


def git(*args: str) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout


def main(base: str) -> int:
    all_names = [p.rsplit("/", 1)[-1] for p in git("ls-files", FOLDER).split()]
    added = git("diff", "--name-only", "--diff-filter=AR", f"{base}...HEAD", "--", FOLDER).split()
    found = problems(all_names, [p.rsplit("/", 1)[-1] for p in added])
    for line in found:
        print(f"::error::{line}")
    print(f"decisions: {len(all_names)} records, {len(added)} new, {len(found)} problems")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "origin/main"))
