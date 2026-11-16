# Signal workspace implementation

1. Keep shared navigation to Today, Calendar, Tasks, Notes, Graph and Settings. Remove mock global AI/capture paths and route search/new-note to the real Notes view.
2. Replace the Today demo composition with a real schedule and optional current task. Preserve goals and command/version guarantees.
3. Simplify page headings, put task filters and calendar scheduling behind named controls, close optional note context initially, and pause graph rotation initially.
4. Remove simulated notification settings and inaccurate mock-storage copy. Preserve all records and appearance preferences.
5. Exercise source types, unit rules and isolated browser interactions. Build separately from the running app, preserve current app data before switching, and show actual screenshots.

Research inputs: W3C cognitive guidance on focus, manageable quantity, personalization and error recovery. Nature/glass is an experience preference, not ADHD treatment. Primary clinical mindfulness studies evaluate structured therapy, not interface styling.

Source references:
- https://www.w3.org/WAI/WCAG2/supplemental/objectives/o5-user-focus/
- https://www.w3.org/WAI/WCAG2/supplemental/patterns/o5p03-manageable-quantity/
- https://www.w3.org/WAI/WCAG2/supplemental/patterns/o8p04-interface/
- https://www.w3.org/WAI/WCAG2/supplemental/objectives/o4-minimize-mistakes/

## Delivered

- Shared shell: five main destinations, Settings, real Notes search, account/sign-out. Removed the mock AI dialog, mock capture dialog, floating capture duplication, marketing footer, demo provenance banner, demo area shortcuts and first-visit scenery interruption. Location is still available in Settings and the weather control.
- Today: actual schedule and due work, an optional selected/running task, explicit timer controls, completion, preserved objective and browser-local selection across reload. No seeded routine, goal/activity cards, canned insights, quotes or scores.
- Calendar: calendar first; unscheduled-task rail and timezone controls open on request. Actual overlap warnings remain visible.
- Tasks: existing board/list and planning workflows preserved; advanced filters are disclosed on request. Fixed move cancellation focus and pending/error state surviving search updates. Routine cards show their occurrence date.
- Notes: connected editor retained; context starts closed; global search and the new-note shortcut lead to this editor. Preview/confirm, Undo and draft recovery remain.
- Graph: presentation bridge starts rotation paused; graph data, layout algorithms and memory code unchanged. Decorative snowfall removed from the application background.
- Settings: simulated notifications and inaccurate mock-storage copy removed; appearance/location controls and preference reset retained.

## Verification

- Production build passed, including TypeScript. A generated-directory Windows permission failure was resolved by packaging outside the restricted environment; no source workaround or weakened checks.
- 117 unit/component tests passed across 14 files.
- All 32 browser scenarios verified across the final runs: 30 in the full run, followed by the two drag/phone cases passing after the test waits for completed search and visible drag feedback. These checks use disposable application PostgreSQL and synthetic Brain fixtures, never real Brain writes.
- Covered sign-in/CSRF, note capture/search/edit preview/cancel/confirm/Undo, stale edits, markdown refusal/draft preservation, routine occurrences, shared calendar/task synchronization, timer confirmation/cancellation, optimistic rollback, 10,000-task bounded rendering, focus restoration, reduced motion/transparency and phone layout.
- Fresh application-only backup and original password preserved before activation. The running app uses the new production build. No real notes edited or deleted.

Live verification completed: Today, Calendar, Tasks, Notes and Graph captured at 1344×896, 820×1180 and 390×844. All 15 page/device combinations fit without horizontal document overflow. The real Notes catalogue contains 82 notes; the Brain viewer reports 82 nodes and 190 connections. Rotation was checked paused inside the actual embedded viewer. No real note edits were performed. Screenshots are private ignored files under app/api/runtime/signal-{page}-{desktop|tablet|mobile}.png.

## Principal files

New: requirements/spec-signal-workspace.md; rationale/decisions/signal-workspace.md; src/components/workspace-search.tsx; src/components/today-workspace.tsx; src/lib/today-workspace.ts; src/app/signal-workspace.css; tests/today-workspace.test.ts; e2e/signal-workspace.spec.ts; scripts/capture-signal-workspace.cjs.

Updated: shared shell/application-provider; Today export; Calendar, Tasks, task board, Notes explorer, Graph presentation and Settings; root layout; legacy Dashboard/area route entry points; Notes new-draft route; graph presentation bridge; relevant browser tests and Playwright configuration. Paths beginning with src/tests/e2e/scripts are under app/web.

No new dependency for this simplification; no backend schema/API or memory-engine changes. The previously staged dnd-kit board is included and verified. Retired demo sources/fixtures remain recoverable in source, but are not exposed as live features. Clinical benefit and individual cognitive preferences require user testing; this is not an ADHD certification.
