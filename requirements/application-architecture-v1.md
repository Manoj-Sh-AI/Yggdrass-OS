# Yggdress OS v1.0 — application engineering contract

Approved scope: Manoj's architecture review and implementation authorization, 2026-11-08.
Updated authority: [revised Phase 1 authorization](spec-phase-1-application-foundation.md) supersedes the original browser-only slice below. Earlier implementation records are historical, not current storage requirements.
Architectural source: `Yggdress_OS_Full_Conversation_2026-11-08.md`, 517 lines; consolidated decisions at lines 433–513. The conversation contains private information and is deliberately not copied into this public repository. Historical assistant suggestions are not additional requirements.

## Ownership and integration boundaries

| Owner | Responsibility | Boundary |
|---|---|---|
| Claude / Lia | Existing memory engine, three-level retrieval, semantic relationships, taxonomy, selective ingestion, map updates, memory experiments | Application work must not rebuild or alter these internals. |
| Application engineering | UI, backend, application persistence, APIs, integrations, specialized application agents | Communicate with memory only through a Claude-approved interface. |
| Yggdress (future) | Sole user-facing manager, hybrid parallel/sequential delegation | Build only after application subsystems and specialist agents pass independent qualification. |
| Deterministic scheduler (future) | Deadlines, dispatch and delivery independently of open clients or an active LLM | No scheduler or notifications in the approved Routine Card slice. |

One shared backend will serve web, PWA, eventual Tauri and mobile clients. Application records (routines, executions, tasks, calendar, schedules, notifications and agent operations) remain logically separate from Brain notes, folders, maps and relationships. A shared database service is permitted; shared ownership of tables is not.

Lia is on demand for memory operations. Application agents do not directly modify Brain tables, write Markdown notes, generate semantic relationships, or promote routine logs into memory. Meaningful insights may later pass through Claude's existing selective ingestion contract.

## Locked task invariants

- Fixed goals, adaptive execution: retain objectives while adapting the method or timing.
- Future routines generate daily/weekly instances with windows and expected durations.
- Future task workflows accept natural-language additions and track starts, delays, progress and completion.
- Future push/split/pause-and-reschedule policies start rule-based; protect essentials and preserve goals.
- Operational execution history belongs to application data, not long-term Brain memory.

## Approved interfaces for this slice

- A controlled, reusable React Routine Execution Card consumes a read-only routine definition, separate execution state, and an asynchronous action callback. It has no knowledge of Today routing, browser storage, Lia, or a future API.
- Application-only PostgreSQL storage owns routine execution and task records. Browser storage contains appearance/location preferences only; legacy demo data is neither imported nor used for notes.
- UI actions may change execution status, reported progress and execution timestamps/history only. They never change the definition's goal, window or expected duration.
- Failures are shown beside the card, preserve entered progress and the last saved execution, and allow retry.

## Unresolved decisions and implementation gates

These are recorded, not silently resolved:

1. **Claude contract:** stable note identifiers, CRUD operations, revision/conflict behavior, edit notifications, map synchronization, failure recovery and transport.
2. **Storage transition:** Claude exclusively owns migration of Brain to PostgreSQL and retirement of Git-based Brain storage, all Brain tables/migrations, hidden changes, version generation, deletion and OneDrive backups. Codex owns only the separate application schema. No existing memory implementation is modified by this phase.
3. **Task design:** objective units, routine exceptions, midnight/timezone/DST behavior, correction/reopen policy, concurrent edits and eventual execution history retention.
4. **Adaptation:** energy/sleep/focus inputs, push/split/pause thresholds, deadline conflicts and impossible schedules. No numeric policy is approved here.
5. **Delivery:** notification channels, acknowledgment and escalation limits, in-app call behavior, hosting/authentication strategy, database provider and current pricing.
6. **Agents:** exact commands, capabilities, approval rules, execution ordering, retry/idempotency protocols and evaluations.

FastAPI/PostgreSQL are approved for application persistence; no hosting/database provider is locked. Real Brain wire contracts require Claude's delivery and integration review. The existing local MCP interface is evidence of integration capability, not an approved production web API.

## Current implementation authorization

Phase 0 contracts plus revised Phase 1 application backend, app-only migrations, single-owner password sign-in, PostgreSQL-backed Routine Card/task capture, and mock Brain adapter UI tests. No recurrence generation, energy algorithms, agents, orchestration, notification delivery, real Brain writes or migration. Existing memory code stays unchanged.
