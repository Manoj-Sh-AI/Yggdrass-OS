# Temporal execution — delivery and verification

Owner-authorized local integration, verified 2026-11-15 UTC. Active frontend:
**`.next-temporal-ready`**. Application migrations **001–010**. The existing web
interface and Windows host use the same Temporal-backed application backend.

## Delivered behavior

- Existing Chat send/resend and saved-note observations feed a durable PostgreSQL
  outbox. One stable workflow identity per application run prevents duplicate
  dispatch. Held messages remain held; activation preserves the previous cutoff.
- Temporal runs the existing Yggdras, Task Manager, Calendar and Lia integration
  through shared deterministic effect generators. Model, read, skill, source
  handoff and checked commit operations are activities. Permissions, shared call
  budgets, fixed goals and human focus behavior are preserved.
- Each completed activity is replayable. Private effect receipts also preserve a
  completed result if its Temporal acknowledgement is lost. Paid model/Lia calls
  have one-attempt policies; interrupted calls with uncertain outcomes require
  explicit resend. Application transport never silently repeats those calls.
- The existing review UI uses durable workflow Updates, retaining exact-payload,
  source-version, target-version and atomic decision receipts. Conflicting reuse
  of a decision key is rejected. Waiting approval survives worker/server restart.
- Cancellation is stored before a workflow Signal is sent. It stops later steps
  and supersedes unapplied proposals. Source edits/resends still invalidate stale
  work. A terminated workflow fails closed without silently regenerating replies.
- Owner-only execution list/detail/cancel routes expose ordered steps, timings,
  sanitized failures, pending decisions and available live workflow state. Public
  traces exclude prompts, private receipts, attachment bytes and credentials.
- Writes wake the dispatcher immediately; periodic reconciliation covers missed
  wakes and restarts. Chat and background work retain separate execution queues.
  A stopped executor leaves normal application reads/CRUD available and requests
  queued. It does not silently hand the same jobs to a different executor.
- Windows startup manages a verified official Temporal CLI with private persistent
  execution storage and loopback-only listeners. The application supervisor starts
  and stops it; no cloud deployment or new desktop installer was introduced.

## Verification actually run

| Check | Result |
|---|---|
| Full backend suite | 180 passed, 2 optional cases skipped |
| Subsequent final Temporal-specific verification | 14 passed |
| Existing agent-role regression run | 31 passed |
| Frontend unit/component suite | 119 passed |
| Production candidate | Compilation, TypeScript and page generation passed |
| Real Temporal through production frontend | 2 browser cases passed |
| Existing Notes/Chat/Graph/connected-work browser regressions | 17 passed |
| Ruff | Checks and format verification passed for 74 files |
| Local upgrade | Full app backup restored/verified; staged migration and original-column comparisons passed |
| Authenticated live reads | Temporal ready, 82 real Notes, 82 Brain graph nodes, 4 agents, 4 model choices |
| Live safety/compatibility | Existing password preserved, private proxy blocked, no automatic replay; Today/Calendar/Notes/Graph/Chat readable |
| Actual Windows executable | Opened Today and completed its read-only native verifier |

The broad suite preceded the last startup/recovery refinements; the final
14-case Temporal run verifies those changes. Initial verification exposed startup
readiness and restart-timeout problems. The harness now checks executor readiness,
startup allows its bounded warmup, and abandoned sticky work has a shorter pickup
timeout. Final dedicated, browser and live checks passed. No failed check is being
presented as successful.

Tests use disposable PostgreSQL, real local Temporal and synthetic model/Lia
responses. **No paid inference calls were made.** Live verification used page/API
reads and sign-in only; there were no managed Temporal executions at that check
and no Brain mutations. Provider semantic quality and real-model latency were not
tested. Timings are measured in the execution trace, rather than inferred from the
framework choice.

Evidence is kept in ignored `app/api/runtime/temporal-*` logs/reports and the private
application backup directory. GitHub Actions now installs the checksum-verified
Linux CLI and runs the synthetic-agent browser case through Temporal; remote CI
was not triggered or claimed as passed.

## Boundaries and operational limits

Lia's original memory engine, retrieval, graph generation, effort policy and write
internals were not changed. Notes keep the existing Brain API save path. Application
execution history is separate from Brain memory. No new scheduling/energy rules,
agent roles, provider, notifications, calls, mobile app or hosting was added.

The local Temporal development server is for this local application. A hosted
release still needs production configuration, TLS/authentication, sizing and
retention. Operational history is stored privately in Temporal's local SQLite
file; canonical application data and conversations remain PostgreSQL. Future
backup procedures must preserve both stores.

Provider replies retain the existing buffered transport and browser refresh
cadence. Immediate dispatch removes an idle worker wait; this is not a measured
claim that model generation itself is faster. Detailed execution tracking is
available through the authenticated API; the interface layout is unchanged.

## Files

| Area | Created / modified |
|---|---|
| Shared role logic | `agent_effects.py`; `agent_specialists.py`, `agent_orchestrator.py`, `agent_source.py`, `agent_worker.py` |
| Temporal runtime | `temporal_agent_workflow.py`, `temporal_agent_activities.py`, `temporal_agent_service.py` |
| Data/receipts | `agent_execution_store.py`, migration `010_temporal_execution.sql`, `agent_store.py`, runtime grants/test fixtures |
| API/compatibility | `agent_api.py`, `application.py`, existing frontend backend-proxy allowlist and review timeout |
| Local lifecycle | `local_runtime.py`, `scripts/install_temporal.py`, `scripts/activate_temporal.py`, dependency manifest/lock |
| Verification/CI | `tests/test_temporal_agents.py`, schema allowlist, synthetic browser harness, `e2e/agents.spec.ts`, frontend workflow |
| Documentation | New requirements contract, execution plan, decision record, API runbook and this report; previous agent documents linked to the amendment |

Next-generated type references now point to the active production candidate.

Primary references: [Temporal AI Agent API](https://github.com/temporal-community/temporal-ai-agent/blob/main/api/main.py),
[workflow implementation](https://github.com/temporal-community/temporal-ai-agent/blob/main/workflows/agent_goal_workflow.py),
and [Temporal Python message passing](https://docs.temporal.io/develop/python/workflows/message-passing).
The project pattern informed the integration; application code and existing
authentication/write safeguards are retained.
