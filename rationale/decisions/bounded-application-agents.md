# Bounded application agents

The owner approved a single continuing agent-layer delivery after the application
receivers, with orchestration following independently tested specialists.

Keep four permanent roles: existing Lia, Task Manager, Calendar and Yggdras.
Routing, planning, checking and dispatch are system responsibilities, not separate
permanent model agents. Temporary workers inherit no additional permissions.

Use existing canonical tables, version checks, receipts and review controls.
An agent produces structured proposals; deterministic code validates the exact
operation, target version and protected objective before any write. Approval
cannot authorize a different later payload. External calls occur outside DB
locks. Ambiguous paid-call failures do not automatically retry and spend again.

Private Anthropic transport is the first provider. Tests inject a model transport
and never call a paid provider. Keys must not enter frontend environment, logs,
database execution records, catalog metadata or model context.

No general multi-agent framework is required for these four roles. The existing
Python, Pydantic and PostgreSQL interfaces are sufficient; revisit this choice if
the working system demonstrates a concrete missing capability.
