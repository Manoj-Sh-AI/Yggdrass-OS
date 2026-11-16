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
