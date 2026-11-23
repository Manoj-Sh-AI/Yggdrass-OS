"""PreToolUse (Bash): keep verbose test and log output short (planning/agentic-engineering.md
item 43). A test run that prints thousands of lines reaches the transcript as its last 80,
with the exit status kept (pipefail), so a failure still reads as a failure.

Documented contract (code.claude.com/docs/en/hooks, read 2026-11-22): PreToolUse may return
hookSpecificOutput.updatedInput, which "Replaces the entire input object, so include
unchanged fields". No permissionDecision is returned, so this hook never grants
permission: auto mode and the deny/ask rules still judge the rewritten command.
"""

from __future__ import annotations

import json
import re
import sys

LIMIT = 80
VERBOSE = re.compile(
    r"(^|[;&|]\s*|\s)(uv run (--no-sync )?)?(pytest|vitest|jest|npm (run )?test|npx (vitest|jest)|"
    r"node \S*vitest\S*|npm run (build|lint)|next build|tsc( |$)|docker logs|journalctl|railway logs)"
)
ALREADY_SHORT = re.compile(r"\|\s*(tail|head|grep|wc|less|more)\b|>\s*\S")


def rewrite(command: str) -> str | None:
    """The shortened command, or None to leave it alone."""
    if not VERBOSE.search(command) or ALREADY_SHORT.search(command):
        return None
    return f"set -o pipefail; {{ {command.rstrip().rstrip(';')}; }} 2>&1 | tail -n {LIMIT}"


def main() -> int:
    try:
        data = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        return 0
    if data.get("tool_name") != "Bash":
        return 0
    tool_input = dict(data.get("tool_input") or {})
    new = rewrite(str(tool_input.get("command", "")))
    if new is None:
        return 0
    tool_input["command"] = new
    print(
        json.dumps(
            {"hookSpecificOutput": {"hookEventName": "PreToolUse", "updatedInput": tool_input}}
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
