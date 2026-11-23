# Temporal agent execution v1

Owner authorization, 2026-11-15: integrate the Temporal AI Agent API/workflow
pattern end to end. Preserve the existing interface, records, four agent roles,
model choices, checked writes and Lia's engine. No paid development calls.

## Acceptance criteria

1. Existing Chat submission and Notes observations durably start one execution per
   application run. Duplicate dispatch cannot create duplicate executions. Held
   messages and pre-activation requests remain excluded.
2. Temporal coordinates model/tool steps, waiting, approvals and cancellation.
   Existing application specialist logic, budgets and permissions remain shared.
   Nondeterministic calls happen in activities, never workflow code.
3. Completed activity results survive worker restarts. An ambiguous interrupted
   paid call is not automatically repeated. Read/delivery/checked command retries
   retain stable identities and existing receipt/version checks.
4. Existing review UI/API applies the exact approved payload through the existing
   transaction. Approval can resume a waiting execution. Cancellation or source
   edits prevent subsequent steps and proposals; in-flight remote calls cannot
   be unsent.
5. Owner-authenticated execution list/detail/cancel APIs expose ordered steps,
   state, timing and sanitized errors. Credentials, attachments and full prompts
   never appear in public execution metadata. Browser access keeps CSRF/session
   checks; private receivers remain private.
6. New requests wake dispatch immediately. Reconciliation still discovers queued
   work after a restart or missed wake. Timings are measured using synthetic
   models; no unmeasured provider-speed claim is made.
7. Local Windows startup manages persistent, loopback-only Temporal execution
   storage separately from both application records and Brain data. An unavailable
   Temporal service leaves application CRUD usable and queued work durable; it
   must not silently switch the same jobs to a second executor.
8. Disposable PostgreSQL + real local Temporal tests cover submission, duplicate
   dispatch, restart/replay, approval, stale source, cancellation, note handoff,
   sanitized failures and no paid-call repetition. Existing app tests still pass.

Not included: deployment, notifications/calls, new agents, new providers, memory
engine changes, Brain writes from Chat, or an interface redesign. Streaming
provider tokens is a separate transport change, not a prerequisite for this API
integration. Existing replies remain compatible.
