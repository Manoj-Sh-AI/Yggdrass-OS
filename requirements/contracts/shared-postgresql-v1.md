# One local PostgreSQL database, separate application and Brain schemas

Authorized by the owner on 16 November 2026: combine the existing local databases
before preparing a single-project Supabase deployment. This supersedes the earlier
requirement for physically separate application and Brain databases, not their
logical separation or Lia's ownership of memory algorithms.

## Acceptance criteria

- Copy both databases into a new local database. Retain both originals, unchanged;
  never overwrite or drop a source database. Refuse an existing destination.
- Preserve the existing `app` and `brain` schemas, records, sequences, relationships,
  migration histories, views, indexes and functions. Do not redesign Brain tables.
- Back up and restore-verify both sources before importing. Compare complete row
  fingerprints and schema definitions after importing, then restore-verify the
  combined backup. Reject unsupported extensions, large objects or extra schemas
  rather than silently omitting data.
- Keep application runtime, application migrations and Brain access under distinct
  restricted roles. Application runtime/migrations cannot read or change Brain;
  Brain access cannot read or change application records. Service credentials never
  reach the browser, console or tracked files.
- Point the existing services at the same database after verification. Preserve
  sign-in, current frontend build, existing API contracts and Temporal history.
- Keep future application upgrades restricted to `app`, while checking that Brain
  contents survive unchanged. No memory engine, graph, retrieval, provider, UI,
  energy policy, paid test call or cloud resource changes belong to this task.
- Verify using disposable PostgreSQL fixtures, then perform authenticated read-only
  application/Brain checks against the combined local database. Do not test by
  editing personal notes or submitting model requests.
- Keep private configuration copies and a rollback procedure. A failed cutover must
  restore previous service connections; do not discard the original databases.

Supabase provisioning and production Temporal hosting remain subsequent work.
