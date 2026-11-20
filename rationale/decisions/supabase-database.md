# The database moves to Supabase (amends principle 5 / D13)

Date: 2026-11-20. Owner: Manoj. Plan: `planning/supabase-database-move.md` (approved).

**Decision.** The shared database (schemas `app` and `brain`, layout
`shared-schemas-v1`) moves from the laptop's PostgreSQL to the Supabase project
`iijaibqmzcwmiaqsvwel` (eu-central-1). Both schemas move, as chosen on 16 Nov, so the
backend, Lia and the voice agent can later run in the cloud and the phone can answer
calls without the laptop.

**Amendment.** Principle 5 ("No cloud-queryable store of the brain") and D13 are amended
by the owner: note contents in the `brain` schema may live in this one Supabase database.
What still holds:
- The database is the brain (D44, Manoj 2026-11-12, `YGGDRAS_BRAIN_SOURCE=rows`); the
  frozen markdown is a rollback copy only, and the nightly verified dumps are the backup.
- Nothing is exposed through Supabase's Data API: `app` and `brain` are not published,
  and the `anon` and `authenticated` roles get no rights on them. Only the app's own roles
  (owner, runtime, migration, brain) can read them, with passwords kept in
  `runtime.json` and the brain `.env` on the laptop.
- No personal data or credentials in the repository.

**Why.** Phone answering, a cloud voice agent and Vercel all need a database reachable
over the internet; Supabase was the owner's chosen host. The laptop has no IPv6, so the
connection uses Supabase's session pooler (IPv4).

**Backups.** Supabase Free has no downloadable backups. The app keeps its own verified
dumps on the laptop: nightly (kept 14 days) and before every migration or cutover.

**Rollback.** The local cluster is kept untouched after cutover; switching the URLs back
restores it.

**Done.** Cut over 2026-11-20 18:50; see the plan for the verification results.
