# Yggdress application service

FastAPI/psycopg backend for one owner. Application SQL owns only the `app` schema;
the Notes HTTP proxy connects to the existing Brain API. A verified shared local
database may contain both `app` and `brain`, with separate roles and schema ownership.
The application runtime and migrator cannot read or modify Brain tables.

The approved local runtime now also runs the [application agent layer](../../planning/agent-layer-verification.md).
Its Task/Calendar tools use this application's database; a separate process calls
the existing Lia reader in her own environment. That process may read her static
skills and Brain rows, without importing or rebuilding the memory engine inside
this service. Chat routes, saved-note observations, approvals and provider calls
follow the [application agents contract](../../requirements/contracts/application-agents-v1.md).
Private provider credentials stay server-side. No paid inference is used by tests.

## Private local setup

Install Python 3.12+, uv and PostgreSQL. From this directory run `uv sync --locked`.
Initial provisioning uses an application-only database with distinct migration and
runtime roles. Existing local databases can be consolidated explicitly using
[the shared-database procedure](../../planning/shared-postgresql.md). Do not merely
point an existing runtime at Brain using its owner credentials. Never use a
superuser as a service runtime role.

Create the database/roles through your local PostgreSQL administration tooling. Choose credentials privately, using the tool's password prompt; never put them in a committed script or terminal command. The migration role owns the application database/schema; the runtime role is NOSUPERUSER, NOCREATEDB, NOCREATEROLE, NOINHERIT, owns no objects and has no Brain grants. Revoke PUBLIC database CONNECT and public-schema CREATE, then grant database CONNECT to those two roles.

Create `runtime/` (ignored). Run `uv run python -m yggdress_app.cli password --output runtime/password.env`. This prompts twice and writes a salted scrypt hash without printing it. Copy the complete quoted hash entry into an ignored `runtime/application.env` together with private values for the names in `.env.example`; single quotes preserve the hash's dollar separators. `YGGDRESS_ORIGIN` is the exact frontend origin without a trailing slash. `YGGDRESS_LOCAL_HTTP=1` is permitted only for loopback HTTP development; HTTPS requires Secure cookies. `YGGDRESS_BRAIN_MODE` is `mock` or `unavailable`; real mode is rejected until Claude's approved contract exists.

Apply migrations explicitly using the separate migration connection:

```
uv run --env-file runtime/application.env python -m yggdress_app.cli migrate
```

Then grant the runtime role only these privileges in the application database (replace the non-secret role identifier with your chosen runtime role):

```sql
GRANT USAGE ON SCHEMA app TO yggdress_app_runtime;
GRANT SELECT, INSERT, DELETE ON app.sessions TO yggdress_app_runtime;
GRANT SELECT, UPDATE ON app.login_guard TO yggdress_app_runtime;
GRANT SELECT, INSERT ON app.routines, app.routine_progress, app.tasks TO yggdress_app_runtime;
GRANT UPDATE (status, progress, started_at, completed_at, updated_at)
  ON app.routines TO yggdress_app_runtime;
GRANT UPDATE (done, updated_at) ON app.tasks TO yggdress_app_runtime;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA app TO yggdress_app_runtime;
```

The runtime role cannot change routine goals/metadata, delete execution history, create tables or run migrations. Remove migration credentials from the service environment after setup. Start the service with `uv run --env-file runtime/application.env python -m yggdress_app.cli serve`. It binds loopback, default port 8100. Configure the frontend's server-only API URL and exact origin separately. No personal password has been chosen by the implementation.

## Application migration and APIs

`migrations/001_application.sql` creates only `app.schema_migrations`, `app.sessions`, `app.login_guard`, `app.routines`, `app.routine_progress`, `app.tasks`. Checksums and an advisory transaction lock protect explicit migration runs. No Brain notes, shelves, changes/history or relationships tables exist here. Task note references are nullable opaque identifiers, not cross-schema foreign keys.

`/v1/auth/login|session|logout` manages one owner's opaque 8-hour session. Password rotation invalidates existing sessions. Login has a five-failure/15-minute lock, with no insecure recovery endpoint. Cookies are HttpOnly/SameSite Strict; unsafe requests require an exact Origin and session CSRF token. Responses are not cached and validation errors do not echo supplied secrets.

`/v1/application/tasks` captures/lists tasks; PATCH `tasks/{id}` changes completion only. `/v1/application/routine` loads one synthetic occurrence; POST `routine/actions` accepts start, reported percentage or complete. Transactions serialize execution commands and preserve definitions. Progress is self-reported; there are no timers or energy rules.

Authenticated `/v1/brain/tree|notes|notes/{id}` and mutation endpoints delegate only to the Brain port. Its mock CRUD/token/delete-preview behavior is an acceptance simulator, not Lia's implementation. There is no application-owned hidden note history and no retained mock copy after intentional deletion. A 409 requires explicit reload; previews expire after five minutes. A service restart resets synthetic notes. `unavailable` mode proves that PostgreSQL tasks/routines remain independent.

## Verify without personal data

`uv run pytest` starts a temporary local PostgreSQL cluster with a unique synthetic database and restricted runtime role. It does not use `YGGDRESS_DATABASE_URL`. PostgreSQL `initdb`/`pg_ctl` must be on PATH (Windows PostgreSQL 18 installation is also detected). CI uses a dedicated test-only service. An optional private `YGGDRESS_TEST_ADMIN_URL` must name a database starting `yggdress_test`; the fixture creates and removes its own unique database and role there.

Run `uv run ruff check src tests scripts` and `uv run ruff format --check src tests scripts`. Frontend production browser tests use `npm run test:e2e` from `app/web` and the same isolated database fixture.

## Explicit unresolved contracts

PR #44 now supplies the approved Notes HTTP read/fact-write contract. Notes uses that contract; global mock DTOs remain scaffolding for other pages. No real write, backup, migration or memory algorithm is claimed complete. Full-note metadata editing and distributed preview storage remain outside this slice.

Phase 2 now supplies application Calendar/scheduling, recurrence/DST handling, task reopen, version conflicts and execution tracking; its current contract is documented below. Retention, notification delivery, workers, agents and orchestration remain future work. Hosting, TLS/private networking, production role provisioning, password recovery/rotation operations and release review remain deployment dependencies. No public deployment is enabled by default.

## Phase 2 planning

Read [the integration report](../web/docs/phase-2-planning.md). Explicitly apply additive migration `002_planning.sql` using the existing migration CLI and **the separate application migration role**, after reviewing/backing up real application records. Do not use Brain credentials. No real database migration has been executed by the implementation.

Alongside the Phase 1 grants, the application runtime role needs:

```sql
GRANT UPDATE ON app.tasks TO yggdress_app_runtime;
GRANT SELECT, INSERT, UPDATE ON app.planning_goals, app.projects,
  app.routine_templates, app.calendar_events, app.execution_blocks,
  app.execution_sessions, app.daily_plans, app.reminder_requests
  TO yggdress_app_runtime;
GRANT SELECT, INSERT, DELETE ON app.task_dependencies TO yggdress_app_runtime;
GRANT SELECT, INSERT ON app.routine_exceptions, app.task_history,
  app.planning_commands TO yggdress_app_runtime;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA app TO yggdress_app_runtime;
```

These permissions allow explicit task edits. The legacy sample routine goal and progress history retain their original restricted grants. Runtime still owns no objects, cannot migrate/create tables, and cannot delete execution sessions, task history or request receipts. New task history is append-only to runtime. No application database is a substitute for Brain storage.

GET `/v1/application/planning` takes named timezone/start/end query parameters. POST `planning/commands` uses a UUID retry key and explicit operation, entity ID/version and validated data. Both require the existing single-user session; writes require Origin and CSRF. Desktop/mobile interfaces can use the same service. Legacy task endpoints share this inventory and execution logic; current UI completion also sends a version.

Routine materialization runs deterministically on authenticated refresh over a bounded range. Reminder readiness/acknowledgments persist; no timer/LLM worker or outbound delivery exists. Production needs separately reviewed worker/delivery/retention operations. `npm run preview` remains a temporary synthetic fixture, distinct from a privately configured persistent application DB.

## Notes → Brain API

Set `BRAIN_SERVER_URL` (default `http://localhost:8100`), `BRAIN_API_USER`, and `BRAIN_API_PASSWORD` in the **application backend's private environment**. Do not set these in `app/web` or use `NEXT_PUBLIC_` variables. The authenticated Next proxy forwards the application cookie and CSRF token; FastAPI attaches Basic Auth on every Brain HTTP request. Redirects are refused. Missing configuration or failed reads show an error without substituting mock notes.

Run the application service on a different port, e.g. `uv run --env-file runtime/application.env python -m yggdress_app.cli serve --port 8101`, and set the frontend's server-only `YGGDRESS_API_URL=http://127.0.0.1:8101`. Port 8100 belongs to the separate Brain server. Keep `YGGDRAS_BRAIN_SOURCE` unchanged (Markdown).

Only `/notes` uses `/v1/notes/search`, `/items/{slug}`, `/items/{slug}/preview`, `/previews/{token}/confirm|cancel`, `/create`, and `/undo`. All require application sign-in; unsafe requests also require Origin/CSRF. Previews are session-bound, expiring process memory. Confirm executes fact calls in order, refreshes versions, stops on conflict, and reports partial completion. Add-fact is staged locally until Confirm because the upstream route has no preview. Existing metadata/non-Facts edits are unsupported and rejected explicitly. Native rich blocks remain browser recovery/export data; Brain receives full Markdown on create and fact operations on updates.

Keep `YGGDRESS_BRAIN_MODE` at its existing `mock`/`unavailable` value: it selects the older global port, while this Notes-only HTTP connection is configured independently through the three backend settings above. Do not set a new `lia` mode or change `YGGDRAS_BRAIN_SOURCE`.

For the disposable local preview, `--brain-env <private-file>` loads only the three authorized Brain connection settings into the backend client. They are not passed to the Next child environment. `--restore-data runtime/<backup>.dump` preserves an existing synthetic application snapshot. No preview command migrates or writes Brain data.

Read [the Notes integration report](../web/docs/notes-brain-api.md) for verification and limitations.

## Connected-workspace foundation (staged, 2026-11-14)

Migration `003_workspace_connections.sql` adds application-only note references, task/note and event/note links, event/task associations, background-run storage, an append-only change journal and an operational-edge view. It never accesses or migrates Brain tables. The current running site's schema has **not** been changed by this architectural iteration; apply migrations explicitly only after reviewing the model, backup and deployment grants.

The existing `notes` client verifies new note attachments with a backend-authenticated GET. The app stores only an external identifier, observed title/revision and verification time. Those are cached provenance, not authoritative note content. There is no cross-service atomicity guarantee for a note archived/changed immediately after verification. Renames/reused slugs, source-instance identity and a durable Brain change feed need an explicit contract before automatic interpretation.

Authenticated, CSRF-protected POST `/v1/application/connections/commands` accepts a UUID `key`, `operation`, `entity_id` and current `version`:

- `task.link_note|unlink_note`, `event.link_note|unlink_note`: `note_slug`, optional `relation` (`source`, `context`, `result`).
- `event.link_task|unlink_task`: the event is `entity_id`; also supply `task_id` and `task_version`. Both entities receive new versions when the link changes.

Commands reuse the existing transaction lock/retry receipts. Replays return the original result without another Brain call. New attachments require a live note; unlinking only removes an app association and works offline. It never removes a note, task or event.

Read GET `/v1/application/connections/notes/{slug}`, `/tasks/{uuid}`, or `/events/{uuid}`. Context responses are bounded (`limit=1..100`, default 40), retain completed/cancelled records, and report truncation. They are application context only; the current frontend and Brain Graph do not consume them yet. Wider browsing/pagination and graph identity merging are follow-up integrations.

Additional grants for the existing non-owner runtime role:

```sql
GRANT SELECT, INSERT ON app.note_refs TO yggdress_app_runtime;
GRANT UPDATE (observed_title, observed_revision, last_verified_at)
  ON app.note_refs TO yggdress_app_runtime;
GRANT SELECT, INSERT, DELETE ON app.task_note_links, app.event_note_links,
  app.event_task_links TO yggdress_app_runtime;
GRANT SELECT ON app.workspace_changes, app.background_runs,
  app.operational_edges TO yggdress_app_runtime;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA app TO yggdress_app_runtime;
```

Runtime cannot directly insert, modify or delete journal entries. A narrowly scoped SECURITY DEFINER trigger function records application changes in the same transaction, with a fixed search path and qualified table names. It records identifiers, field names, states and references, not copied note bodies/descriptions. Its sequence is not a reliable delivery cursor or global commit order. No consumer, agent or dispatcher exists in this slice.

Background runs have a separate queued/running/terminal lifecycle and wall elapsed clock. They do not write execution sessions or contribute to human focus totals. No background runner or automatic task completion is implemented. The planned focus handoff will move the single human timer on an explicit Focus choice; that API/UI behavior is not enabled by this migration.

Trusted data-only **preview** restores now use administrator-only `pg_restore --disable-triggers` inside the existing single restore transaction. This preserves archived journal rows without creating duplicate history while reloading records. Do not grant trigger-disabling or schema ownership to runtime. A full restore into a new database remains the preferred production recovery path.

Verification: 95 backend tests passed, 2 environment-dependent cases skipped; Ruff checks passed. Coverage includes local FKs, retry/concurrency, stale versions, completion/context retention, journal rollback/permissions, separate background elapsed time, and restoring connections/history without re-emitting journal events. Synthetic fixtures and disposable PostgreSQL only; no live Brain writes.
## Temporal execution

The owner-approved Temporal execution adapter preserves the existing API and
agent roles. Setup, endpoint mapping, private local persistence and recovery
behavior are documented in [temporal-execution.md](temporal-execution.md).
