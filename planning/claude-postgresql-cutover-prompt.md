# Claude: review the PostgreSQL migration gate and enable live writes

**Subsequent operational update, 2026-11-12:** Manoj explicitly requested that application engineering enable the existing write mode while leaving the memory engine untouched. That private setting is now `rows`; the existing Brain HTTP API has been restarted at the application-expected address. Authenticated app reads of 82 notes and a preview-only absent-note diagnostic passed. No personal notes were changed in testing. The failed historical parity gate remains unresolved and unchanged. Treat the cutover steps below as the earlier proposed sequence; first verify current state rather than switching again. The remaining request for Claude is the failed-gate diagnosis, not an assertion that the gate passed. Details: sibling application's `planning/notes-live-write-integration.md`.

I authorize you to finish the PostgreSQL cutover for my existing Yggdras Brain, including enabling live writes and restarting the Brain service **after the migration readiness checks pass**. Do the investigation and scoped fixes first; if the gate cannot be cleared, report the blocker rather than forcing the switch. Do not ask me again for permission to enable writes once these conditions are satisfied.

## Project and ownership

Work in `C:/Users/shman/OneDrive/Desktop/Yggdrass OS/Yggdrass-OS-main`, the checkout containing the current Brain implementation. You own Lia's memory, retrieval, semantic relationship handling and Brain persistence. Preserve those semantics; do not rebuild the engine or redesign the Notes UI. Application engineering is in the sibling `Yggdrass-OS` checkout.

Read the original decisions and their latest amendments, especially `rationale/decisions/D44-database-is-the-brain.md`, the write/approval/restore decisions, and the relevant decision-register entries. The goal is for PostgreSQL to become the live source of truth, with the old Markdown Brain frozen rather than used to reload over database changes.

## Backup readiness

The full logical Brain database backup was restored into a fresh, isolated PostgreSQL 18 cluster and compared with its exported read-only source snapshot. All 13 user tables, complete row contents, sequences, large objects and normalized schema matched, including 82 notes and 188 relationships. The Markdown archive contains 1,955 files from both Brain folders and both project checkouts. Originals were preserved.

The backup folder is:

`C:/Users/shman/OneDrive/Yggdras Backups/2026-11-12_19-31-30Z_fa5cc5`

It contains `brain-postgresql.dump`, `markdown.zip`, `manifest.json`, `verification-report.json` and `README.md`. Check the artifacts/checksums before relying on them. I have now confirmed that the backup files have reached OneDrive online. The dump covers the complete Brain database, not server-wide role passwords or PostgreSQL server configuration.

## Recorded blocker to investigate

`local-data/rows-parity/parity.md` currently records:

- accuracy, invented citations, absence checks, cost and latency bars: PASS;
- traps: FAIL;
- `Switch the default to rows: NO`.

The accompanying `load-report.txt` reports matching data counts, including 82 notes, 299 facts, 134 explicit links, 54 mentions and 165 aliases. Matching counts do not settle the failed behavior check.

Inspect the underlying stored runs, expected results, configuration and evaluation code. Establish whether this is a genuine PostgreSQL-path regression, nondeterminism, an evaluation issue or a stale report. Identify the exact failing cases and root cause. Make the smallest justified fix if needed, respecting the existing test budgets. Run the relevant free tests and the necessary parity verification. Keep the original evidence and report the new result; do not weaken acceptance bars or change expected answers merely to make the gate pass.

## Enable the existing database write path once ready

After the backup evidence is checked and the migration gate passes:

1. Configure `YGGDRAS_BRAIN_SOURCE=rows` privately in the environment actually used by the running Brain service. Do not hard-code credentials or change the fallback to conceal a failed cutover.
2. Restart only the verified Brain service. The application expects the authenticated Brain API at `http://localhost:8100`; preserve its server-side Basic Auth and verify the actual running process picked up the new configuration.
3. Confirm Lia reads the database-backed library/maps, and that all intended writers now target PostgreSQL rather than continuing to write or reload the frozen Markdown Brain.
4. Verify search and note reads. A preview-only request to a deliberately nonexistent diagnostic note can distinguish the old Markdown refusal from a database-mode not-found response without modifying a personal note.
5. Exercise create, add fact, replace/confirm, permanent remove/unlink, archive/reference cleanup, restore, Undo, stale versions and map/relationship consistency on an isolated database of invented notes. Do not delete or experiment on my personal notes as a test. State explicitly which live checks were read-only.

Preserve the recorded CRUD rules: additions return a summary and Undo; changes/removals require their approved confirmation; whole-note delete means archive with reference cleanup; fact Remove and explicit Unlink are permanent under the latest amendment. Keep confirmation capabilities outside model control.

## Scope and separate application follow-up

Do not build the general orchestrator, tasks, Calendar, Supabase migration or another semantic linking engine. The app's agreed future sequence is: save the exact manual edit to PostgreSQL first, automatically trigger Lia after every successful Save, review silently, and surface conflicts. A no-new-connections outcome must leave the user's edit saved. That application trigger is not yet implemented; enabling database writes alone must not be reported as completing it.

The current RowStore materializes temporary Markdown scratch workspaces. Their removal is a separately identified user-owned/Brain-owned follow-up. Do not delete my originals or OneDrive archives, and do not claim the current database path has zero intermediate files unless that has actually been addressed and verified.

## Report

Return the failed-gate diagnosis, minimal changes, verification results, the current source mode and confirmed service address. Say whether live PostgreSQL writes are enabled. Identify any remaining blockers and distinguish database-cutover completion from the application's still-pending post-save Lia review integration. Never print or return passwords, API keys or database connection strings.
