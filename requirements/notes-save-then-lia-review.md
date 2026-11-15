# Notes: direct save, followed by Lia review

User clarification on 2026-11-12. This supersedes the earlier voice interpretation that a manual editor Save must wait for a Claude-backed write request.

## Confirmed interaction

1. The user opens real PostgreSQL-backed notes in the existing application, including on a phone.
2. The user edits and explicitly saves. The application backend persists that manual change through the approved Brain data interface; Save must not wait for Claude reasoning.
3. Only after a successful commit does the saved change trigger a separate Lia review.
4. Lia reads the committed data and handles meaning, placement and relationship reasoning using Claude's existing implementation. The application must not duplicate those algorithms.
5. The editor reports normal database-save success/failure. Lia review runs silently: no routine pending/completed popups or messages. Surface a conflict when the user must resolve it. A review failure must not erase or mislabel the already saved manual change; operational review state must remain observable to the backend without routine user interruptions.
6. Existing confirmation rules for changes/removals remain the baseline. This clarification does not authorize Lia to silently replace other user facts, perform irreversible operations, or overwrite newer edits made while review was running.
7. Every successfully committed manual change should trigger review for supported connections. Finding no new connection is a valid successful outcome: the user's change remains saved unchanged. Do not require a relationship to exist as a precondition for saving the manual edit or invent a link solely to satisfy the review.

Feedback clarification from Manoj: stay silent unless there is a conflict. The saved edit is retained whether or not Lia finds any new connections. The user believes a trigger may already exist; treat that as something to verify in implementation, not proof of an operational automatic review service.

Explicit trigger confirmation from Manoj: **every successful Save of a manual change automatically starts Lia's background review**. No extra Run Lia action, opt-in per note or filter restricting review to selected types of edits. Review success and a no-new-connections outcome are silent; conflicts requiring the user's input are surfaced. This decision is settled and must not be re-asked. Trigger delivery must be tied to the successful commit and deduplicated so a network retry does not create repeated independent review work.

## Ownership and unresolved engineering contracts

- PostgreSQL owns saved Brain notes and relationships. Application records and event/job state remain separately owned; the browser has no database credentials.
- The user is handling removal of intermediate Markdown files and backups. Do not add a new file-based persistence path in the application or independently rewrite Lia's memory engine.
- Preserve the recovered create/add/replace/remove/archive/link/unlink/restore behavior unless a specific rule is explicitly changed. Reconcile those rules with the editor's explicit Save/Confirm actions; do not introduce an extra model wait into the initial save.
- The existing inspected service does not yet establish a durable save-event → Lia-review contract. Trigger delivery, operation/version identity, deduplication, safe retries, restart recovery and authoritative completion must be agreed/verified with that service before claiming automatic review works.
- A review must be tied to the committed version and revalidate before applying subsequent changes. The original user edit is not a model-generated replacement.
- Existing migration readiness and source-mode requirements still need verification before personal-data writes; this clarification is not evidence that the running server's write gate has changed.

Scope remains Notes integration and verification first. Supabase, tasks, Calendar and a general-purpose orchestrator are later work. No code, configuration or real data was changed while recording this clarification.
