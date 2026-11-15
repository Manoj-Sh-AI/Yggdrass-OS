# Windows desktop delivery — 2026-11-15

The first personal Windows build is running. Desktop and Start menu shortcuts named Yggdras point to `app/desktop/dist/Yggdras.exe`. The same web address remains available at http://127.0.0.1:3000. Existing personal sign-in is unchanged; desktop has a separate persistent browser profile.

## What was verified

- Production frontend compile/types passed in `.next-desktop`. This is now the active build; do not overwrite it while serving.
- 119 frontend unit/component tests passed.
- 120 API tests passed across the full run and targeted schema-test correction; two optional actual-Brain integration tests skipped. The full run initially had 119 passing tests and one outdated expected-table set; that expectation was extended for approved Chat/date tables and its rerun passed. API tests use disposable databases, not personal Brain data.
- 20 browser scenarios passed: calendar navigation/responsive layouts, Chat storage/edits/search/archive/export/files/failure recovery, focus handoff, graph loading/rotation/note opening/recovery, Notes list/capture/search/reload/save preview/confirm/Undo/conflicts, linked work and date-range persistence.
- Full application-only backup restored into an isolated cluster and compared by schema/data fingerprints before explicit import. Existing tables were compared after app migrations; final source auth/retry records were copied under a source freeze before switching only the verified old frontend process.
- Persistent PostgreSQL used SCRAM and private current-user storage; runtime role could not create tables. Normal startup performs no migrations, import, seed or reset.
- Owned services reused rather than duplicated. An authenticated live check read 82 real Notes and the 82-node Brain graph. No Brain writes occurred.
- Owned services and PostgreSQL stopped cleanly, restarted, and retained identical complete table/sequence/large-object fingerprints; existing application sign-in remained valid.
- Unauthenticated private runtime-control request rejected.
- Actual WebView2 native page loaded and captured; normal app window opened; a second launch reused the first window and exited successfully.
- Native host exposes no application message handler or host object; native messaging is disabled. Foreign top-level/frame navigation and arbitrary URI schemes are restricted. Microsoft SDK license ships with the binary.

Ignored evidence is under `app/api/runtime/desktop-*`; private database/credentials/profile/verified backup are under `%LOCALAPPDATA%/Yggdras`. No private configuration is included in the CI host artifact. Local verification was performed; the new GitHub Actions Windows compile job has not been run remotely in this session.

## Main files

- `app/desktop/Program.cs`, `app.manifest`, `build.ps1`, `icon.svg`, `icon.mjs`, `README.md`, `.gitignore`: native window, recovery, navigation/security, single instance, branding and reproducible host build.
- `app/api/src/yggdress_app/local_runtime.py`, `runtime_grants.py`, `tests/test_local_runtime.py`: explicit verified provisioning, persistent local services, private control, role permissions and restart test.
- `app/api/migrations/005_chat_foundation.sql`, `006_calendar_date_items.sql`, `chat.py`, `receivers.py`, `temporal.py`, related API tests and routing: prior approved Chat/time foundations included in this desktop candidate.
- `app/web/src/components/chat.tsx`, `calendar-date-form.tsx`, Calendar/Today/linked-context components, shared API/types/proxy, Chat route/styles, browser tests: same shared interface in web and desktop.
- `.github/workflows/frontend.yml`: Windows host compile and private-config-free artifact, alongside existing app checks. `app/api/pyproject.toml` makes test helper imports independent of runner working directory.
- `requirements/spec-windows-desktop.md`, `rationale/decisions/windows-desktop-host.md`, `planning/local-platform-foundations.md`: scope, tradeoffs and remaining foundations.

## Limits and remaining scope

This is a workspace-linked laptop app. Keep the checkout, Python environment, Node, PostgreSQL tools and active build in place. A self-contained installer, code signing, automatic updates, startup-at-login and native mobile have not been implemented. Home-network device access and hosting were not enabled.

At this initial desktop checkpoint, the remaining receiving areas were not yet complete. The subsequent [connected foundations delivery](connected-foundations-delivery.md) finishes and activates those application-side areas and Chat selectors. The active build is now `.next-connected-polish`; all live agent/model/routing execution remains disconnected. Lia's engine is unchanged.
