# Interface feel: first responsiveness pass

2026-11-13: Manoj asked for continuing visual refinement, research into Apple design guidance, useful experience improvements and smoother everyday interactions. This is application UI work only; keep Brain operations, authentication, concurrency checks, drafts and confirmation rules unchanged.

## Research

- Community Apple Design skill, read as an independent interpretation, not official Apple tooling: https://github.com/emilkowalski/skills/blob/main/skills/apple-design/SKILL.md
- Apple primary source: Designing Fluid Interfaces, https://developer.apple.com/videos/play/wwdc2018/803/
- Apple Motion HIG: https://developer.apple.com/design/human-interface-guidelines/motion
- Apple Progress Indicators HIG: https://developer.apple.com/design/human-interface-guidelines/progress-indicators
- Installed Next.js documentation: linking-and-navigating, prefetching and lazy-loading.

Useful principles: visual feedback starts at press, committing still happens at release; never lock interactions to finish decorative animation; prioritize eliminating waits before adding motion; keep spatially consistent, short opening/closing paths; respect reduced motion and transparency. No sound, vibration, continuous ambient motion, fake speed claims, forced splash screen or new animation dependency.

## Concrete first changes

1. Let independently loaded Notes and Graph render without waiting for unrelated application task/mock-Brain startup. Keep the server-side authenticated workspace gate intact. Other pages retain their existing readiness contract.
2. Warm the existing editor's separate bundle when entering Notes, concurrently with its data read. Keep it lazy elsewhere and preload only on note hover/focus. Do not prefetch personal note bodies or cache secrets.
3. Show a quiet writing-layout placeholder during a genuine editor load, with accessible status. No artificial minimum loading time.
4. Add shared press feedback and consistent short modal/sheet entrance and exit motion, with manual and operating-system reduced-motion fallbacks. Avoid movement on text-editor internals and draggable controls.
5. Verify a deliberately delayed unrelated task read does not block Notes; verify editor, focus restoration and reduced motion against the disposable synthetic integration service. Do not infer responsiveness from screenshots alone or claim a fixed frame rate without measurements.

The open-air visual study remains independently reviewable. This pass does not apply its new theme across the real application's pages.

Verification: all 108 frontend unit/component tests pass; a separate `.next-verify` production build compiled and passed TypeScript and packaging. The normal running `.next` preview was preserved. Four focused browser checks pass across the final runs: Notes rendering while an unrelated task request remains held, press feedback/modal focus/reduced motion, stale note-open protection, and authenticated capture/search/reload. Two initial runs timed out during sign-in/initial editor setup before reaching their assertions; direct login setup and a bounded wait for the genuine editor load resolved them. No live Brain mutation was used.

Subsequent authorization: carry the reviewed Today material into Calendar, Notes and Graph before rebuilding Tasks as a Kanban workspace. Keep the notebook layout, graph behavior and task semantics intact during the visual pass. Do not confuse the separate static Today study with a deployed application theme.

Shared-material rollout: `open-air.css` now supplies neutral smoked surfaces, thin highlights, clear primary actions and a floating sidebar across the existing functional pages. Fake window controls and the simulated notification shortcut are hidden; data-source detail is folded into one disclosure. The graph's existing presentation bridge receives the same neutral palette; its data, nodes, edges and renderer are unchanged. The reviewed build was activated on local port 3000 after a private application-data backup/restore, retaining the existing password and backend-only Brain environment. Desktop and phone captures succeeded for Calendar, Notes and Graph with no horizontal page overflow; the Notes editor opens real Brain content. The earlier transient database read error did not recur in the successful captures, and no real note was edited.

Follow-up polish queued with Kanban: prevent the phone Notes title/actions from squeezing into narrow columns, let long sidebar navigation scroll, remove empty planning-feedback space and reduce the Calendar's duplicate heading padding. Main preview currently serves `.next-verify`; build the next iteration into the default `.next` directory to avoid overwriting files in use.
