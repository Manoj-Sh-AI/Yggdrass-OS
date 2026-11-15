# Connected workspace data foundation

Owner direction, 2026-11-14. Tables and application integration precede agents and orchestration.

## Confirmed requirements

- Notes, Calendar, Tasks, Today and Graph represent one interconnected workspace, with canonical records and traceable connections rather than copies passed between pages.
- Clear actionable date interpretations may eventually create the appropriate item automatically; uncertain meaning must ask the owner. This approves that behavior, not a confidence threshold, parser, model prompt or scheduling policy.
- Several tasks, ideas and timelines may remain open in parallel. Only one human focus timer runs at once, and hands off automatically when the owner switches their focus task (owner's revised third option supersedes the earlier two-choice answer).
- Unattended jobs/pipelines have a separate background-run lifecycle and elapsed clock. Their elapsed time must never count as human focus time or silently complete the human task. This slice defines their data boundary, not agents or a job runner.
- Completion removes work from active lists; records, original goals, actual execution and source connections remain available in history. No automatic loss of context.
- Distinguish a deadline, fixed event interval, proposed execution window, availability, review date, recurrence and historical date. Date-only information is not an invented midnight timestamp. Duration is not a deadline.
- Existing Brain ownership and Fixed Goals, Adaptive Execution remain locked. Application work does not change Lia's engine, Brain schema, taxonomy or semantic algorithms.
- No agents, orchestration, background interpretation, unapproved energy policies or automatic Brain writes in this foundation slice.

## First implementation slice

Application-owned note references, task↔note and event↔note links, event↔task associations, an append-only transactional application change journal, and a read-only operational edge projection. Authenticate all APIs, protect mutations with CSRF and retry receipts, enforce local foreign keys, preserve versions, and validate new note links through the existing backend-only Brain reader.

Notes remain in Brain PostgreSQL. The application stores a source reference and last-observed title/revision only, not a second note body or a semantic graph. No cross-database foreign key or assumed shared transaction.

Temporal interpretation, note-save delivery and UI/graph merging require the contracts and sequence described in the accompanying architecture. Do not treat every date as a task or generate duplicate commitments on every note revision. No automatic creation is enabled by merely adding these tables.

## Acceptance

- Link one verified note to an existing task/event, link an event and a task, read connections from either side, and unlink without deleting the underlying records.
- Reject missing targets, cancelled event attachment, stale versions, conflicting retry keys and unverified note identifiers. Unlink remains possible when Brain is offline.
- Repeating a successful command returns its original receipt without another Brain call, link, version bump or journal entry.
- Task completion preserves its note/event links and execution history; changing a schedule does not change its objective or deadline.
- Journal entries commit/roll back with application writes and cannot be edited by the runtime role. No worker or broker is introduced.
- Verify constraints, rollback, restart persistence and permissions using synthetic data and isolated PostgreSQL. Stage explicit migrations; do not apply live DDL or rewrite Brain tables as an incidental server startup action.
