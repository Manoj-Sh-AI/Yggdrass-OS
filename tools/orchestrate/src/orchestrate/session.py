"""Headless Claude Code sessions through the Agent SDK (design §1, §4, §7, §10).

API names are from the installed claude-agent-sdk (ClaudeAgentOptions, ClaudeSDKClient,
HookMatcher, PermissionResultDeny, ResultMessage) and code.claude.com/docs/en/agent-sdk."""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    HookMatcher,
    PermissionResultDeny,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
)

from .brief import PLAN_SCHEMA, PLANNER_SYSTEM, RESULT_SCHEMA
from .isolation import PLANNER_MODEL, WORKER_MODEL, kill_tree, worker_env

log = logging.getLogger(__name__)

WORKER_ALLOW = [
    "Bash(git add:*)", "Bash(git commit:*)", "Bash(git status:*)", "Bash(git diff:*)",
    "Bash(git log:*)", "Bash(git show:*)", "Bash(uv run:*)", "Bash(uv sync:*)", "Bash(ls:*)",
]  # fmt: skip
WORKER_DENY_TOOLS = ["AskUserQuestion", "WebFetch", "WebSearch", "Agent", "Task"]

BASH_BLOCKS = [
    (r"\bgit\s+push\b", "Workers never push."),
    (r"\bgit\s+(merge|rebase|pull|fetch|cherry-pick|worktree|remote|config)\b",
     "Workers stay on their own branch."),
    (r"\bgit\s+reset\s+--hard\b|\bgit\s+clean\b", "No destructive git commands."),
    (r"\bgit\s+(checkout|switch)\b", "Workers stay on their own branch."),
    (r"\bgit\s+branch\s+-[dDmMf]", "Workers never delete or move branches."),
    (r"\bgit\s+(-C|--git-dir|--work-tree)\b|GIT_DIR=|GIT_WORK_TREE=",
     "No git redirection outside the worktree."),
    (r"\bgh\b", "Workers never use the GitHub CLI (no PRs, merges or API calls)."),
    (r"\brailway\b|\bdeploy\b", "Workers never deploy."),
]  # fmt: skip
PATH_TOOLS = {"Edit": "file_path", "Write": "file_path", "NotebookEdit": "notebook_path"}


def deny_reason(tool_name: str, tool_input: dict[str, Any], cwd: str) -> str | None:
    """Why the guard hook refuses this call, or None. Pure, so it is unit-tested."""
    if tool_name == "Bash":
        command = str(tool_input.get("command", ""))
        for pattern, reason in BASH_BLOCKS:
            if re.search(pattern, command):
                return reason
        return None
    key = PATH_TOOLS.get(tool_name)
    if key and tool_input.get(key):
        root = Path(cwd).resolve()
        target = (root / str(tool_input[key])).resolve()
        if root != target and root not in target.parents:
            return "Workers edit only inside their own worktree."
        relative = target.relative_to(root).as_posix() if target != root else ""
        if re.match(r"(\.claude|\.github)/|railway\.|app/api/migrations/", relative) or re.search(
            r"(^|/)\.env(\.|$)", relative
        ):
            return "That path is protected."
    return None


def guard_hook(cwd: str):
    async def guard(hook_input: dict, tool_use_id: str | None, context: dict) -> dict:
        reason = deny_reason(hook_input.get("tool_name", ""), hook_input.get("tool_input", {}), cwd)
        if not reason:
            return {}
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }
        }

    return guard


async def deny_all(tool_name: str, tool_input: dict, context: Any) -> PermissionResultDeny:
    # Reached only when nothing allowed the call and it would prompt; nobody is there to answer.
    return PermissionResultDeny(
        message="Not allowed for workers and no one is here to approve it. "
        "If you truly need it, finish with status blocked and say what is missing."
    )


@dataclass
class Outcome:
    session_id: str
    subtype: str = "no_result"
    is_error: bool = True
    structured: dict | None = None
    text: str = ""
    cost_usd: float = 0.0
    tokens: dict = field(default_factory=dict)
    duration_ms: int = 0
    num_turns: int = 0
    denials: list = field(default_factory=list)
    terminal_reason: str | None = None
    assistant_text: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _tokens(model_usage: dict | None) -> dict:
    total = {"input": 0, "output": 0, "cache_read": 0, "cache_creation": 0}
    for usage in (model_usage or {}).values():
        total["input"] += int(usage.get("inputTokens", 0))
        total["output"] += int(usage.get("outputTokens", 0))
        total["cache_read"] += int(usage.get("cacheReadInputTokens", 0))
        total["cache_creation"] += int(usage.get("cacheCreationInputTokens", 0))
    return total


def outcome_from(result: ResultMessage, assistant_text: str) -> Outcome:
    model_cost = sum(float(u.get("costUSD", 0)) for u in (result.model_usage or {}).values())
    structured = result.structured_output if isinstance(result.structured_output, dict) else None
    return Outcome(
        session_id=result.session_id,
        subtype=result.subtype,
        is_error=result.is_error,
        structured=structured,
        text=result.result or "",
        cost_usd=float(result.total_cost_usd or model_cost or 0.0),
        tokens=_tokens(result.model_usage),
        duration_ms=result.duration_ms,
        num_turns=result.num_turns,
        denials=[d if isinstance(d, dict) else str(d) for d in (result.permission_denials or [])],
        terminal_reason=result.terminal_reason,
        assistant_text=assistant_text[-4000:],
    )


def cli_pid(client: ClaudeSDKClient) -> int | None:
    # Not a public API: the transport's child process. Used only to kill a stuck tree.
    process = getattr(getattr(client, "_transport", None), "_process", None)
    return getattr(process, "pid", None)


async def run_session(
    prompt: str,
    options: ClaudeAgentOptions,
    on_event: Callable[[str], None] = lambda _: None,
    on_pid: Callable[[int | None], None] = lambda _: None,
) -> Outcome:
    """One turn: send the prompt, stream to the result. On cancel: interrupt, drain,
    disconnect, then kill the CLI tree, because the docs don't say what happens to it."""
    client = ClaudeSDKClient(options)
    pid = None
    texts: list[str] = []
    result: ResultMessage | None = None
    await client.connect()
    try:
        pid = cli_pid(client)
        on_pid(pid)
        await client.query(prompt)
        async for message in client.receive_response():
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        texts.append(block.text)
                    elif isinstance(block, ToolUseBlock):
                        on_event(block.name)
            elif isinstance(message, ResultMessage):
                result = message
    except Exception:
        # The docs say an error result is yielded first and then an error is raised: keep the
        # result (with its cost) if we have it; otherwise let the activity fail and retry.
        if result is None:
            raise
    except asyncio.CancelledError:
        try:
            await asyncio.wait_for(client.interrupt(), timeout=10)

            async def drain() -> None:
                async for _ in client.receive_response():
                    pass

            await asyncio.wait_for(drain(), timeout=20)
        except Exception as error:  # noqa: BLE001 -- best effort; the tree is killed below
            log.warning("interrupt/drain did not finish cleanly: %s", type(error).__name__)
        raise
    finally:
        try:
            await asyncio.wait_for(client.disconnect(), timeout=15)
        except Exception as error:  # noqa: BLE001 -- best effort; the tree is killed next
            log.warning("disconnect did not finish cleanly: %s", type(error).__name__)
        kill_tree(pid)
        on_pid(None)
    if result is None:
        return Outcome(
            session_id=options.session_id or options.resume or "", assistant_text="".join(texts)
        )
    return outcome_from(result, "\n".join(texts))


def worker_options(
    worktree: Path,
    scratch_url: str,
    session_id: str,
    resume: bool,
    budget_usd: float,
    max_turns: int,
    check_commands: list[str],
    log: Callable[[str], None] | None = None,
) -> ClaudeAgentOptions:
    cwd = str(worktree)
    return ClaudeAgentOptions(
        model=WORKER_MODEL,
        cwd=cwd,
        permission_mode="acceptEdits",
        allowed_tools=[*WORKER_ALLOW, *(f"Bash({c})" for c in check_commands)],
        disallowed_tools=WORKER_DENY_TOOLS,
        setting_sources=["user", "project"],
        env=worker_env(scratch_url),
        max_turns=max_turns,
        max_budget_usd=budget_usd,
        output_format={"type": "json_schema", "schema": RESULT_SCHEMA},
        hooks={"PreToolUse": [HookMatcher(matcher=None, hooks=[guard_hook(cwd)])]},
        can_use_tool=deny_all,
        session_id=None if resume else session_id,
        resume=session_id if resume else None,
        stderr=log,
    )


def planner_options(repo: Path, session_id: str, budget_usd: float) -> ClaudeAgentOptions:
    return ClaudeAgentOptions(
        model=PLANNER_MODEL,
        cwd=str(repo),
        tools=["Read", "Grep", "Glob"],  # the restricting option; it cannot edit or run anything
        system_prompt=PLANNER_SYSTEM,
        setting_sources=["user", "project"],
        permission_mode="default",
        can_use_tool=deny_all,
        max_turns=30,
        max_budget_usd=budget_usd,
        output_format={"type": "json_schema", "schema": PLAN_SCHEMA},
        session_id=session_id,
    )
