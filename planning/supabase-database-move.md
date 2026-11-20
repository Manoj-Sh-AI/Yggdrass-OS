# Moving the database to Supabase

Status: DONE 2026-11-20 18:50 (cutover run with Manoj). The app and Lia use Supabase;
the laptop cluster is stopped and kept for rollback.

Supabase project: `iijaibqmzcwmiaqsvwel` (AWS Frankfurt, eu-central-1). Owner choice of
16 Nov (`planning/deployment-research-2026-11-16.md`): one Supabase project holding the
`app` and `brain` schemas with separate roles. This is step 1 of the cloud move; Vercel
and the backend/voice agent come after.

## What exists today (measured)

- One local PostgreSQL 18.4 database, layout `shared-schemas-v1`: schema `app` (59 tables,
  ~4.9 MB) and schema `brain` (13 tables, ~1.3 MB); 14 MB in all. No extensions.
- Roles: owner `yggdras_owner`, runtime `yggdras_application`, plus per-schema owner roles.
  The backend uses three URLs in `%LOCALAPPDATA%/Yggdras/runtime.json` (admin, runtime,
  migration); the brain service and Lia use `BRAIN_DATABASE_URL` in the brain `.env`.
- The brain's text default is `English_India.1252` (Windows); Supabase runs Linux
  locales, so text ordering/matching needs a parity check (already flagged in
  `rationale/decisions/shared-postgresql.md`).
- Markdown stays the source of truth for the brain (D1); the `brain` schema is what the
  brain service and Lia read.

## Findings that shape the plan

1. **Connection:** the direct host `db.<ref>.supabase.co` is IPv6-only and this laptop
   has no IPv6 (port 5432 unreachable). Use Supabase's **session pooler** (IPv4, free,
   port 5432, user `<role>.<ref>`), shown in the dashboard under Connect -> Session pooler.
2. **Version:** Supabase projects run PostgreSQL 17 or older; a dump from 18 is checked
   by a dry-run restore before cutover (plain tables, no extensions: expected to work).
3. **Exposure:** Supabase's Data API publishes the `public` schema to anyone with the
   publishable key. `app` and `brain` are kept out of it, and `anon`/`authenticated`
   get no rights on them. No row-level security is needed because nothing is exposed.
4. **Backups:** the Free plan has no downloadable backups. Keep the app's own verified
   dumps (`backup.py`) on the laptop, nightly, plus one before cutover.
5. **Privacy (needs Manoj's decision):** moving `brain` puts note contents in a cloud
   database. That amends principle 5 / D13 ("no cloud-queryable store"); it is recorded
   as a decision before any copy.
6. **Code:** the local runtime starts and owns a local PostgreSQL and the upgrade command
   refuses any other cluster. A "remote database" mode is needed: do not start local
   PostgreSQL, run migrations and grants against Supabase, back up from Supabase.

## Steps (each verified before the next)

1. Manoj puts the Supabase **session-pooler** connection string for `postgres` in a
   private file (never in chat or the repo): `%LOCALAPPDATA%/Yggdras/supabase-admin.url`.
2. Connectivity + version + locale check (read-only): server version, default
   collation, Data API schemas.
3. Remote-database mode in `local_runtime.py` / `local_upgrade.py` (tests with a fake
   remote URL; the local cluster stays the default).
4. Create the same roles in Supabase with new random passwords (stored only in
   `runtime.json` and the brain `.env`), schemas `app` and `brain`, no Data API exposure.
5. Dry run: dump the live database, restore into Supabase, compare schema and row
   fingerprints (existing `backup.fingerprints`), run the locale parity check, then
   drop the dry-run copy.
6. Cutover (app stopped, ~5 minutes): final verified dump -> restore -> fingerprints
   equal -> switch `runtime.json` URLs and `BRAIN_DATABASE_URL` -> start -> smoke test
   (sign in, calendar, a note read through Lia, a simulated call).
7. Rollback stays possible: the local cluster is kept untouched; switching the URLs
   back restores it (anything written to Supabase after cutover would be copied back
   first).

## Results so far (2026-11-20)

- Step 1 done: the session-pooler string is in the private file.
- Step 2 check: PostgreSQL 17.12, `en_US.UTF-8`, UTF8; `app`/`brain` absent and not exposed
  by the Data API; the admin role can create roles.
- Steps 3-4 code: remote-database mode, schema-scoped backups, nightly backups (built and
  tested; `cloud_move.py check|dry-run`).
- Step 5 dry run: a verified snapshot of 72 tables / 4,594 rows restored from PostgreSQL 18
  into Supabase 17 with every table and sequence identical; the copy was removed.
  Text sort order differs only in `brain.aliases.alias` and `brain.changes.old_text`;
  the brain code orders aliases with `COLLATE "C"` and never orders `old_text`, so no
  behaviour changes. Backup kept: `supabase-dryrun-20261120-182522.dump`.
- Cutover built (`cloud_move.py cutover|rollback`), tested between two throwaway
  databases: stops the app, takes a final verified dump, recreates the same role names
  with new random passwords (pooler logins `<role>.<project>`), lets each owner create
  and restore its own schema, copies the runtime role's exact grants, revokes everything
  from PUBLIC/anon/authenticated on `app` and `brain`, verifies every table and sequence
  and the isolation, saves `runtime.json` and the brain `.env` as `*.before-supabase`,
  switches both, stops the laptop cluster (so nothing writes to the old copy unnoticed)
  and starts the app. Any failure removes the Supabase copy and restarts on the laptop.
- After the switch, Claude's yggdras connector must be restarted (it keeps the old
  database setting until then).
- Cutover 2026-11-20 18:49-18:50: 72 tables / 4,616 rows identical, roles isolated,
  app serving, app sees its tasks, brain sees 82 notes, brain search works through the
  brain service, voice worker heartbeat healthy. Backup: `supabase-cutover-20261120-184944.dump`.
  Saved for rollback: `runtime.json.before-supabase`, brain `.env.before-supabase`.

## Risks

- Every query now crosses the internet (~20-40 ms from Germany); the 15-second call
  sweep and voice turns stay well within budget, but the app will feel slightly slower
  until the backend also moves to the cloud.
- Laptop offline = no database. That is already true of the whole app today.
- Free plan: 500 MB database (we use 14 MB); the project pauses after 7 days without
  activity, which the 15-second sweep prevents while the laptop is on.
