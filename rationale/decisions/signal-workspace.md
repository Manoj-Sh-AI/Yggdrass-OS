# Prefer working tools over prototype breadth

2026-11-14. The owner explicitly extended the minimal, mindful design direction to the whole platform.

The active workspace exposes Today, Calendar, Tasks, connected Notes and the real Brain graph. The demo Dashboard now redirects to Today; known demo area routes redirect to Notes. Their implementation and fixture data remain in source, so this presentation change deletes no user records and does not rebuild area semantics.

Global search now uses the existing authenticated Notes proxy, with no synthetic fallback or simulated AI answer. Capture entry points lead to the connected editor or existing task form. Existing preview/confirm/Undo safeguards are retained. Appearance remains browser-local; task execution remains application PostgreSQL; Brain storage and Lia algorithms remain outside this change.

Today shows actual calendar entries, due work and an optional task explicitly selected by the user or already running. A selection is only a browser-local view preference. It neither changes the task goal nor ranks, adapts or schedules work. Quiet empty states replace seeded cards. Secondary task filters, calendar scheduling and note context remain discoverable without competing with the main work.

Continuous graph rotation is opt-in in the application presentation bridge; decorative snowfall is removed. Short interaction feedback and the scenery library remain. The existing motion/transparency controls are retained. This design is informed by cognitive-accessibility guidance and requires user testing; it is not a clinical ADHD intervention or certification.

Historical browser tests that depended on the retired mock note drawer and simulated Lia answers were replaced with connected Notes coverage. Sign-in/CSRF, routine persistence, task versions, failure recovery, notebook save review and Undo remain tested. Reusable routine component/state tests remain intact.
