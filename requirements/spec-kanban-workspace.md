# Minimal Kanban task workspace

Authorized 2026-11-13 after the shared open-air design pass. Rebuild the Tasks presentation around a Kanban board, using existing application data and commands. Keep a list view and all current routine/goal/project/daily-planning functionality available. Do not add an independent task database or Brain writes.

## First slice

- Default board columns mirror existing states: To do, In progress, Paused, Done. Skipped routine occurrences stay in their existing routine workflow.
- Reuse task creation, detail sheet, title/objective, priority, estimate, due date, tags, area and goal/project links. Preserve filters and a useful list alternative.
- Pointer/touch movement and an explicit keyboard-accessible move control use the same action path. Render bounded card batches for large task counts; counts reflect all matches.
- Existing commands remain authoritative. Version conflicts, dependency guards, one-active-task checks, completion rules and idempotent retries must remain intact.
- **User decision:** moving into In progress asks before starting/resuming a timer. Confirm invokes the existing start/resume action; Cancel makes no write and leaves the card/timer unchanged.
- Moving back to To do uses existing reopen behavior. Clearly confirm its progress reset and timer closure before making that change. The original objective is unchanged.
- Pause is available for running tasks; complete uses existing validation. Do not silently invent unsupported state transitions.
- Show pending moves honestly, announce saved moves, and roll back failed ones without losing detail drafts. Preserve a saved move if only its subsequent refresh fails, with a visible refresh action.
- Keep the reviewed neutral glass/nature styling, clear card hierarchy, restrained motion, mobile scrolling, focus restoration and reduced-motion support.

## Verification

Use disposable synthetic data for mutations. Test create → detail → move → cancel/confirm → reload, timer confirmation, objective preservation, pause/resume/complete/reopen, failure/stale-version rollback, keyboard/touch access, filters and a 10,000-task bounded-render fixture. Capture the completed board for review. No agent orchestration, automatic scheduling, energy thresholds, comments/attachments, custom workflows or collaboration infrastructure in this slice.
