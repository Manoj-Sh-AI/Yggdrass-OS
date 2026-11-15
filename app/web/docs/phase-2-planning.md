# Phase 2 — unified Calendar and Task Management

Authorized 2026-11-09. This milestone extends the application; Lia's Brain, schemas, retrieval and graph code remain untouched.

## Where to find it

- `/tasks`: Tasks, Routines, Goals & projects, Plan & review. Tasks has Today, Upcoming, Inbox, Backlog, All and Completed views, search, priority/group filters and sorting.
- Open a task for explicit outcome/deadline edits, progress, subtasks/dependencies, blocks, focus controls and recorded history.
- `/calendar`: day/week/month/agenda, a scheduling rail, event creation, blocks, routines, deadlines, overlaps and daily capacity. Drag a task to create a block; drag a block to move it. Its bottom edge resizes; arrow keys on that edge adjust 15 minutes. The time form is the keyboard/touch alternative.
- `/today`: the same application schedule, planning summary and generated routines, using the existing reusable Routine Execution Card. The original sample card is preserved independently.
- Plan & review: confirm availability/intention, optional energy/focus/sleep, evening reflection, estimate-versus-actual summaries, manual follow-through and reminder acknowledgments.

## Licensing and reuse audit

Morchitask: https://github.com/lucasfmujica/morchitask, inspected commit **dd334ea30e2173a5075954fb8abb0647ccb0e80b** on 2026-11-09. A shallow checkout was inspected outside this repository. No tracked LICENSE/COPYING/NOTICE, package-specific license file or package `license` field grants source reuse. Commercial redistribution, modification and SaaS reuse permissions could not be established. No source, assets or branding were copied. Attribution would not cure missing permission. The project is a product/architecture reference only.

Inspected its daily/weekly/monthly planning, capacity, date logic, task-block scheduling, routines, timers, shutdown, Google Calendar sync and reminder infrastructure. Its separate blocks, deterministic recurrence, timestamp timers and explicit capacity informed the integration plan. Its household/Google authentication, Drizzle/Neon schemas, billing, external sync and push services are incompatible with this scope and were not imported.

No new third-party dependency was added. Existing libraries used: React/React DOM MIT, Next.js MIT, Radix Dialog MIT, lucide-react ISC, psycopg LGPL-3.0-only and FastAPI MIT. Standard Python zoneinfo uses the existing system/installed timezone database (tzdata is already in the Windows dependency graph). Existing BlockNote packages/notices remain unchanged, MPL-2.0; see THIRD_PARTY_NOTICES.md. No paid service.

## Data ownership and contracts

`app/api/migrations/002_planning.sql` is additive; 001 is unchanged. Existing task IDs/records remain. Tasks gain optional due dates, exact offset-aware deadlines, fixed objective, effort/estimate, tags, priority, associations, progress/state, occurrence identity and integer version. Existing completed records are backfilled consistently. Occurrences snapshot objective/window/timezone; they are tasks, not another inventory.

New application-only tables: planning_goals, projects, routine_templates, task_dependencies, routine_exceptions, calendar_events, execution_blocks, execution_sessions, task_history, daily_plans, reminder_requests and planning_commands. Foreign keys/indexes and uniqueness protect relationships and one occurrence per template/local date. No Brain table, cross-schema FK or real Brain call.

Authenticated GET `/v1/application/planning?start=YYYY-MM-DD&end=YYYY-MM-DD&timezone=Europe%2FBerlin` returns a repeatable-read shared snapshot. The range is at most 63 days. Blocks/events/session segments and daily summaries are range-based; task inventory includes all tasks up to an explicit 10,000-task limit. Latest 1,000 history rows and 200 readiness records are loaded; full records remain in PostgreSQL. Responses are private/no-store.

POST `/v1/application/planning/commands`: `{key,op,id?,version?,data}`. `key` is a UUID retry receipt; reuse with different payload is rejected. Operations: task.create/update/execute; goal/project.create/update; routine.create/update/skip; ensure; block.create/update/remove/split; event.create/update/remove; daily.save; reminder.ack. DTOs in planning_models.py are authoritative field contracts. Browser, desktop/mobile clients and future specialized agents may call these same authenticated interfaces; no agent is required.

Edits require the read integer version. HTTP 409 preserves the client's draft; explicit refresh is needed. The single-user command domain uses an advisory transaction lock, including legacy task capture/completion. Entity edits/history/receipts are atomic. The client retains retry keys for failed requests during the session. A successful save with a failed refresh is reported distinctly. Legacy task completion accepts optional version for backwards compatibility; the current UI supplies it.

Task completion closes any active session; reported 100% progress does not imply completion. Start/resume opens a server-timestamped segment; pause closes it. Only one focus session runs at once. Selecting a block snapshots scheduled start and expected task duration, allowing initiation-delay inspection even after a later reschedule. Actual time is timestamp-derived, clipped by named-zone day boundaries in summaries. A browser crash leaves a timer running until the user pauses it; no unapproved inactivity inference is made. The optional focus interval is a browser display preference and never auto-completes or pauses work.

## Recurrence, clocks and manual adaptation

Daily every-N-day and weekly every-N-week rules with selected weekdays, start/end, preferred window, duration, priority, associated goal, area, essential and active flags. Authenticated refresh materializes the viewed range transactionally; unique keys prevent duplicate occurrences. Future ranges can be generated without an AI service. There is no always-running recurrence worker. Unvisited missed ranges materialize when opened.

One-occurrence edits set an exception marker on that task. Explicit future-series edits affect only dates after today that are untouched/unstarted; historical, completed, today and manually edited occurrences are preserved. Exceptions persist. Inactive series suppress future untouched automatic blocks without deleting tasks/history. Editing a definition can leave an already-started commitment intact by design.

Named IANA zones and UTC instants, never fixed-offset recurrence. Invalid spring wall times in manual forms return a correction error. Autumn forms expose first/second occurrence. Automatic routine starts in the spring gap advance to the next valid minute (at most three hours); autumn uses first occurrence. Dragging uses elapsed duration through DST. Calendar's compact time grid is a wall-clock axis: repeated autumn hours share a vertical position and show UTC offsets; the agenda view distinguishes chronological instants. Full duplicated-hour timeline rails remain a UI refinement. Midnight/capacity/session math uses real timezone day boundaries.

Manual Push continues a session, Pause records a stop, Split divides a block into two attached to the same task, and Reschedule changes block time only. Multiple blocks never duplicate the objective or change its deadline. Overlap lanes keep conflicting commitments selectable. No automatic task dropping, rollover, energy thresholds, health profiling or reduction of essential routines.

## Reminder readiness and delivery limits

Commands create deterministic deadline/start request records. Snapshot eligibility excludes completed/skipped tasks, cancelled blocks and obsolete schedule versions. Acknowledgment persists and retries are safe. The planner shows upcoming/overdue deadlines and unstarted windows. **No delivery worker, push notification, SMS, email or call exists.** No browser/device-offline delivery guarantee. A later delivery component needs server worker scheduling, leasing/deduplication, retries/backoff, delivery/ack distinction, device permissions and operational monitoring. No continuously running LLM.

## Proposed adaptation rules — DISABLED, awaiting approval

1. Offer, never apply, smaller sessions when the user requests a split or reports difficulty starting; user chooses durations/windows.
2. On an explicit low-energy report, show compatible lower-effort execution options without modifying commitments or essential routines.
3. On an overdue/unstarted window, ask whether to continue, split, pause or choose a new window; preserve deadline and goal.

No numeric thresholds, autonomous policies or ADHD energy profile has been chosen. Suggestion ranking, observation retention, consent and conflict priority remain design decisions for review.

## Operation and limitations

Apply migration 002 explicitly with the application migration role, after a backup/review for real application data. Never use Brain credentials. No migration runs at API startup. Runtime needs the additional grants in app/api/README.md. Tests use disposable restricted-role PostgreSQL only. The local `npm run preview` remains synthetic and temporary; ending that preview removes its fixture DB. A privately configured application DB persists independently of service/browser restarts.

There is no Google Calendar synchronization, notification delivery, offline mutation replay, background worker, agent/orchestrator, public deploy or unrelated Notes work. Completed counts reflect current completion timestamps (reopening clears current completion, while append-only task history retains the earlier event). Focus timers require explicit user pause after an interruption. History/receipt retention and paged APIs beyond the initial bounds are future operational work. Mobile layouts are browser-emulated; physical-device drag and keyboards need device QA.

## Modified files

See [the exact new/modified inventory](phase-2-files.md).

- Requirements/plan/decision: spec-phase-2-planning.md, phase-2-planning.md, D42-phase-2-shared-planning.md.
- API: migration 002; planning.py/planning_models.py; application.py (protected router and legacy task synchronization); database.py (UTC connection timezone); test fixture/grants and test_application.py updated for additive schema; new test_planning.py.
- Frontend: shared planning types/provider/UI/daily/routines; tasks route/workspace; existing Calendar enhanced; Today agenda/goals/planning integrated; shell navigation/task sheet; workspace provider composition; allowlisted proxy query forwarding; task version field; root planning stylesheet import and planning.css.
- Verification: planning.test.ts, phase2.spec.ts; Phase 1 calendar test selects the new Month tab; Playwright includes Phase 2; README and this report. Existing Notes/editor/Brain adapter code and packages remain unchanged.

The local preview updater accepts `--restore-data` only for an explicit ignored backup in `app/api/runtime`. During this milestone the previous temporary preview's task/routine records were backed up before refresh and restored into the new isolated fixture. This is a local viewing aid, not a production backup policy or a Brain restore tool.

## Verification results

- Frontend: **99 unit/component tests**, all passing; standalone type check and production webpack build pass. Includes Berlin spring/autumn rendering, preserving the second autumn fold in edit forms, midnight end exclusivity, overlap lanes, timestamp recovery and 10,000 nonoverlapping blocks.
- Application API: **47 tests**, all passing against disposable real PostgreSQL with a restricted runtime role. Covers additive migration, auth/CSRF, original sample goals, mock Brain regression, capture/schedule/move/split/remove, fixed objective/deadline preservation, occurrence idempotency and exceptions, future-series edits, Berlin DST and midnight capacity, timestamp sessions, concurrency, retry keys, combined subtask/dependency cycles, 10,000-task reads and global schedule summaries outside the current month.
- An active focus session was additionally rechecked through backend recreation, then pause/resume/complete: passed. The API restart test also verifies persistent tasks/blocks and continued session authentication.
- Production Edge browser suite: **15 scenarios passed together**, including all existing Notes/BlockNote and Phase 1 scenarios. After final date-edge refinements, **all six Phase 2 scenarios passed again**. These exercise real pointer drag from the scheduling rail, block drag, pointer and keyboard resize, split, focus/reload/pause/resume/complete, cross-page status, recurrence and one-occurrence/future edits, daily planning/overbooking/review, save failures/stale drafts, keyboard tabs and loaded mobile layouts.
- Unchanged Python regression: initial run **321 passed, one Edge viewer timeout, one known Windows stdio case deselected**. The viewer passed alone (11.60s); the stdio case was retried with a 45-second bound and passed (36.01s). Thus all **323 distinct existing cases were verified across the run and isolated retries**; a single uninterrupted all-green run is not claimed. No Brain source or test files were changed.
- API Ruff and formatting, frontend changed-file Prettier, and `git diff --check`: pass. Runtime dependency audit: **0 vulnerabilities**. No external package was added or upgraded; existing development-tool audit findings are unchanged from the Notes milestone.
- Screenshots inspected at 1344px desktop and 390px phone: `verification/phase2-calendar-desktop.png`, `phase2-tasks-desktop.png`, `phase2-calendar-phone.png` (ignored artifacts). The final mobile checks wait for loaded data and confirm no document-level horizontal overflow on Tasks, Calendar, Today and Notes. The calendar grid retains its own scroll container.
- Updated local preview at port 3000 restored the former synthetic task/routine backup into a newly migrated fixture. Sign-in succeeds and the new Tasks sidebar, scopes, filters and planning tabs are visibly present in the user's existing app tab. This preview remains temporary; private application database setup/migration is a separate operator action.

Initial browser failures (native HTML drag not firing reliably in this Edge environment and dismissing while a save was pending) were corrected with pointer handles and guarded pending dismissal; their scenarios now pass. The nonfatal upstream Starlette/httpx deprecation warning remains. No public deployment or real application/Brain migration was performed.
