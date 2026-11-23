# D41 — shared application backend, exclusive Claude Brain ownership

Approved: revised Phase 1 authorization, 2026-11-08.

Put the application backend in `app/api`, independently of Claude's `app/src/yggdras` package. Application SQL names only the `app` schema. Database-backed note migration, hidden changes, semantic links, conflict token generation, intentional permanent deletion and OneDrive Brain backups belong exclusively to Claude. Earlier archive/history and application-owned Brain migration proposals are not applied to this integration.

Use FastAPI and psycopg with versioned, transactionally applied application-only SQL migrations. Keep one owner's opaque session and login throttling in application operational tables. Salted scrypt hashes are configured outside Git; sessions require Origin and CSRF verification for mutations. The Next.js frontend is a same-origin proxy/UI and never receives PostgreSQL credentials.

Reuse the controlled Routine Card with an HTTP persistence adapter. Reuse Notes UI through a labeled synthetic Brain port while real contracts are absent. Fixtures mirror the public shelf taxonomy; they are not a live Brain snapshot. Mock CRUD/version/preview behavior tests the application boundary only and is not represented as a replacement Lia engine. Do not persist notes in application SQL.

Tradeoff: a separate backend and session store add setup work but establish cross-client persistence and a verifiable access boundary. Mock Brain data is deliberately process-local and resets on backend restart. No provider, deployment, scheduling policy or new agent is selected by this record.
