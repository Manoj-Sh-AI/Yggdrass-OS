# Local shared PostgreSQL verification — 16 November 2026

## Delivered

The installed application and Brain API now use one local PostgreSQL database
containing separate `app` and `brain` schemas. The active layout is
`shared-schemas-v1`. This is a local consolidation; no Supabase project or other
cloud resource was provisioned.

Final authenticated read-only verification confirmed:

| Check | Result |
| --- | --- |
| Application tables | 45 |
| Brain tables | 13 |
| Combined database size | Approximately 12 MB |
| Real notes readable through the existing Brain API | 82 |
| Brain graph nodes | 82 |
| Note editor, task and chat reads | Passed |
| Today, Tasks, Calendar, Notes, Graph and Chat page responses | Passed |
| Restricted application, migration and Brain roles | Passed |
| Brain records, schema definitions and original text defaults | Preserved |
| Original source databases | Retained and unchanged |
| Existing password, frontend build and Temporal configuration | Preserved |
| Existing Temporal execution service | Ready |
| Paid provider calls or personal Brain mutations submitted by verification | Zero |

The live page checks verify authenticated responses and editor data retrieval;
they are not a new visual or exhaustive browser interaction audit. The existing
Windows desktop verifier also opened the installed application's sign-in screen.

## Data safety and recovery

Full application and Brain backups were restored and checked before copying.
The full combined backup was also restored and checked. Complete row and sequence
fingerprints and normalized schema definitions matched. Original database and
prior combined-copy lineage was checked again after activation.

Backups, connection settings and activation records remain under the private
installed runtime at `C:\Users\shman\AppData\Local\Yggdras`; no credentials were
written to tracked files or printed. The current private archive is referenced by
`consolidation.json`. The machine-readable final check is saved both in that
archive and in ignored `app/api/runtime/shared-database-live-verification.json`.

An earlier service-start failure exercised rollback to both original connection
settings. The final copy's activation was interrupted after settings switched but
before its completion record was written. Recovery compared the exact intended
settings, all copied records, schema definitions, text defaults and permissions,
then restarted the existing services and finalized the activation record after
the Brain API became readable.

Original databases are rollback copies, not live replicas. After new saves,
reverting connections requires reconciling those saves first. Do not delete the
originals or restore stale copies over current data.

## Tests and code checks

- Focused backup, upgrade, local runtime, shared database and Temporal rerun:
  **33 passed**.
- Latest shared-database tests after the locale and installed-permissions fixes:
  **6 passed**. These overlap the focused suite above; they are not 39 distinct
  tests.
- The shared tests use disposable PostgreSQL databases, including Unicode task
  creation, completion and reload, permission denial, backup restoration and
  activation rollback. They do not edit personal notes.
- Scoped Ruff checks and formatting checks passed for the six database-related
  Python files; `git diff --check` passed.
- An earlier broader run had a shared-fixture contamination failure and a Temporal
  timing failure. The fixture was isolated and both passed the focused rerun.
  Whole-workspace green CI is not claimed: unrelated orchestration changes were
  being developed concurrently, and a broader lint run reported unused variables
  in their new API tests.

## Implementation scope

- `shared_database.py`: verified copy, backup restoration, fingerprints, schema
  checks, installed permission copying and restricted-role verification.
- `local_consolidation.py`: local preparation, private settings cutover, rollback
  and preservation of original Brain text defaults.
- `backup.py`: consistent UTC fingerprint serialization.
- `database.py` and `local_upgrade.py`: existing-schema support and restricted
  application migrations with Brain preservation checks.
- `test_shared_database.py`: disposable database and interaction verification.
- API README, requirements contract, implementation plan, deployment research and
  decision record: shared storage operation, boundaries and tradeoffs.
- Private runtime configuration and the existing Brain service environment:
  updated connection settings only. Lia's memory-engine code was not changed.

The permissions copy uses the tables actually installed locally. It does not
apply unrelated migration 011 or grant access to not-yet-installed orchestration
tables merely because newer code references them.

## Remaining considerations

The original application default locale was `C`; Brain's was
`English_India.1252`, both with UTF-8 and English text search. The shared database
preserves Brain's defaults. Application default text ordering and case behavior
therefore follow those defaults too; Unicode CRUD was verified. Linux/Supabase
locale parity needs a separate migration check before cloud cutover.

Restart any already-open external Lia/MCP session so it reloads the updated
private database connection. Application migrations remain restricted to `app`;
Brain schema migrations retain separate ownership.

The next deployment step can target one Supabase project, with these schema and
permission boundaries preserved. Hosting and deployment remain separate work.
