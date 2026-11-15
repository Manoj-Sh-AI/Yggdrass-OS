# Frontend implementation

Historical browser prototype record. Current application persistence, authentication and Brain boundaries are recorded in [revised Phase 1](phase-1-application-foundation.md).

1. Shared tokens, wireframe, typed entities and async browser repository.
2. Shared shell, Today layout, generated landscape manifest and weather selection.
3. Capture/search/note drawer and shared state updates.
4. Dashboard, area notes/graph/timeline/review, calendar, settings.
5. Meaningful tests, production build, responsive browser verification and CI.

## Wireframe
Desktop: 194px sidebar | header search + weather | greeting + right upcoming | agenda (2 units) + insights (1 unit) + capture (1 unit) | focus + goals + active work + activity | panorama.
Tablet: collapsed sidebar, two-column cards. Phone: drawer navigation, one-column cards, full-width note sheet.

## Component and data dependencies
AppProvider → asynchronous Repository → versioned browser state.
AppShell → Sidebar, Header/Search, Scenery, Capture, NoteDrawer, LiaDialog.
Pages → shared Panel/Progress/Activity/NoteList + provider selectors.
SceneryProvider → preferences/location → Open-Meteo → cached conditions → pure scene selector → responsive asset manifest.
All data-changing flows go through one provider transaction and publish only after browser persistence succeeds.

## Verified delivery — 2026-11-08

- Next.js production build and route type generation passed. Webpack is used because the local Turbopack stylesheet worker failed even outside the restricted process environment.
- 34 unit tests passed: capture/link/search/persistence/reset/failure handling, 10,000-note search, all scene assets, sun boundaries, southern seasons, stale weather, polar conditions, malformed caches, and manual overrides.
- 7 production browser tests passed: 10,000-note bounded lists/graphs; location denial and city selection; quota failure preserving drafts; missing scenery fallback; responsive screenshot capture; capture/edit/link/reload/Lia save; graph/calendar/flashcards/scenery; keyboard focus and mobile navigation.
- Inspected screenshots at 1344×896, 820×1180 and 390×844. Local screenshots are in `app/web/verification/` (ignored); the generated 24-scene contact sheet is in `app/web/public/scenes/`.
- 24 individually generated scenes, each optimized to 480, 960 and 1920px WebP (72 assets, approximately 10.7 MB total), with a manifest. Two rainy-night variants were regenerated after visual inspection to remove unwanted sunrise lighting.
- Existing Python code and private Markdown memory were not changed. Vercel root/configuration and GitHub Actions are prepared; no cloud deployment was performed.
