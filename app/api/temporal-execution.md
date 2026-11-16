# Local Temporal execution

The existing web/desktop interface submits to the same authenticated application
API. A transactional application outbox dispatches each queued run into a unique
Temporal workflow. HTTP requests do not wait for model generation.

## API mapping

| Operation | Application interface | Temporal behavior |
|---|---|---|
| Submit / explicitly resend | `POST /v1/chat/commands` | Start the request's workflow through the durable outbox |
| Read conversation | `GET /v1/chat/conversations/{id}` | Canonical PostgreSQL conversation, independent of worker availability |
| List executions | `GET /v1/application/agents/executions?limit=30&before={id}` | Paginated operational history |
| Inspect execution | `GET /v1/application/agents/executions/{id}` | Ordered effect trace, duration, review states and available live workflow query |
| Inspect proposed action | `GET /v1/application/agents/reviews` | Exact existing proposal and current record values |
| Confirm / dismiss | `POST /v1/application/agents/reviews/resolve` | Durable Update; existing versioned transaction commits the exact decision |
| Cancel execution | `POST /v1/application/agents/executions/{id}/cancel` | Persist cancellation, send Signal, prevent later steps/proposals |
| Connection status | `GET /v1/application/agents/status` | Execution provider, readiness and sanitized connection issue |

Cancel body: `{"version": <execution version>}`. Repeating an already requested
cancellation is harmless. Cancellation cannot undo a committed decision or an
already submitted provider call. Existing message editing/cancellation semantics
remain in force. Held messages require explicit resend and never replay on setup.

Session and CSRF protections apply. Only these owner routes pass through the
frontend proxy. Responses never expose private activity receipts, prompts,
attachment bytes, provider keys or service addresses.

## Local setup

Install the locked application dependencies, then run
`python scripts/install_temporal.py --directory <private-tools-directory>`.
It verifies the pinned official archive and returns its executable digest. Add
that `binary` and `sha256` to private `runtime.json` under `agents.temporal`, and
set `agents.execution_backend` to `temporal` only after the verified app upgrade.
The local supervisor starts a loopback-only Temporal development server, without
its web UI, backed by `<private-app-home>/temporal/history.sqlite`. It shuts the
server down with the service. Windows host and web share the same API.

This local server is not a production deployment. Hosting, TLS/authentication,
retention and production server sizing remain deployment work. Its operational
history must be backed up alongside PostgreSQL when managing future backups.

## Recovery and costs

Completed activities replay from history. Application effect receipts also guard
against a lost activity-completion acknowledgement. Model/Lia calls have a
one-attempt policy; an ambiguous interrupted paid call is surfaced for an explicit
resend. Read and repeat-safe write/delivery activities may retry. No framework can
make an arbitrary external API side effect exactly-once without a matching receipt.

Workflow reasoning shares the same bounded effect generators used by role tests.
Lia remains an external reader with her original engine/policies; application
effect budgets do not count her internal provider calls. Notes writes keep their
existing Brain API path. Agents cannot start focus timers or change fixed goals.

The HTTP middleware wakes execution dispatch after changes, removing the former
idle polling delay. Background reconciliation catches missed notifications and
restart work. Provider responses still use the existing buffered transport and
the browser's existing refresh cadence; token streaming is not claimed.

## Verification

`pytest tests/test_temporal_agents.py` runs real local Temporal and disposable
PostgreSQL with synthetic models. No inference credentials are needed. The same
tests run in CI with the verified Linux CLI. See the delivery report in
`planning/temporal-agent-execution.md` for recorded results.
