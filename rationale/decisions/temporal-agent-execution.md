# Temporal as the application execution backend

The owner explicitly approved replacing the agent execution plumbing with a
Temporal-backed command/query/workflow structure. This revises the earlier choice
to use only an in-process PostgreSQL worker; agent responsibilities do not change.

Temporal owns execution progress and durable activity results. PostgreSQL remains
authoritative for application entities, conversation history, proposal decisions,
idempotency receipts and owner-readable traces. Brain storage and Lia's retrieval,
checks and graph logic are untouched. Temporal history is operational history,
not Brain memory. Attachment bytes remain outside workflow history.

Tradeoffs: a local Temporal service and SDK add maintenance/storage overhead in
return for resumable step execution, durable waits, explicit messaging and a
common execution model for future agents. Immediate dispatch removes an existing
polling wait; provider-generation speed is not guaranteed to improve.

The workflow runs the same bounded agent effect generators as the synchronous
test adapter. Model and Lia calls use one-attempt policies plus durable receipts;
an ambiguous paid operation fails visibly. Pure reads and idempotent delivery or
approved writes may retry. Retry is never treated as exactly-once external I/O.

Use local persistent Temporal development server only for the approved local
application; production hosting, authentication/TLS and retention are separate
deployment work. Bind all local endpoints to loopback. Application secrets stay
in activities/private configuration and never enter workflow inputs or trace APIs.

Sources: https://github.com/temporal-community/temporal-ai-agent,
https://docs.temporal.io/develop/python/workflows/message-passing,
https://docs.temporal.io/develop/python/workflows/child-workflows.
