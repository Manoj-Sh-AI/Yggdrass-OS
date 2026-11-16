# Routine Execution Card — approved first UI slice

Historical first-slice contract. [Revised Phase 1](spec-phase-1-application-foundation.md) replaces browser-local routine persistence with application PostgreSQL; card behavior and fixed-goal invariants remain applicable.

Authorization: Manoj, 2026-11-08. Implements the approved roadmap's first independently testable UI task. Depends on `application-architecture-v1.md`.

## Behavior and acceptance criteria

1. Today shows one fictional routine with an original goal, scheduled calendar date/window/timezone and expected duration.
2. The definition is read-only and separate from execution. Every transition preserves it exactly.
3. Start changes Ready → In progress and records a start timestamp once. Repeated Start cannot replace that timestamp.
4. After Start, a user may save a whole-number progress percentage from 0 through 100. The input is an explicit self-report; time passing never changes progress. Corrections within this range are allowed and retained in progress history.
5. Complete is an explicit declaration that the goal was met. It records completion, reports 100%, and enters a terminal Completed state. Saving 100% alone does not implicitly complete the routine. Completion never rewrites or shrinks the goal or expected duration.
6. Before Start, progress/completion are unavailable; after completion, execution controls are replaced with a completion summary. Individual reopen/correction behavior is deferred.
7. Started, saved-progress and completed states survive a browser reload and page navigation. Existing demo data is preserved when the new store is introduced.
8. Storage failure retains the last saved execution and the unsaved progress draft, shows an actionable inline error, and permits retry. Corrupt/newer-format routine storage is not overwritten automatically.
9. The controlled card accepts data and action callbacks, so future weekly/mobile views can use it without importing storage, Today state, or memory APIs. It follows existing panels, tokens, buttons, responsive layouts and keyboard focus conventions.
10. Domain/storage tests, server-rendered component tests and browser interaction tests verify these behaviors, including narrow layouts and unchanged goals after reload.

## Prototype conventions, not production scheduling policy

- One synthetic reading routine is initialized on the first visit. It is a sample occurrence, not an auto-generated daily routine. Its original date/window remain visible on subsequent days.
- Percentage is a UI progress convention, not objective volume or measured elapsed time. Expected duration is an estimate, not a timer or completion threshold.
- Actions use the device's current timestamp, displayed in the occurrence's saved timezone. No lateness score, rescheduling, reminders, adaptation, or goal adjustment occurs.
- A separate `yggdras.app.routines.v1` browser key stores application-only execution data. Reset demo also resets this fictional application record; no real memory is touched.
- Cross-device synchronization, multi-tab conflict resolution, automatic recurrence, user-authored routine definitions and production APIs remain deferred.
