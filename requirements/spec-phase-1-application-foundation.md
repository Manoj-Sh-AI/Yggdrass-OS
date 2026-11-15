# Phase 1 — revised application UI and PostgreSQL foundation

Authorized by Manoj's revised Phase 1 instructions, 2026-11-08. This supersedes earlier application plans that assigned Brain migration to application engineering or used archive/visible History semantics. The private source conversation is not copied into the public repository.

## Ownership
Claude exclusively owns Brain migration to PostgreSQL, every Brain schema/table/migration, note storage, three-level maps, semantic relationships, retrieval, checker, hidden changes, version/conflict generation, permanent deletion and OneDrive Brain backups. Application code neither imports the existing Python memory engine nor creates, queries, or writes Brain tables. Git-based Brain storage retirement is Claude's work.

Codex owns a separate FastAPI application service, PostgreSQL `app` schema/migrations, single-owner authentication, task/routine persistence, frontend integration and verifiers. No orchestrator, agents, adaptation thresholds, scheduling algorithm or notification delivery in this phase.

## Acceptance
- All workspace pages and application/Brain adapter APIs require the owner's password-backed session. Missing configuration/backend fails closed. Public deployment is not performed and remains blocked pending security verification and real credentials.
- Passwords are configured as a salted scrypt hash through an interactive CLI. Opaque random session cookies are HttpOnly, SameSite=Strict, time-limited, revocable and Secure outside loopback development. Unsafe requests require matching Origin and a session CSRF token. Login is rate-limited. No credentials in tracked files or responses.
- Application-only PostgreSQL migrations create routines/execution/progress, tasks and authentication operational tables. No notes, folders, relationships, maps or Brain history are duplicated in these tables. Runtime uses an application-only role; migration and runtime credentials are separate configuration inputs.
- The reusable card displays goal, description, original window/duration and durable start/progress/completion. Commands change execution only and preserve the definition. Self-reported percentage and explicit completion remain prototype conventions, not energy policy.
- Task capture/completion persists through the application API. Calendar/schedule/notification service boundaries are documented; no unapproved worker or delivery behavior is implemented.
- Reuse Notes UI behind an explicit Brain adapter. Until Claude supplies contracts, authenticated synthetic mocks return the public existing shelf/area taxonomy, notes, backlinks and opaque test version tokens. UI prominently identifies mock data and integration-blocked status. No new Brain hierarchy is invented.
- Create/replace/delete go only through the adapter's write port. Mock replacement exposes updated text only; no application-owned hidden history. A delete preview and explicit confirmation are required. Stale versions reject with a reload prompt. Mock deletion retains no copy; real deletion/version/history behavior remains Claude-owned and integration-blocked.
- Application tasks/routines remain usable when the Brain port is unavailable. No automatic fallback presents synthetic Brain data as real.
- Test PostgreSQL persistence/restarts, immutable goals, authentication/CSRF/unauthorized rejection, mock tree/CRUD/preview/stale versions, service outages and schema isolation using synthetic data only.

## Implementation conventions and remaining gates
FastAPI/psycopg application service and the existing Next.js frontend. The web app proxies a fixed allowlist of backend API paths; it does not possess database credentials. One owner, no signup or account federation. No host/provider selection or public deployment. PostgreSQL may be tested in an isolated temporary local instance; never use a pre-existing personal/Brain database for tests.

The mock adapter's wire shape is provisional application scaffolding, not an imposed Claude protocol. Real note tree, note details/backlinks, version tokens, approved write/preview/confirmation operations and service authentication await Claude. Real integration, Brain backup/migration, production host/access controls and scheduling policies remain explicit dependencies.
