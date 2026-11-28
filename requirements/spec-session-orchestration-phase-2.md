# Spec: Session orchestration, Phase 2 (smallest working version)

Status: **approved by Manoj 2026-11-23.** The criteria below are
transcribed from Manoj's Phase 2 brief (2026-11-23). Nothing has been added beyond what
the approved design (`planning/session-orchestration.md`) requires.

## Summary

One orchestrator and 2 workers, run on one harmless task Manoj picks. The point is to
prove that the mechanics work before any real job runs.

## Inputs and outputs

| Input | Source | Format |
|---|---|---|
| Job text | Manoj | plain text |
| Harmless task | Manoj picks it (open question 1) | 2 independent docs-only or test-only tasks |
| API key | host environment (D6) | `ANTHROPIC_API_KEY` |

| Output | Destination | Format |
|---|---|---|
| Branches with commits | local git, one per worker | `claude/<date>-<run>-<task>` |
| Run report | run folder + reply to Manoj | per worker and total: tokens, cost, wall time, verdict, attempts |

## Behavior

As in `planning/session-orchestration.md` §§1–11, with decisions D1–D8.

## Acceptance criteria

1. Given the worker options, when the probe session tries to read a decoy `.env` with
   Read and with `cat .env`, then both calls are refused (they appear in
   `permission_denials`) and the decoy value is not in the output. No worker starts unless
   this has passed.
2. Given 2 independent tasks, when the run starts, then both worker sessions run at the
   same time, each in its own worktree and with its own scratch database. The evidence is
   overlapping start and end times, plus the two worktree paths and the two database URLs.
3. Given a task whose check is made to fail on purpose, when the worker returns, then it
   is sent back with the failing output. It then either passes, or is reported after 2
   send-backs.
4. Given a task that needs something the worker can't have, when the worker runs, then it
   returns `blocked` with `missing` filled in, and does not guess.
5. Given running workers, when `orchestrate stop <run>` is issued, then every worker
   session ends and no CLI process from the run is left (checked by process id).
6. Given a running orchestration, when the host process is killed and restarted, then the
   workflow resumes from Temporal, completed workers are not re-run, and no task has two
   sessions.
7. Given a finished run, then tokens, cost and wall time are reported per worker and in
   total, with the Console figure for the same window next to the SDK estimate.
8. Workers never push, merge or deploy. A probe `git push` from a worker is refused.

## Edge cases

| Case | Expected behavior |
|---|---|
| Plan has a task with no checks | Plan rejected before start |
| Two tasks touch the same path | Run one after the other, never in parallel |
| Worker edits a file outside `touches` | Check fails, task sent back |
| `structured_output` missing on success | Counted as a failed attempt |

## Tradeoffs (name them)

Reliability over cost. Every check runs again in code, even when the worker has already
pasted passing output.

## Out of scope

Real jobs (Phase 3), cloud sessions, a sandbox, more than 2 workers, and any UI.

## Open questions

1. Which harmless task? (Manoj picks.)
2. Is the Console spend limit set, and is `ANTHROPIC_API_KEY` available to the host
   process?
