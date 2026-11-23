# Frontend prototype — approved 2026-11-08

Historical prototype baseline. Storage and Brain ownership assumptions are superseded by [the revised Phase 1 contract](spec-phase-1-application-foundation.md); retain the visual requirements.

Build an isolated Next.js/React/TypeScript/Tailwind app in `app/web`. This spec records the user's approved plan; it does not change the private Markdown brain or Python interfaces.

## Acceptance criteria
- `/today` is the default and follows the supplied 1344×896 reference: narrow navigation, alpine panorama, dark glass panels, agenda, insights, capture, focus, goals, active work, activity, and bottom panorama.
- Dashboard, life areas (notes/graph/timeline), calendar, and settings share an accessible responsive shell.
- Capture notes/tasks/ideas/file metadata; search title/body/tags; edit notes, tags, areas, and links; show backlinks. Changes persist across reloads and update activity.
- Clearly labeled simulated Lia answers can be saved to notes. Graph supports pan/zoom and note opening. Timeline incrementally loads. Flashcards support flip, swipe/buttons/keys and final score.
- Fictional demo data only; browser-local versioned storage with reset. Failed saves retain form content. No real authentication, brain access, or model calls.
- Generate 24 consistent landscape images: four seasons × sunrise/afternoon/night × clear/rainy; optimize responsive WebP assets and record a manifest. Preserve one camera viewpoint.
- Location is opt-in; denied/unavailable location offers manual city selection with Hamburg fallback. Open-Meteo supplies weather/timezone/sunrise/sunset. Cached weather expires after two hours; offline fallback uses local season and clock. Support southern seasons, polar day/night, fixed scene and independent previews. Weather refresh 30 minutes; scene clock refresh one minute and on resume.
- Scene changes crossfade, reduced motion is respected, and cards remain readable. Missing images retain a safe fallback.
- Test storage, capture/link/search/save flows, scenes/time/weather boundaries, keyboard operation, and bounded rendering with 10,000 notes. CI checks types, tests, and production build without altering Python CI.

## Deferred
Real accounts, notifications, FastAPI/PostgreSQL operational data, and Lia integration. Markdown stays authoritative; future real-memory writes retain existing review requirements.
