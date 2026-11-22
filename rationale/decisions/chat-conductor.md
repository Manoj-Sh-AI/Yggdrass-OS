# The chat becomes an orchestrator ("conductor")

Date: 2026-11-22. Owner choices: build on the panel's router/planner/approval lineage
(not the polling chat worker); chat default model Sonnet 5.5, Haiku only for routing and
verification; work modelled on how Claude Code runs long tasks (an orchestrator that
plans, fans work out to parallel worker threads, verifies each result, and is safe by
layers).

**Why.** Today the chat polls every 1.5 s, cannot stream, and has no plan or steps. The
panel pipeline plans but runs steps one at a time, never checks a step's result, keeps
approvals in memory, and dies with its request thread. Two engines with different models
and keys answer the same person.

**What.** One engine, `app/api/src/yggdress_app/conductor/`, one module per job:
- `state`: the single run-state schema (mode, plan of steps with dependencies and a
  pass/fail `check` each, the seven tool states, usage). Status keeps the three-value
  Task schema; a failed verification is a separate `verdict` plus reason.
- `log`: every state change is an op (`set` / `append-text`, assistant-stream's protocol)
  appended to `app.conductor_events` with a dense per-run seq. A client that closes the
  tab reconnects with "everything after seq N" and rebuilds the same state. Each append
  is validated against the schema in the same transaction, so the stored snapshot can
  never be invalid.
- Later milestones: models (streaming, by role), orchestrator (parallel DAG + retries),
  verify, policy (deny rules → classifier → human by stakes), approvals (durable),
  context (sensitive notes excluded), transport (`/v1/assistant`).

**Durability limit.** Hosted runs use threads, not Temporal: a run survives a closed tab
but not a server restart. On start-up unfinished runs are marked `interrupted`; their
logged results remain for a resume. Temporal-backed runs are a later step.

**Migration 040** (not 033) leaves room for the daily-routines branch, which already uses
015, 029, 031 and 032. Grants are listed in three places that must stay in step:
`runtime_grants.py`, `tests/postgres_fixture.py` and the table inventory in
`tests/test_application.py`.
