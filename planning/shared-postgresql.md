# Local database consolidation

1. Inspect actual local connection targets without exposing credentials. Confirmed:
   application has 45 `app` tables; Brain has 13 `brain` tables. Both use PostgreSQL
   and only the built-in plpgsql extension; neither currently has large objects.
2. Implement a reusable copy-and-verify operation and synthetic integration tests.
   Sources remain read-only except short table locks preventing concurrent writes.
3. Restore-verify full source backups; import existing schemas into a fresh named
   database in the owned local PostgreSQL cluster under separate schema owners.
4. Check all rows, sequences and schema definitions, cross-schema permission denial,
   and full combined backup restoration before changing service connections.
5. With application workers stopped, back up private configuration, switch the
   application and Brain connections, restart the existing services, and verify
   authenticated reads without submitting paid inference or changing personal data.
6. Record actual verification and rollback instructions. Preserve original databases
   and Temporal's separate local execution-history store. Do not deploy.

The existing application-only provisioning guard stays in place: consolidation is
an explicit operation, not an implicit side effect of ordinary startup/import.

## Operating procedure

Run the API environment's Python module `yggdress_app.local_consolidation` with an
explicit `--home` pointing at the private installed runtime. `prepare` creates and
verifies the new copy; `activate` checks for changed source data/configuration,
switches both service connections, starts the existing services, and checks the
Brain search API. Private `consolidation.json` records the selected archive and
state. The archive contains full application/Brain/combined dumps and configuration
copies. It stays outside the checkout, under the existing private runtime ACLs.

Preparation temporarily stops the owned application/Brain services. A maintenance
marker prevents a desktop launch from accepting edits while the copies are checked.
Unrelated listeners, existing destinations, active submitted jobs, unknown source
schemas, extra extensions and large objects cause a refusal rather than data loss.

If activation fails, the operation restores both prior configuration files and
restarts the prior services. If preparation is interrupted, inspect the private
state before restarting; do not delete the originals or retry into an existing
destination. A partial database is retained for inspection, never silently reused.

After successful activation, the old databases are rollback copies, not synchronized
replicas. Once new edits have been made, restoring old connections requires
reconciling those edits first. Existing external Lia/MCP sessions must restart to
reload their updated private database setting. No memory-engine code is changed.

Application upgrades recognize `shared-schemas-v1` only when explicitly configured;
they use the separate restricted application migration connection and compare Brain
records before/after. Initial provisioning still refuses mixed source databases.
Brain schema migrations remain an explicit Brain-owned administrative operation;
the normal Brain service is not granted database-wide schema-creation privileges.

The preserve-brain-text operation corrects an already consolidated local
installation by making a verified copy of its CURRENT shared records with the
Brain's original text settings, then switching services. It retains previous
databases and never replaces new saves with stale original records.
