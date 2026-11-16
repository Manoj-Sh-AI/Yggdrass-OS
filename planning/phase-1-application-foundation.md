# Revised Phase 1 — implementation and delivery record

Authority: [approved revised requirements](../requirements/spec-phase-1-application-foundation.md), superseding the previous browser-only Routine Card slice. [D41](../rationale/decisions/D41-phase-1-revised-boundaries.md) records ownership and tradeoffs. Historical prototype and Routine Card verification records remain historical.

## Layout and dependencies before implementation

Reuse the existing Today layout and controlled Routine Card; replace only its persistence container. Reuse Notes list/drawer/modal components; add a Brain-provided shelf sidebar on `/notes`, an integration banner and a public sign-in screen. Keep the established landscape/glass design tokens and mobile stacking.

```
Public Login → same-origin application proxy → authenticated API/session
Protected workspace layout → shared application provider
  Today → TodayRoutine → RoutineExecutionCard → routine HTTP port → app PostgreSQL
  Capture / task checklist → task API → app PostgreSQL
  Notes / search / drawer → BrainAdapter → synthetic Brain port
                                      → future Claude service (blocked)
  Scenery / Settings → browser appearance preferences + optional weather
```

The UI never receives database credentials. Brain adapters never use application SQL. Domain/card inputs remain independent of routing and transport so weekly planning and future interfaces can reuse them. Native mobile UI rendering will still need a native view; the shared backend/data commands are reusable.

## Sequence

1. Record revised ownership, acceptance criteria and explicit unavailable contracts.
2. Add separate FastAPI package and checksummed `app`-only SQL migration.
3. Add private password setup, hashed opaque sessions, Origin/CSRF checks and login throttling.
4. Implement transactional task/routine application endpoints with restricted database privileges.
5. Introduce a provisional, authenticated mock Brain port; no real engine imports or Brain database access.
6. Gate existing workspace routes behind authentication, replace runtime local note/routine storage, reuse Notes UI and add preview/confirmation/stale-version handling.
7. Verify real PostgreSQL service restarts, UI flows, failure states, responsive layout and deployment gate. Add CI alongside existing Python checks.

## Application schema and ownership

Only `app.schema_migrations`, `sessions`, `login_guard`, `routines`, `routine_progress`, `tasks` are created. No application note tables, hidden changes, Brain foreign keys or semantic relationship storage. Migration runs are explicit; server startup never migrates. A separate runtime role cannot update goal metadata, create schema objects or remove progress history.

Brain mocks are process-local, labeled and integration-blocked. They reset on service restart. Fixture replacement/delete semantics verify application behavior without implementing Lia's hidden history, conflict-version algorithm, semantic linking, checker or backup. Public existing shelf IDs are fixture labels, not a new hierarchy or live snapshot.

## Remaining approvals and dependencies

- Claude: tree/detail/backlinks, stable IDs, opaque version tokens, approved write/preview/confirm flow, service authentication/transport and error contract. Real Brain integration is blocked.
- Future calendar/schedule service: application-owned dated-item contract, recurrence/timezone/DST and conflict policies. Existing views remain synthetic samples. No scheduler, notification table/worker, delivery or agent is added.
- Task/routine semantics: new occurrences, objective units, correction/reopen, cross-client execution conflicts and retention. No energy thresholds or automated adaptation.
- Release: hosting, private connectivity/TLS, actual application database/roles, personally chosen password, operational password rotation/recovery and separate deployment review. Vercel ignores releases by default.

## Verification record

Only isolated synthetic databases were used. No existing Brain or personal database was accessed; no private transcript was copied into the public repository.

- Frontend types and production build pass. All 68 unit/component tests pass, including 7 new service-adapter tests.
- All **29 backend tests** pass, including service restarts, explicit completion versus 100% reporting, immutable goals at API/database privilege boundaries, authentication/CSRF, mock writes, deletion previews, stale tokens, unavailable Lia and private password setup/overwrite protection. The final CLI permission change also passed its targeted rerun. Dotenv loading was verified with a generated value; hash entries must remain quoted to preserve dollar separators.
- All 5 authenticated production browser scenarios pass together: private-route rejection/sign-in/out; routine execution/reload/new sign-in/failure preservation; Notes create/edit/stale reload/confirmed delete; independent application tasks during Brain outage with save rollback; demo Lia answer saving/calendar/appearance/mobile.
- Inspected desktop Today at 1344×896, phone Today at 390×844 and the sign-in screen. Verification screenshots are local/ignored under `app/web/verification/phase1-*`.
- API Ruff lint/format, existing Python lint/format, application CLI package installation/help, SQL inclusion in the built wheel, deployment-default block and `git diff --check` pass. Ignored runtime credentials are removed by the browser harness. A source scan found no credential-bearing PostgreSQL URLs in 89 publishable text files.
- One concurrent backend run received an intermittent database-unavailable response. The isolated case and subsequent complete 28-test run passed; no retries were added to hide failed writes. Third-party Starlette emits an HTTPX deprecation warning; it does not fail tests.
- The restricted existing Python run failed a local-server test and stalled. With local-server access, it passed that portion but hung in `test_the_server_speaks_mcp_over_stdio` (`app/tests/test_mcp.py:164`); the 45-second stack dump identifies the Windows asyncio/stdio wait. Running the remaining suite separately passed **322 tests, with that one test deselected**. Memory code/tests and existing CI are unchanged; the local transport check is not claimed passing.

## File groups

- `app/api/src/yggdress_app/`: application configuration, password/session security, database migration runner, application APIs and synthetic Brain port.
- `app/api/migrations/001_application.sql`: application-only schema.
- `app/api/tests/`, `scripts/browser_check.py`: disposable real PostgreSQL and authenticated production-browser harness.
- `app/web/src/lib/api.ts`, `brain-adapter.ts`, `routine-http.ts`: frontend service boundaries.
- `app/web/src/components/application-provider.tsx`, `workspace-gate.tsx`, `login.tsx`, `brain-explorer.tsx`: shared state, access gate and reused Notes composition.
- Existing Notes/capture/shell/settings/Today routine container: adapter operations, immutable goal execution and accurate persistence labels.
- Workspace route group and same-origin API proxy: protected existing routes, no URL change.
- `app/web/e2e/phase1.spec.ts`, `tests/application-adapters.test.ts`: current acceptance and adapter tests. Earlier browser-local specs are retained as historical references, explicitly excluded from the active browser contract; existing unit suites remain enabled.
- Setup READMEs, revised requirements, D41, this record and `.github/workflows/frontend.yml`: scope, private setup and application checks. Existing memory package, memory dependencies, locked memory plan and constitution are unchanged.
