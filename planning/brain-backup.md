# Backup-only execution

1. Locate the two discovered Markdown Brain directories, both project checkouts and the private Brain database connection. Inspect existing parity records without printing personal note contents.
2. Implement a reusable backup/verification command using existing PostgreSQL tools and psycopg. Use no memory-engine imports or new dependencies.
3. Verify the command on synthetic files/database data, then take a read-only full Brain database snapshot and ZIP the selected Markdown sources.
4. Restore into a fresh loopback-only temporary cluster and compare data/schema fingerprints. Stop that cluster after verification.
5. Copy verified artifacts into a new dated OneDrive folder and verify checksums. Report restore evidence, file counts and cloud-sync status accurately.

Tradeoff: a full logical dump plus restore is slower than checking archive headers but proves data can actually be recovered. Temporary filesystem work here is backup/restore staging, separate from the prohibited Notes save path. A verified local OneDrive copy is not by itself proof of off-PC availability; that remains a separate provider-sync check. Nothing enables live writes or changes source data.

## Completed verification

- Reusable command: `app/api/src/yggdress_app/backup.py`; no memory-engine imports or new dependencies.
- Nine tests pass, including an isolated complete database restore, Unicode/binary data, sequences, materialized views and large objects. Ruff checks/formatting pass.
- Real backup created in a new dated folder under the user's personal OneDrive `Yggdras Backups` directory: Markdown ZIP, custom-format PostgreSQL dump, checksum manifest and verification reports.
- 1,955 Markdown files were archived from both discovered Brain folders and both project checkouts. Their source hashes were rechecked after publishing; all matched and originals remain in place.
- Real database restore passed in a fresh local PostgreSQL 18 cluster. All 13 user tables, complete row contents, sequences, large objects and normalized schema matched the exported read-only snapshot. Included 82 notes and 188 relationships. Copied artifact checksums match the verified originals. The isolated verification cluster was stopped.
- The dump is the full logical Brain database; server-wide roles/passwords/configuration are not included. Verification deliberately did not replay production ownership/access grants.
- The configured personal OneDrive client was started. Cloud Files flags did not independently establish that these artifacts were uploaded. Cloud/off-PC availability remains unconfirmed; no live-write setting or source mode was changed.
- Subsequent readiness inspection found the existing `local-data/rows-parity/parity.md` in the sibling checkout explicitly records “Switch the default to rows: NO”: accuracy, citation, absence, cost and latency bars pass, but its traps bar fails. The load report's counts agree (82 notes and associated data). This is a recorded behavior-gate failure, separate from backup integrity, and requires the Brain owner's review or a newer approved gate result before cutover. No paid evaluation was rerun and the report was not edited.

For another snapshot, run the command from `app/api` with explicit `--source` folder(s), `--destination` backup folder and `--env-file` private backend configuration. Each invocation uses a fresh dated destination and performs another complete restore check. No scheduled backup automation was configured.

Subsequent user confirmation: the backup files have reached OneDrive. This is user-confirmed cloud availability, distinct from independent provider verification. The user also authorized enabling live writes; the separate recorded failed migration gate still needs the Brain owner's review. A scoped review-and-cutover prompt is in `planning/claude-postgresql-cutover-prompt.md`. No running service setting was changed while preparing it.
