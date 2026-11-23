# Phase 2: unified Calendar and Task Management

Source: user-authorized Phase 2 prompt, 2026-11-09. This records that scope; it does not approve autonomous energy rules or a public release.

## Boundaries

Application-owned PostgreSQL only. Preserve authentication, Notes/BlockNote, the Brain adapter and the existing Routine Execution Card. No Brain schema, engine, data or agent changes. No orchestration, notification delivery, calls, paid integrations or autonomous scheduling.

Fixed Goals, Adaptive Execution: distinguish explicit goals, task objectives/deadlines, scheduled blocks and actual sessions. Only explicit task/goal edits change commitments. Block moves, resizing, splitting and pausing never change them.

## Acceptance criteria (from the approved prompt)

- Tasks: inbox, today, upcoming, backlog, priorities, tags, estimates/effort, goals/projects, subtasks/dependencies, search/filter/sort, editable deadlines, progress and history.
- Shared calendar: day/week/month/agenda; fixed events, flexible blocks, routines and deadlines; navigation, drag scheduling, resize, conflicts, named timezones and keyboard/manual equivalents.
- Daily/weekly routine definitions, preferred time/window, duration, priority, goal, active state and exceptions; idempotent occurrence generation; one-occurrence edits preserve the series. Future-series editing must be explicit.
- Server-timestamped start/pause/resume/complete sessions survive reload/restart; preserve and extend the reusable Routine Execution Card.
- Morning planning and evening review: capacity, planned versus actual time, unfinished work, optional energy/focus/sleep context. Manual Push/Split/Pause/Reschedule only. No inferred health policies or removal of essentials.
- Reminder eligibility and acknowledgments are scheduling records, not delivered notifications.
- Authenticated, CSRF-protected APIs; additive migration, foreign keys/indexes, transactional changes, optimistic versions and duplicate-request protection.
- Verify task capture → schedule → move (deadline unchanged) → split → execute → complete across pages, reload and backend restart. Test recurrence exceptions, Berlin DST, midnight, conflicts, unauthorized calls, interruptions and concurrent writes. Run existing application suites and report failures.
- Synthetic fixtures only; no public deployment. Document licensing, contracts, verification and remaining limitations.
