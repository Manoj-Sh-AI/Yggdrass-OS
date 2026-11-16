# D42 — Application-owned shared planning

2026-11-09. Implements the user's Phase 2 authorization.

Morchitask is reference-only: no current tracked license or package reuse grant at dd334ea30e2173a5075954fb8abb0647ccb0e80b. Public visibility does not authorize copying. Original implementation within the existing stack trades speed of wholesale copying for lawful reuse and architectural consistency. No external application source is imported.

Extend app.tasks additively; keep the existing sample routine intact. Recurring occurrences are tasks with a unique (template, local date), not a second task inventory. Separate execution blocks and session segments preserve objectives/deadlines. Explicit versioned command transactions serialize this single-user planning domain with a PostgreSQL advisory lock; request receipts protect retries. This favors integrity and simplicity over multiuser write throughput. No DDL on service startup.

Named IANA timezones; UTC instants for schedules/sessions, local dates for recurrence. Nonexistent wall times are rejected with a visible correction request; ambiguous times expose first/second occurrence selection. Generated routines use the first valid instant at/after a skipped wall time (at most a three-hour DST gap) and the earlier fold; this deterministic transport policy is disclosed, not an energy policy. Generation is bounded to the viewed date range; missed historical occurrences can be materialized by opening that range. No infinite background worker.

Series changes affect only future, unstarted, unmodified occurrences under an explicit future policy; completed/edited/past occurrences and exceptions remain. Pause series suppresses future unstarted automatic blocks without deleting tasks/history. Explicit skip records an exception. No notification delivery guarantee: eligibility computed on authenticated reads; requests/acknowledgments persist, an offline browser receives nothing. A delivery worker/retries/device permission remains a later separately approved component.

Automatic energy thresholds, timing policies, autonomous push/split/pause, health profiling and automatic rollover are unresolved and disabled. Energy/focus/sleep are optional user context only. Manual rollover adds/moves blocks, never deadlines. No Brain integration, orchestration or external calendar synchronization is added.
