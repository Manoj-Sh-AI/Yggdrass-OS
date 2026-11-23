# Kanban follow-up: research and scope

Requested 2026-11-13 after completing the open-air design pass. Rebuild the task interface around a minimalist Kanban board; keep task/calendar/routine records shared in the existing application backend, separate from Brain data. Preserve Fixed Goals, Adaptive Execution and all version/idempotency checks. No energy thresholds, agents or orchestration.

## Primary references inspected

- Kanboard: https://github.com/kanboard/kanboard and https://kanboard.org/. MIT; deliberately simple boards, column WIP limits, filtering, subtasks and due dates. PHP backend is not a fit to import into this stack. Reuse product ideas, not a second task server.
- PLANKA: https://github.com/plankanban/planka. Boards/cards, detail panels, due dates, timers and realtime updates. Current source uses fair-code licences, not an unrestricted MIT licence. Do not copy its source into Yggdress under an assumed permission. Useful interaction reference only.
- dnd-kit: https://github.com/clauderic/dnd-kit. MIT toolkit; current React API supports controlled sortable lists, cross-list movement and cancellation. Its current API differs from older `@dnd-kit/core` examples. Check exact versions and use keyboard/touch alternatives before selecting a dependency; nothing installed yet.
- Existing Morchitask audit in `planning/phase-2-planning.md`: no established source reuse licence at the inspected commit. No code copied.

## Existing assets to preserve

Tasks already have `todo`, `in_progress`, `paused`, `completed`, `skipped`, objectives, due dates, priorities, tags, estimates, goal/project/parent/routine references, versions, scheduling information and time tracking. Shared task sheet, authenticated commands and Calendar already exist. The current task UI is a filtered list, not a board.

## Proposed smallest board slice

Display the existing task states as columns rather than introducing competing workflow state or another database. Reuse current filters, create/detail sheet, schedules, progress and authoritative commands. Keep card text concise; put description, relationships, execution/history and date controls in the existing detail sheet. Offer an explicit keyboard-accessible move/action control alongside pointer/touch interactions. A failed move rolls back visibly; a stale version asks for refresh without losing the draft.

Before wiring moves, inspect and document the existing command semantics: moving a visual card must not silently start a timer, change an objective, skip an occurrence or invent a reopen operation. If the supported command set cannot represent a requested move, show a supported action or leave that move unavailable rather than writing the database directly.

Defer custom workflow columns, WIP limits, automation, multi-user realtime, attachments/comments, and advanced reporting until their value and data contracts are agreed. These are researched possibilities, not newly approved requirements.

User decision: ask before starting a timer when moving a card into In progress. Use the existing execution command only after that confirmation; cancel leaves the card and timer unchanged. Existing paused tasks use the existing resume operation, with the same explicit timing confirmation. The service already supports reopen; because it resets progress, an explicit acknowledgement is required before invoking it from a board move. No new scheduling algorithm is needed.

Implementation slice: imported the published MIT `@dnd-kit/react` 0.5.3 package (React 18/19 peers), rather than copying an application repository. Pointer/keyboard drag handles and native move menus use one movement policy. Cards are grouped by existing execution state, sorted by the existing task filters, with 40 cards rendered per column initially. Within-column manual ranking/custom columns are not introduced. The existing list remains available and remembers the view choice.

Dependency check: registry audit reported the four existing development-tool findings (`@vitest/mocker`, `sharp`, `tinypool`, `vitest`); no dnd-kit package was listed. No forced, unrelated major upgrade was applied. The package's MIT notice is preserved in the public licence folder.
