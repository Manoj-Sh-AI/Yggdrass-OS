# Yggdress application frontend

Next.js/React application UI with password sign-in and PostgreSQL-backed tasks/routine execution through a separate FastAPI application service. Dedicated Notes uses the authenticated Brain API, and `/graph` embeds the existing real Brain viewer below Notes in navigation. Other prototype Brain/Lia views retain their previous adapter. See [Notes integration](docs/notes-brain-api.md) and [Graph integration](docs/brain-graph.md) for their live connection requirements and limits.

## Run locally

For an isolated synthetic UI preview, install the frontend and API development dependencies, run `npm run build`, then `npm run preview` from `app/web`. Stop any older server on port 3000 first. The preview runs at `http://127.0.0.1:3000/notes` and starts its own temporary local PostgreSQL instance; it never uses your personal or Brain database. Authentication stays enabled. Temporary sign-in details are in the ignored `app/api/runtime/preview-session.json`; keep the preview process running. Stopping it removes that temporary database. This viewing workflow is separate from the private personal setup below.

Requires Node 22+, Python 3.12+, uv and a separately configured application PostgreSQL database. Follow [application service setup](../api/README.md) first. In `app/web`, run `npm ci`, supply server-only `YGGDRESS_API_URL` and the exact `YGGDRESS_ORIGIN` in an ignored `.env.local`, then `npm run dev`. Use the same origin in the backend configuration. No database credentials belong in the frontend environment. `/` redirects to `/today`; protected pages redirect to `/login` until authenticated.

The single personal password is chosen privately through the backend's interactive password command. There is no shared/demo password, signup, or password reset endpoint. The interface stays closed if the application service is absent or misconfigured.

## Persistence and boundaries

- Tasks, task descriptions/completion, routine metadata, execution history and authentication records live only in the application's PostgreSQL `app` schema.
- `RoutineExecutionCard` is controlled and reusable: read-only definition, execution state and asynchronous action callback. `TodayRoutine` supplies HTTP persistence. Start, self-reported progress and explicit completion preserve the original goal/window/duration. One synthetic occurrence is supplied; recurrence, correction/reopen and adaptation policies await approval.
- Notes UI uses BlockNote's MPL-2.0 open-source core. The dedicated Notes page uses the server-authenticated Brain API for real reads and supported fact writes; its metadata/section limits are documented in the Notes integration report. Shared prototype drawers retain the previous `BrainAdapter` and mock write port. Rich block recovery drafts remain browser-local; there are no application SQL Brain-note tables. Real history, version generation and graph maintenance remain owned by the Brain service. See the earlier [Notes milestone report](docs/notes-blocknote-milestone.md) and [third-party notices](THIRD_PARTY_NOTICES.md).
- Appearance/location use `yggdress.app.preferences.v1`; weather has its own browser cache. Old browser demo/routine keys are not imported or erased. Reset appearance preserves application and mock Brain records.
- Calendar and Tasks now share application PostgreSQL planning records; goals/projects, routines, execution sessions and daily plans also persist there. Flashcards and Lia insights remain synthetic presentation samples. Ask Brain is a labeled deterministic demo. No agents or notification delivery run.

## Phase 2 workspace

Open `/tasks` for Tasks, Routines, Goals & projects, and Plan & review. Open `/calendar` for day/week/month/agenda, task time blocks, fixed events, routines and deadlines. Today uses this same schedule. Start/pause/resume/complete focus sessions, split or reschedule blocks, and report progress without changing the task's fixed outcome or deadline. Apply application migration 002 and its runtime grants for a privately configured database; the temporary synthetic preview applies them only to its own fixture.

See [Phase 2 contracts, licensing, limitations and verification](docs/phase-2-planning.md). Morchitask is reference-only: its audited repository did not provide source reuse permission, so no Morchitask code was copied. No dependencies were added. Automatic energy adaptation, notification delivery, external calendar sync and orchestration remain disabled/unimplemented.

## Verify

Run `npm run typecheck`, `npm test`, `npm run build`, then `npm run test:e2e`. First install API test dependencies with `uv sync --locked --project app/api` from the repository root.

The browser runner creates a disposable PostgreSQL database/least-privilege runtime role, generates an ephemeral test password, starts the API and production frontend on loopback, and cleans up afterward. It never uses the configured application database. PostgreSQL tools must be installed locally; CI uses a dedicated disposable service. Test-only runtime files and screenshots are ignored. Microsoft Edge is the Windows default; set `PLAYWRIGHT_CHANNEL=chromium` with installed Playwright Chromium for Linux.

`e2e/phase1.spec.ts`, `e2e/phase2.spec.ts`, `e2e/notes.spec.ts` and `e2e/graph.spec.ts` cover the authenticated application, planning, Notes editor and graph integration. Earlier unauthenticated browser specs remain historical reference and are excluded explicitly in Playwright configuration. Existing domain, controlled-component, scenery and legacy repository unit tests still run. No current UI writes notes through the legacy browser repository.

## Scenery

24 generated scenes share a camera viewpoint, with 480/960/1920px WebP assets. `public/scenes/manifest.json` records assets. Only the current/outgoing scene loads; Settings previews six at a time. Open-Meteo weather is optional, location permission is opt-in, and seasonal/time fallback works offline. Independent manual overrides and reduced motion remain available. Inter's license is in `public/fonts/LICENSE.txt`.

## Deployment gate

No deployment was performed. Vercel's configured ignore command skips deployment by default. A separately reviewed release must explicitly supply `YGGDRESS_RELEASE_APPROVED=1`, HTTPS application/API origins, backend-only credentials and verified service/network access. These checks do not replace a hosting/security review. Root Directory remains `app/web`; the Python service needs its own hosting. Real Brain integration is still blocked regardless of deployment configuration.
