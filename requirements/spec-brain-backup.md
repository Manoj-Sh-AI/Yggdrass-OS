# Brain backup and restore verification

Authorized by Manoj, 2026-11-12: archive the Yggdras Markdown files in his OneDrive and verify a full PostgreSQL backup. This is a backup-only task; originals, memory engine, source mode and live-write gate remain unchanged.

Acceptance:

- Make a new dated snapshot; never move/delete originals or overwrite earlier backups.
- Archive the discovered Brain folders and project Markdown records, preserving relative paths. Exclude Git internals, dependencies, builds and temporary test outputs. Reject linked paths escaping a selected source; do not silently omit unreadable files.
- Take a complete custom-format logical dump of the configured Brain database, including schema, data, sequences and large objects. Read credentials only from private backend configuration; never put a password in arguments, output, manifests or source.
- Use a shared read-only database snapshot for the dump and source fingerprints. Verify the dump by restoring into an independently initialized temporary PostgreSQL cluster, never the source server.
- Compare every user table/materialized view's content and row count, sequences, large objects and normalized schema. Publish a verified status only if every comparison passes.
- Put the verified dump, Markdown ZIP and manifest with SHA-256 checksums into OneDrive. Verify copied bytes again; publish the final folder only after verification. Keep partial failures clearly distinguishable and never claim successful cloud upload from a local copy alone.
- Test non-destructive archive behavior, exclusions, traversal/symlink protection, corruption detection and credential handling using invented data.
- A logical database dump is not a whole PostgreSQL-server backup: cluster roles/passwords and server configuration are outside its scope. Restoration verification uses local verification ownership, not production credentials/privilege grants.
