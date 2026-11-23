# Phase 2 integration sequence

Authorized 2026-11-09. Implement and verify one slice at a time.

## A. Audit (completed)

Yggdress: Next/React shared glass shell; Calendar was a browser-seeded month grid; app.tasks persisted capture/completion only; app.routines held one fixed sample with progress history; authentication and mock-only Brain/BlockNote already work. App migration runner is explicit and checksum protected. Preserve migration 001 and all existing records.

Morchitask audited in a temporary checkout at dd334ea30e2173a5075954fb8abb0647ccb0e80b (2026-11-09). No LICENSE, COPYING, NOTICE or package license declaration found in tracked tree. No source reuse permission established, including commercial redistribution/modification/SaaS. No Morchitask source/assets copied. Product/architecture reference only. No attribution license can be fulfilled in place of missing permission.

Inspected schema, recurrence queries, calendar scheduling, timer store/hook, capacity/date/reminder modules and planning/shutdown architecture. Useful patterns: separate multiple blocks from tasks, timestamp timers, explicit daily capacity, idempotent recurrence. Incompatible parts: household/account/billing model, Drizzle/Neon data access, server actions, OAuth, external sync/push infrastructure. Do not import these. Existing React, Radix, lucide and PostgreSQL libraries suffice; Python timezone data is the only potential platform dependency.

## Component and data map before implementation

Shared authenticated planning provider → asynchronous planning HTTP API → transactional application planning service → app schema. Tasks workspace and existing Calendar both consume the same provider. Today embeds daily planning and occurrence execution through the existing Routine Execution Card. Shared task sheet, block editor, focus controls and capacity display serve all views. Notes remains independent.

Tasks workspace: header/capture → scope filters → search/sort → grouped task list → detail sheet (objective/deadline/relationships/history, blocks, execution). Secondary tabs: routines, goals/projects, daily plan/review.

Calendar: date/view/timezone toolbar → task scheduling rail + day/week time grid or month grid/agenda → shared item sheet. Mobile stacks rail/grid and offers explicit date/time controls alongside pointer interactions.

## B–G. Sequence

1. Add migration 002 extending tasks; separate goals/projects/dependencies/routine templates/occurrences/events/blocks/sessions/history/daily plans/reminder requests/idempotency. Never rewrite 001 or migrate real data automatically.
2. Shared protected commands/read API, concurrency/version checks, timezone resolver, bounded recurrence materialization and tests against disposable restricted-role PostgreSQL.
3. Task Manager, routine/goal/project controls and shared planning state. Legacy quick capture and Today completion continue using the same tasks table.
4. Enhance existing Calendar with shared records and views; pointer drag/drop/resize plus accessible form alternatives.
5. Daily planning/review and timestamp execution; extend existing routine card with optional execution controls.
6. Manual adaptation, reminder eligibility, history/summaries. Document automatic suggestions separately, disabled pending approval.
7. Unit/API/component/browser regression, DST/restart/concurrency/security, responsive screenshots and production build. Update local preview only after verification; keep it synthetic.
