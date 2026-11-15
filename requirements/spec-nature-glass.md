# Nature-inspired accessible glass presentation

Authorized by Manoj, 2026-11-13: apply a fresh, open, nature-inspired glass aesthetic throughout the existing website, using the supplied Axess Lab article as a reference. This is presentation work; preserve navigation, layouts, CRUD, real data connections and Lia's ownership of memory/relationships.

## Direction

Alpine mist and clear water: existing landscapes become more visible between frosted surfaces, with deep fir foundations, sage/mint accents, gentle daylight highlights, rounded edges and clear spacing. Glass is a material hierarchy rather than an animated decoration. Keep dark appearance and automatic location/time/season/weather selection; do not force the user's scene to daylight.

## Acceptance

- Shared tokens for palette, glass fills, borders, highlights, shadows, radius and motion; consistent shell, Today, Dashboard, life areas, Notes, Calendar, Tasks, Settings, dialogs and graph presentation.
- Content remains readable over light and dark scenery. Verify primary/secondary text against worst-case glass backgrounds; target at least 4.5:1 for ordinary text and 3:1 for essential non-text cues. Preserve clear focus, selected states and non-colour labels.
- Stronger, calm reading surfaces for the notebook and dense planning content; no layout or editor-behaviour redesign. Avoid nested blur, parallax and continuous decorative motion. Keep blur modest and lower on mobile.
- Settings offers persisted Reduce transparency. Respect OS reduced transparency where supported, reduced motion, forced colours and lack of backdrop-filter support. Manual reduction remains useful when the system media query is unsupported.
- Reflect accessibility preferences in the embedded graph without changing its data, layout/relationship algorithms or source files. Reuse existing presentation adapter only.
- No new dependencies, data migrations, Brain writes or memory-engine changes.
- Verify desktop/mobile layouts and interaction regressions, reduction persistence, keyboard focus and contrast on bright/dark backgrounds; inspect screenshots of Today, Notes, Calendar, Settings and Graph. Preserve preview records and keep the existing local sign-in password during the refresh.

Reference: https://axesslab.com/glassmorphism-meets-accessibility-can-frosted-glass-be-inclusive/
