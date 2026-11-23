# Notes-to-work bridge — 2026-11-15

## Delivered component

Saved note → explicit canonical task/fixed event → source link → existing Calendar/Today projections → completion/history, with reverse source-note navigation.

- `connections.py`: authenticated capability, atomic create-from-note, existing link/context commands, source identity and revision checks, command replay and transactional journal correlation.
- Migration 004 records per-link source revision; migration 003 supplies the application-owned reference/link/journal foundation. No Brain tables, semantic relationships, memory engine, or agents are changed.
- Optional Notes context: create task/event using the existing forms, attach existing work, unlink, inspect completion, and identify source revisions that have changed.
- Task, Calendar and Today event details: optional linked context with source-note deep links.
- Failed saves preserve entered form data. Lost-response retries retain the request UUID across component remounts using an opaque fingerprint in session storage; note text is not stored by this retry mechanism.
- Context stays visible during refresh, avoiding a blank-panel flicker. Stale mutations expose a refresh action rather than overwriting newer data.

## Verification

- Production build and TypeScript passed in `.next-note-work`, separate from the running Calendar build. A dedicated `YGGDRESS_BUILD_DIR` option accepts only `.next` names; the earlier default `.next` folder had a Windows unlink-permission failure and was not reused.
- 119 frontend unit/component tests passed across 15 files.
- All 103 backend cases passed across the regression run and focused rerun; two environment-dependent cases skipped. Three admin-fixture cleanup statements initially timed out during parallel verification and then passed in the isolated rerun. Production query timeouts were not relaxed. Ruff passed.
- All 18 affected browser scenarios passed across the regression run and focused rerun. Covered four new bridge scenarios plus existing Notes/scheduling checks: task/event creation; Calendar/Today visibility; completion/reload/unlink; failed/lost-response retry; source-revision changes; phone layout; existing-work attachment and stale refresh; editor save previews/Undo/draft recovery; drag/resize/split/focus and recurring plans.
- Two new browser assertions were corrected to inspect the actual linked-work buttons and the accessible picker role. An unlinked item remains available in the picker by design.
- Verification uses synthetic Brain notes and disposable PostgreSQL. No real Brain note was edited or removed.

## Activation and remaining boundary

The private rollout restores a full verified snapshot of the current application database, applies migrations 003/004 explicitly to that copy, checks that existing records are unchanged, grants the restricted runtime role, and switches the frontend. Brain authentication remains server-side. Private backups/launchers/screenshots live under ignored `app/api/runtime`.

Activation completed on 2026-11-15 at the original local address and password. The full backup passed isolated restore/schema/data verification, existing application records matched after migration, and the active application has migrations 001–004. Read-only live checks passed for the new controls at desktop and phone widths: 82 real notes and the unchanged Brain viewer's 82 nodes/190 links. No live work was created and no real Brain note was edited during verification. The active frontend uses `.next-note-work`; do not rebuild that directory while it serves the app. Build future verification into another dedicated `.next-*` directory.

The automatic Leah → application path is not active. Current Brain HTTP reads/writes have no verified durable committed-change feed or typed workflow-interpretation endpoint. The required producer and reconciliation boundary is recorded in `requirements/contracts/lia-workflow-change-v1.md`; application code does not substitute its own interpreter or claim a callback guarantees every save.

Next independently testable component: bind the agreed Brain committed-change/interpretation contract to application validation using synthetic revisions, including stable commitment identity, clear/uncertain outcomes, source/target conflicts and retries. Then add the bounded operational Graph layer. Specialized agents follow independently, with Yggdras orchestration and its conversational interface afterward.
