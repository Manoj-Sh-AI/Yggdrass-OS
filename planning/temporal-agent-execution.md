# Temporal execution integration

Approved direction: retain the application-facing API and introduce a durable
execution backend following temporal-community/temporal-ai-agent's separation of
HTTP commands/queries, workflows, activities and tools.

1. Record contract and tradeoffs; install the official SDK and verify local CLI.
2. Extract shared specialist/coordinator effects so synchronous tests and durable
   workflows execute identical reasoning and validation logic.
3. Add application-only execution receipts/metadata and real Temporal workflows,
   activity adapters, dispatch reconciliation and approval/cancellation messaging.
4. Wire existing owner APIs and local Windows supervisor, preserving source
   observations, authentication, frontend behavior and Brain boundaries.
5. Test with a disposable database, real Temporal and synthetic models. Verify
   interrupted execution and repeat-safe decisions, then activate locally after
   backup/upgrade checks. Never rebuild the active frontend directory.
6. Record actual results and remaining limitations in the delivery report.

Reference code is studied, not blindly copied. The existing authentication,
per-conversation identity, bounded context and checked writes are retained.

Completed locally. See [delivery and verification](temporal-agent-execution-verification.md)
for the active build, tests, preserved data and operational limits.
