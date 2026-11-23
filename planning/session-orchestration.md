# Session orchestration: design (Phase 1)

Status: **design for review. No code.** Phase 2 starts only after Manoj approves this
file and the decisions in §13.

One orchestrator splits a job, starts headless Claude Code worker sessions, checks what
comes back by running the checks itself, and sends unfinished work back until it passes
or a limit is hit. This is the Stage 6 pattern in `planning/agentic-engineering.md`. It
reuses the brief template from `AGENTS.md`, `tools/scratch_db.py` (item 61), the
committed hooks, and the Temporal setup already used by `temporal_agent_workflow.py`.

**Why this is worth trying here, and its limit.** Stage 6 says orchestration "reliably
saves context and reliably costs tokens", and that a single session plus subagents wins
unless all four conditions hold (3+ disjoint units, a command proves each one done, each
can be briefed without re-explaining the architecture, and you accept the faster spend).
Phase 3 measures this on a real job. It does not assume it.

---

## 1. Shape

```
Manoj ── start / status / answer / stop ──►  Temporal workflow  YggdrasSessionOrchestrationV1
                                               │  (deterministic code: queue, limits, checks, retries)
                                               │
                    plan activity ─────────────┤  Fable session, read-only tools, structured output
                                               │
     worker activity (≤3 at once) ─────────────┤  Opus 5.5 session per task, own worktree + scratch DB
                                               │
     check activity ───────────────────────────┘  runs the task's checks in the worktree, no model
```

The orchestrator has two parts, and neither can write code:

- **The control loop is Temporal workflow code.** It decides what runs, holds the limits,
  runs the checks and sends work back. It is code, not a model, so it cannot be talked out
  of a check and cannot "decide the job is finished early". Stage 6 records that failure
  for agent-team leads.
- **The Fable session is used only to split the job (§2) and to write the final report.**
  It gets `tools=["Read", "Grep", "Glob"]`. The SDK docs say `tools` is the restricting
  option, while `allowed_tools` "does not restrict Claude to only these tools". So it has no
  Edit, Write or Bash and cannot write code even if it tried.

Models are set per session through `ClaudeAgentOptions.model` (orchestrator
`claude-fable-5-2`, workers `claude-opus-5-5`). Neither is switched mid-session. The
alternative is a long-lived Fable session driving workers through custom tools. It is
rejected in §13 D1 because it costs more tokens and keeps the judgement in a model.

## 2. Splitting a job into tasks

Input: the job text Manoj writes. The plan activity runs one Fable `query()` with
`output_format={"type": "json_schema", "schema": PLAN}` and reads
`ResultMessage.structured_output`. The docs warn that a `success` result without
`structured_output` "is not a usable answer". That case counts as a failed plan, never as
an empty one.

Each task in the plan:

| field | meaning |
|---|---|
| `id` | short slug, also used in the branch and scratch-DB names |
| `objective` | one paragraph: what to change and why |
| `touches` | path globs the task may change (e.g. `docs/a.md`, `app/api/tests/test_x.py`) |
| `checks` | commands that prove it done, each with an expected exit code; optionally `screenshot: <url>` |
| `done_means` | one sentence a person can read |
| `depends_on` | task ids whose branch this task builds on |

**Code validates the plan before anything starts.** It rejects:
- a task with no `checks` (Stage 6's decomposition test: if you can't write the command
  that proves it done, it is not delegable);
- a `touches` glob that hits a protected path (`.claude/**`, `.github/**`, `railway.*`,
  `app/api/migrations/**`, Temporal workflow modules, `.env*`);
- a dependency cycle;
- more than 6 tasks.

A rejected plan goes back to Fable once with the reason. If it fails again, the
orchestration stops and reports. Both numbers are proposals (§13).

**Manoj approves the plan before any worker starts** (principle 4: the brain proposes, the
human disposes). The workflow waits on a Temporal update `approve_plan`. Approving can
also edit or drop tasks.

Checks Manoj can use in a plan:
- **tests:** `uv run pytest <path> -q`, `npm test -- <file>`;
- **lint/build:** `uv run ruff check .`, `npm run build`, `npm run lint:tokens`;
- **screenshot:** the check activity loads the URL with the existing Playwright setup and
  saves a PNG. It passes if the page loads without a console error. Whether it *looks*
  right is for Manoj to judge, so screenshots go to the report and never count as a pass
  on their own.

## 3. Worker brief

This is the `AGENTS.md` brief template filled in by code from the approved task. No model
rewrites it. The last line is verbatim.

```text
You are a worker on Yggdras. Do only this task.

Task <id>: <objective>
You may change only: <touches>
Done means: <done_means>
Before you report done, run these and paste their summary lines:
  <checks, one per line>

- You are in your own git worktree on branch <branch>. Commit there only.
- Never push, merge, open a PR, deploy, or edit .claude/, .github/, railway.*,
  app/api/migrations/ or any .env file.
- Your database is DATABASE_URL (a throwaway scratch database). Never use another one.
- Finish with the result object you were given a schema for.
- If you can't reach something you need, say exactly what's missing in your first message and stop. Don't substitute, mock, or guess.
```

On a send-back (§5), code appends: `Your previous attempt did not pass. Failing check:
<command>, exit <n>. Output (last 150 lines): <...>. Fix that.`

## 4. Worker result

The worker session runs with `output_format` set to this schema. The orchestration reads
only `structured_output` plus the `ResultMessage` accounting fields.

| field | values |
|---|---|
| `status` | `done` · `failed` · `blocked` |
| `summary` | ≤ 5 sentences |
| `branch` | branch name |
| `commits` | commit SHAs |
| `files_changed` | paths |
| `evidence` | per check: command, exit code, last 30 lines of output |
| `missing` | only when `blocked`: what exactly is needed (a credential, a decision, a file) |

`blocked` means the worker needs credentials or Manoj's input. The worker is told never to
guess (brief, last line). `AskUserQuestion` is not given to workers. A blocked task waits
and the others continue. See §8.

Accounting kept per worker session, from `ResultMessage`: `total_cost_usd`, `model_usage`
(the docs say "Prefer `model_usage` for token and cost accounting"), `duration_ms`,
`num_turns`, `subtype`, `session_id`, `permission_denials`. The docs call
`total_cost_usd` "client-side estimates, not authoritative billing data". The Phase 2
report gives both these figures and the Console usage for the same window.

## 5. Judging a result: run the checks, never trust the worker

When a worker activity returns, the workflow runs a **check activity**. It is pure code:
no model and no tokens. It works in that worker's worktree with that worker's scratch DB:

1. **Branch:** the branch exists, has ≥ 1 new commit, and the working tree is clean.
2. **Scope:** `git diff --name-only <base>...<branch>`. Every path must match the task's
   `touches`, and no path may be protected. Any file out of scope fails the check.
3. **Checks:** run every command in `checks` with a timeout (proposal: 10 min each). The
   gate's env scrubbing applies, and `DATABASE_URL`, `APP_DATABASE_URL` and
   `GATE_SCRATCH_DB_URL` are set to the scratch URL. Exit code and output are saved to the
   run folder.
4. **Screenshot**, if listed (see §2).

The worker's `status` and `evidence` are recorded but **never decide the verdict**. A
worker that says `done` while a check fails is sent back. One that says `failed` while
every check passes is still `failed`, because the brief made the worker the one who runs
the checks. Manoj sees that mismatch.

**Sending back:** if the verdict fails, the workflow starts a new worker activity that
*resumes the same session* (`resume=<session_id>`) with the send-back text from §3. The
worker keeps what it already learned, which costs less than a fresh session re-reading the
repo. The limit is 2 send-backs, so 3 attempts in total (proposal). After that the task is
`failed_after_retries` and goes in the report with the last failing output.

Two kinds of retry are kept apart:
- **Send-back:** the work is wrong. The workflow decides, up to the limit above.
- **Infrastructure retry:** the process died. Temporal decides it from the activity's
  `RetryPolicy`. See §9.

## 6. No two tasks on the same files at once

- Before scheduling, code compares the `touches` globs of every pair of tasks. If two
  tasks can match the same path, they **never run in parallel**: the later one gets an
  implicit `depends_on`. Two globs overlap when one could match a path the other matches.
  When code can't tell, it treats them as overlapping. A false "overlap" only costs time.
- A dependent task branches from its predecessor's branch, not from `main`, so it sees
  that work. The predecessor must have passed its checks first.
- The scope check in §5 enforces this afterwards: a worker that strays outside `touches`
  fails, even when nothing collided.
- Scratch DBs are per worker by construction (`scratch_db.py up <run>-<task>`, its own
  cluster and port). Worktrees are per worker by construction, see §7.

## 7. Isolation for each worker

- **Worktree:** code runs `git worktree add <root>/<run>-<task> -b
  claude/<YYYYMMDD>-<run>-<task> <base>`. `<root>` is outside OneDrive and outside the
  repo; the proposal is `%LOCALAPPDATA%\yggdras\worktrees` (§13 D4). The SDK option `cwd`
  points at it. Nothing from `.worktreeinclude` is copied, so **workers get no `.env`**:
  everything a worker needs is passed in `env`.
- **Scratch DB:** `scratch_db.py up <run>-<task>` before start, `down` after the
  orchestration ends (kept on `failed` so Manoj can look).
- **Environment:** the docs say `env` values are "merged on top of the inherited process
  environment". So env can add or override a variable but not remove one. The orchestration
  host process therefore **starts with a scrubbed environment** (no real `DATABASE_URL`, no
  brain or Supabase credentials). Each worker gets only `ANTHROPIC_API_KEY` (or the auth
  Manoj picks, §13 D6), `PATH`, the scratch URLs, and `CLAUDE_PROJECT_DIR`, which the
  session sets itself.
- **Settings and hooks:** the docs say that by default the SDK "loads the same filesystem
  settings as the Claude Code CLI: user, project, and local". Settings-file hooks run "when
  the corresponding `setting_sources` entry is enabled". The orchestration still passes
  `setting_sources=["user", "project"]` explicitly, so a library default can't silently
  change. `"local"` is left out: `.claude/settings.local.json` is a per-person file.
- **No push, merge or deploy, enforced three ways:**
  1. **Deny rules** in the user settings, already in place.
  2. An **SDK `PreToolUse` hook** registered by the orchestration. It refuses `git push`,
     `gh pr`, `gh api`, `git merge`, `git rebase`, `git checkout main`, `railway`, and any
     `git -C`/`--git-dir` that points outside the worktree. The docs give the evaluation
     order as "hooks, then deny rules, then ask rules, then permission mode, then allow
     rules, then `canUseTool`", so the hook runs first.
  3. A **`can_use_tool` callback** that denies anything that reaches it and records it.
     There is no human to answer a prompt.

  Workers use `permission_mode="acceptEdits"`, never `bypassPermissions`. File edits go
  through, and every other call that isn't allowed falls through to the callback.
- **Proof before any worker starts (the rule from the task):** a probe session is started
  with the exact worker options, in a throwaway worktree that holds a **decoy** `.env`
  (`PROBE=decoy`, never a real key). It is told to read `.env` with Read and with
  `cat .env`. The probe passes only if both calls appear in
  `ResultMessage.permission_denials` and `decoy` is not in the output. The orchestration
  refuses to start workers unless this probe passed on the same Claude Code version.
  Phase 2 adds a second probe that tries `git push` and must be refused.

## 8. Limits and what happens when one is hit

All numbers are **proposals for Manoj** (§13 D3), not measurements.

| limit | per worker attempt | per orchestration |
|---|---|---|
| cost | `max_budget_usd` = min($3, money left in the run) | $15 |
| turns | `max_turns` = 60 | n/a |
| wall time | activity `start_to_close_timeout` 45 min, `heartbeat_timeout` 2 min | workflow run timeout 3 h |
| concurrency | n/a | at most 3 worker activities (workflow semaphore, and `max_concurrent_activities=3` on the worker task queue) |
| retries | 2 send-backs; infrastructure `maximum_attempts=2` | plan re-asked at most once |

When a limit is hit:
- **Worker cost or turns:** the session ends with `error_max_budget_usd` or
  `error_max_turns`. That attempt counts as a failure. It is sent back only if the run's
  money allows another attempt; otherwise the task is reported.
- **Worker wall time:** Temporal cancels the activity, and the activity stops its process
  tree (§10). The attempt counts as a failure.
- **Run cost:** no new attempt starts. Running workers are stopped and the report is
  written. The docs describe `max_budget_usd` as a client-side estimate that stops the
  query when it "reaches" the value, so one attempt can overshoot. **The only hard ceiling
  is the Console workspace spend limit, which Manoj sets** (§13 D3).
- **Run wall time:** same as run cost.
- **Blocked worker:** the task waits for `answer(task, text)`, which resumes the session
  with Manoj's answer, or `skip(task)`. It holds no worker slot while waiting.
  Orchestration wall time keeps running.

## 9. Crash and resume without starting a worker twice

- Everything the orchestration knows lives in Temporal history: plan, approvals, results,
  verdicts and costs. After a host crash and restart, the workflow replays. **Completed
  activities are not re-run**: their results come from history. That is Temporal's
  guarantee, and Phase 2 proves it.
- A **running** worker activity sends a heartbeat on every SDK message. The heartbeat
  details hold `session_id`, the CLI process id and the attempt number. If the host dies,
  the heartbeat times out and Temporal retries the activity once (`maximum_attempts=2`).
  The retried activity:
  1. reads the last heartbeat details;
  2. kills that old process tree if it still exists, since the SDK docs don't say a
     child process dies with its parent;
  3. **resumes** the session (`resume=session_id`) with "You were interrupted. Check
     `git status` and `git log`, then continue."

  It never opens a second fresh session on the same task.
- The workflow id is `orch-<run>`, and starting an id that already exists is refused
  (`WorkflowAlreadyStartedError`, as `temporal_agent_service.py` already uses), so starting
  the same job twice can't double the workers.
- The workflow is new code with a versioned name (`…V1`). Stage 6 treats any edit to a
  Temporal workflow definition as Tier 3, merged by hand. A replay test against a recorded
  history is part of Phase 2's tests.

## 10. What Manoj sees, and the one stop action

- **While it runs:** `uv run orchestrate status <run>` (a Temporal query, which costs
  nothing) prints one line per task: state, attempt, elapsed, cost so far, last tool used,
  and the branch. The run folder (`<root>/runs/<run>/`) holds the plan, each brief, each
  result, each check's output and screenshots. The Temporal UI can also be turned on for
  the dev server.
- **Questions:** a blocked task shows `waiting for Manoj: <missing>`. Manoj replies with
  `orchestrate answer <run> <task> "<text>"`.
- **At the end:** a report written from results only. For each task: verdict, attempts,
  branch, files, cost, tokens and time; then totals, and anything that needs Manoj.
  Nothing is merged. Manoj merges.
- **Stop everything with one action:** `uv run orchestrate stop <run>`. It sends a
  workflow signal, the workflow cancels every running activity, and each activity, on
  receiving the cancellation through its heartbeat:
  1. calls `ClaudeSDKClient.interrupt()` (the docs say "only works in streaming mode", so
     workers use `ClaudeSDKClient`, not `query()`);
  2. drains `receive_response()`, because the docs say interrupt "does not clear the
     message buffer";
  3. disconnects;
  4. **then kills the CLI process tree with the existing `stop_tree`**
     (`local_runtime.py`, `taskkill /T /F` on Windows). The SDK docs don't say what
     interrupt or disconnect do to the subprocess, so the design doesn't rely on them.

  Worktrees and branches are kept for inspection. Scratch DBs are stopped.
- **If the host itself is hung:** `orchestrate stop --hard` terminates the workflow, then
  kills every process id recorded in the run folder. A terminated workflow runs no cleanup
  code, which is why the process ids are written to disk as well as to heartbeats.

## 11. Keeping the orchestrator's context small

- The Fable session sees only the job text, what it reads with Read/Grep/Glob, and for
  the final report the result objects and verdicts. It never sees worker transcripts, diffs
  or check logs.
- The workflow itself is code. Its state is briefs, result objects (capped: summary ≤ 5
  sentences, evidence tails ≤ 30 lines) and verdicts.
- Worker transcripts stay where the SDK keeps them (`~/.claude/projects/<encoded-cwd>/`,
  per the sessions docs). The report links each `session_id`, so Manoj can open one when he
  needs to.
- A send-back carries the last 150 lines of the failing command, never the whole log.

## 12. Where the code would go (Phase 2)

A separate uv project, **`tools/orchestrate/`**, with its own `pyproject.toml`
(`claude-agent-sdk`, `temporalio`). It is dev tooling, not a Yggdras product feature, so
the app never depends on the Agent SDK, and the three app layers stay untouched (§13 D2).
It reuses `tools/scratch_db.py` and imports nothing from `app/`. The exception is
`stop_tree`, which is copied in rather than imported, to keep the layering clean (flagged
in D2). Tests use temporalio's test environment with a fake session runner for the
workflow logic, plus the real Phase 2 runs with real sessions.

Phase 2 also needs, before code:
- a short spec in `requirements/` with acceptance criteria. Manoj's Phase 2 prove-list is
  the obvious source, but **Manoj writes or approves it** (constitution rules 1–2);
- a decision record `rationale/decisions/<date>-session-orchestration.md` for the choices
  in §13.

## 13. Decisions for Manoj

| # | decision | recommendation | alternative |
|---|---|---|---|
| D1 | What "the orchestrator" is | **Temporal code holds the loop; Fable only splits and reports** (§1) | One long Fable session driving workers through custom tools: more tokens, and the model makes the judgement |
| D2 | Code location | **`tools/orchestrate/`, its own uv project** | `app/api/src/yggdress_app/orchestration/`: shares app deps, and the app gains an SDK dependency |
| D3 | Limits | **$3 / 60 turns / 45 min per attempt; $15 / 3 h per run; 2 send-backs**, plus a Console workspace limit you set | Your numbers. Phase 2 measures the real ones |
| D4 | Worktree location | **`%LOCALAPPDATA%\yggdras\worktrees`** (outside OneDrive and the repo) | `.claude/worktrees/` (git-ignored, but OneDrive syncs it, and the `.claude/**` path hooks may treat files there as protected; unverified) |
| D5 | Plan approval | **You approve every plan before workers start** | Auto-start: faster, against principle 4 |
| D6 | Auth for workers | **An API key on a workspace with a spend limit** (`ANTHROPIC_API_KEY`) | Your claude.ai login: the SDK overview says third-party developers may not use claude.ai login "unless previously approved". It is unclear whether that covers your own local use, so **I need your call** |
| D7 | Dependent tasks | **Branch from the predecessor's branch (stacked)** | Branch from main and you resolve the conflicts at merge |
| D8 | Send-back | **Resume the worker's session** (cheaper, keeps what it learned) | A fresh session each attempt: cleaner context, costs more |

## 14. Facts the docs did not settle

These get checked in Phase 2 and are not assumed here:
- what `interrupt()` and `disconnect()` do to the CLI subprocess (handled by killing the
  process tree in §10);
- whether `disallowed_tools` accepts rule strings such as `Bash(git push:*)`. The design
  uses a hook instead, which the docs do cover;
- how far `max_budget_usd` can overshoot (measured in Phase 2).

Docs read 2026-11-23: code.claude.com/docs/en/agent-sdk/{overview, python, permissions,
hooks, sessions, cost-tracking, agent-loop, structured-outputs, claude-code-features,
quickstart}.
