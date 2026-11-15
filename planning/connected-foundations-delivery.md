# Connected local foundations — 2026-11-15

Subsequent delivery: the [local agent layer](agent-layer-verification.md) now
consumes these receivers. This report records the earlier receiving-only stage.

The six receiving-side areas and Chat destination selectors are implemented and active in the shared website/Windows runtime. This completes the application-side preparation requested before agents; it does not create or connect Lia, Yggdras, specialist agents or model providers.

## Delivered scope

| Foundation | Application behavior now available |
|---|---|
| Interpreted note handoff | Durable date/context inbox for Lia, a separate future-router read/ack interface, and separately authenticated agent update commands that require a matching handoff. No mutation merely from receiving Lia's context. |
| Source lifecycle and synchronization | Ordered revisions, immutable retry identities, current source/version validation, stable source/commitment bindings with typed FKs, explicit existing-target binding without duplicates, rename/archive/restore observations, preserved goals/history, safe cancellation, quiet actionable owner review. |
| Connected graph | Optional Work connections view beside the unchanged Brain viewer; real source/task/event/goal/project/schedule/run edges, bounded neighborhoods/truncation, search, depth, completed filter, pan/zoom, keyboard selection, list alternative and source-note navigation. |
| Focus and background execution | Existing explicit atomic one-human-timer handoff remains active. Background jobs have independent state/wall elapsed time, ordered deduplicated receipts, and cancellation requests that wait for provider confirmation. No runner or automatic task completion. |
| Time meaning | Typed exact versus date-only time; all-day/review ranges and availability remain separate. Historical context creates no work. Uncertain/coarse/relative/preferences/recurrence are retained for clarification rather than guessed or coerced into appointments. |
| Reliable local/responsive clients | Persistent private local PostgreSQL, shared APIs, restored/verified app backup, preserved records/sign-in, desktop and responsive web. Explicit staged app-only upgrades preserve all original column values; normal startup does not migrate/seed. |

Chat adds independent agent/model selectors. Conversations retain the next destination; messages, requests and replies snapshot their destination. Changing selection does not change an in-flight request. Held messages still require explicit resend after a future connection. Actual model choices come from registered backend metadata; the live default has Yggdras/Lia disconnected and Provider default as the model placeholder. Synthetic test model choices are not installed as fake live models.

## Verification evidence

- Production build/types passed first in `.next-connected` and then in `.next-connected-polish`, which is now active. Future builds must use another directory.
- 119 frontend unit/component cases passed.
- All 23 distinct affected browser scenarios passed across regression and focused reruns: Notes CRUD/review/Undo, source links, Calendar/responsiveness, Brain viewer recovery/navigation, Chat storage/files/errors/selection persistence, explicit focus handoff, separated handoff-to-agent flow into Today/Calendar, conflict review, Work graph and background cancellation.
- The first broad browser pass exposed a closed dialog still waiting on a CSS animation event. Dialog portals now unmount deterministically on close; Calendar and Notes focus/restoration checks passed afterward. Another failure was a test reading a cancellation before its save completed; it now waits for the confirmed modal close and passed.
- API regression and focused suites verified all existing application cases plus new handoff, lifecycle, graph, background, Chat destination, concurrency, receipt and upgrade cases. Two optional actual-Brain mutation integration cases remained skipped. The broad run had 132 passing cases and two fixture/load steps limited by the interactive ten-second SQL bound; bulk test seeding/cleanup now have their own local bound and both reruns passed. Production request limits were not increased.
- New receiving/selection suite passed 15 cases, including 10,000-task graph bounds, concurrent duplicate deliveries, API restart persistence, goal protection and explicit manual-target review. Final receipt/review tests also verified canonical JSONB round-trip replay and read-only review snapshots. Upgrade comparison/maintenance tests passed three cases.
- The actual app upgrade restored and verified a full app-only backup, migrated that isolated copy, compared all original column values, then applied migrations 007/008 to the exact owned app cluster. Existing values remained identical. New defaulted routing fields did not alter old message contents or states; held messages were not replayed.
- Live read-only checks returned 82 real Notes and the 82-node Brain graph, loaded Work connections and Chat metadata, verified private endpoints remain blocked by the browser proxy, and confirmed actual agent/model receiver connections are disabled. No Brain mutations occurred.
- The existing native Windows executable opened the upgraded Today interface successfully. Its paths, personal sign-in, profile and shared runtime were preserved; no separate desktop database or website was introduced.
- Final visual inspection led to a separate verified frontend refinement: Work graph fits the selected neighborhood and keeps phone labels readable; dense labels appear on selection. Graph/Chat/source-flow checks passed again, and the Chat capture now waits for the selected model to be saved. Background cancellation failure remains visible inside the dialog and its preserved request can be retried; the injected failure/retry browser check passed. The final build switch also passed restored-backup and original-value comparisons.

Private evidence: `app/api/runtime/connected-*`. The verified backup and private service configuration remain under the user's LocalAppData/Yggdras. GitHub checks were prepared locally; no remote CI/deployment is claimed.

## Main implementation files

- API: `handoffs.py`, `workflow.py`, `background.py`, `work_graph.py`, `chat_catalog.py`, receiving/auth helpers, Chat routes, runtime grants, `local_upgrade.py` and `local_runtime.py`.
- Database: additive application migrations `007_connected_receivers.sql`, `008_chat_choices.sql`; no Brain DDL.
- Interface: `workflow-review.tsx`, `background-runs.tsx`, `work-graph.tsx`; shared header/Today/Brain graph controls; Chat selectors/types/styles; owner-only proxy allowlist. Shared dialog close cleanup was corrected.
- Tests: `test_connected_receivers.py`, `test_chat_choices.py`, `test_local_upgrade.py`, disposable fixture grants/setup, `e2e/connected.spec.ts` and affected regression tests.
- Contracts: `requirements/contracts/connected-receivers-v1.md` and six exported JSON schemas under `requirements/contracts/schemas`.

## Explicit boundaries for the next phase

Connecting real automatic note-save handoffs requires Claude's actual Lia producer and stable identity agreement. Yggdras dispatch, specialist agents and model calls come afterward. Whole-note Brain archive/restore HTTP writes are still unavailable; only application-side lifecycle observations/reconciliation are ready. No memory/retrieval/semantic graph logic, energy thresholds, scheduling algorithms, live notifications, deployment or native mobile were added.

The Windows host is still a workspace-linked personal build; keep the checkout/local tools and active build. Reload an already-open web/desktop view to load the new interface. Standalone installation, signing, automatic native updates, remote device setup, mobile and voice are later work.
