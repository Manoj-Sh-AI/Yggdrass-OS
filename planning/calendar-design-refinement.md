# Calendar visual refinement — 2026-11-14

## Scope

Refine Calendar presentation within the existing nature/smoked-glass design. Preserve the shared task/calendar records, scheduling rules, focus behavior, and existing day/week/month/agenda workflows. No Brain, agent, or connected-workspace schema changes belong to this pass.

## Presentation

- One calendar surface contains the period heading, navigation, view selector, and grid. A quieter utility row contains date jumping, the optional scheduling rail, and timezone selection.
- Month/year typography, current-day markers, selected dates, grid lines, and event colours establish a consistent hierarchy.
- Week/day keep their existing 56px/hour geometry for drag, resize, and keyboard scheduling; only presentation changes.
- Desktop month cells show compact event previews and reveal a “View all” action whenever events or deadlines exceed their display limit. This also corrects the previous case where four events could hide the fourth without an overflow action.
- Phone month cells show the date and item count. The existing labelled day button opens the full day; individual event text is not squeezed into narrow columns.
- Styling is scoped to Calendar, with reduced-transparency and forced-colour treatments. Existing reduced-motion behavior remains in effect.

## Verification

- Production build and TypeScript passed.
- Seven production-browser tests passed against disposable application data: populated layouts across 320px, 390px, 820px, and 1344px; all calendar views; keyboard/date navigation; event opening; transparency preference; scheduling, drag, resize, split, completion, recurring routines, conflicts, failed/stale saves, and rail scheduling.
- Populated preview screenshots are synthetic. Real application captures use the separate read-only `capture-calendar-design.cjs` script.
- The design test removes its own sample events so it cannot obstruct subsequent drag targets.

## Local rollout

The previous preview launcher rebuilds its disposable database from every source migration. To keep the already-staged connected-workspace migration inactive, the visual rollout instead restored a full verified snapshot of the active application schema and records, retaining only `001_application.sql` and `002_planning.sql`. Backup data and schema were checked by an isolated restore. Runtime access uses a separate restricted role; Brain access remains through the existing server-side proxy.

Private backup/launcher files and screenshots are ignored under `app/api/runtime`. The active local frontend uses `.next-verify`; do not rebuild that directory while it is serving. Normal `.next` builds remain separate. The original local address and password are retained.

Runtime update, 2026-11-15: the later Notes-to-work bridge rollout retained this Calendar design and activated application migrations 003/004. The active build is now `.next-note-work`; `.next-verify` is no longer the serving directory. See `planning/note-work-bridge.md` for current verification and rollout details.
