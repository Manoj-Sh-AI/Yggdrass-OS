# Session orchestration: Temporal holds the loop, headless SDK workers do the work

Date: 2026-11-23
Status: accepted (Manoj approved D1–D8 as recommended, 2026-11-23)

## Context

Manoj asked for one orchestrator that splits a job, starts worker sessions, checks what
comes back and sends unfinished work back. The design is in
`planning/session-orchestration.md`. §13 of that file lists eight choices.

## Decision

- **D1:** Temporal workflow code holds the loop: scheduling, limits, checks and send-backs.
  A Fable session (`claude-fable-5-2`, tools Read/Grep/Glob only) only splits the job and
  writes the final report. Workers are Opus 5.5 (`claude-opus-5-5`) headless Agent SDK
  sessions.
- **D2:** The code lives in `tools/orchestrate/`, its own uv project. The app never depends
  on the Agent SDK.
- **D3:** Limits per attempt are $3, 60 turns and 45 min. Per run, $15 and 3 h. Each task
  gets 2 send-backs. A Console workspace spend limit, set by Manoj, is the only hard
  ceiling.
- **D4:** Worktrees go in `%LOCALAPPDATA%\yggdras\worktrees`, outside OneDrive and the
  repo.
- **D5:** Manoj approves every plan before any worker starts.
- **D6:** Workers authenticate with an API key (`ANTHROPIC_API_KEY`) on a workspace that
  has a spend limit, not with Manoj's claude.ai login.
- **D7:** A task that depends on another branches from that task's branch (stacked).
- **D8:** A send-back resumes the worker's own session.

## Alternatives considered

- One long Fable session driving workers through custom tools. It uses more tokens, and a
  model makes the pass/fail call. The Stage 6 research records leads stopping early.
- The code inside `app/api/`. The app would gain an SDK dependency for dev tooling.
- `.claude/worktrees/`. OneDrive would sync it, and the `.claude/**` path hooks may treat
  files there as protected.
- claude.ai login. The SDK overview restricts it for third-party developers "unless
  previously approved", and whether that covers this use is unclear.
- A fresh session on every attempt. It gives a cleaner context but re-reads the repo every
  time.

## Tradeoffs

- Reliability and consistency are favoured over simplicity: the workflow, the plan
  validation and the check runner are extra code.
- Cost: an API key bills per token, outside any subscription.
- Stacked branches make merge order matter.

## Consequences

- A model never decides whether a task passed.
- Phase 2 must prove three things: the deny-rule probe, stop kills every process tree, and
  a crash-resume starts no worker twice.
- Any edit to the workflow definition is Tier 3 and is merged by hand.
