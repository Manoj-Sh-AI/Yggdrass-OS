# Application agents v1

Approved scope: Claude first, server-side credentials; independently tested
specialists followed by Yggdras coordination. No paid development verification.

## Ownership

- Existing Lia owns knowledge, retrieval, semantic relationships and Brain maps.
  The app's subprocess adapter invokes her existing **read workflow**, using her
  own environment, row-backed library, skills and checks. It never imports the
  memory package into the application service or rewrites that engine.
- Task Manager owns application task proposals. Calendar owns event, date-range
  and availability proposals. Both read bounded canonical records.
- Yggdras answers directly or delegates bounded, isolated-context steps. The
  router/planner/checker are responsibilities, not extra permanent model agents.
- Application PostgreSQL owns execution history, receipts and owner decisions.
  None of these automatically become Brain facts.

## Execution

Only explicitly submitted Chat requests enter the worker. Held history is never
replayed. A private activation cutoff excludes pre-activation queued requests and
handoffs too. Message edits, deletion, archive and cancellation invalidate the
old request and its pending proposals.

Direct Chat actions are structured proposals shown in the shared Review control.
Accept applies the exact stored payload against its original target version;
dismiss changes no work. Approval, canonical mutation and decision receipt share
one application transaction. Retry identities cannot apply another payload.
Unmentioned metadata, dependencies and goal references survive updates. Original
task objectives cannot change. Task cancellation retains goal/history and cancels
future blocks; started/finished work remains protected. Focus starts/switches are
not exposed as model tools.

The worker has a PostgreSQL claim/lease, bounded context and output, an eight-call
application budget, a token stopping threshold and a time limit. Temporary
consultation helpers can only read the other application domain, receive isolated
context and cannot delegate again. All nested application calls share the budget.
There is no shell, arbitrary SQL or arbitrary local-file tool. Skills are an
explicit shipped allowlist, loaded on demand; loading instructions grants no tools.

The existing Lia service retains its own effort/model/checking logic and internal
limits, with its existing budget wrapper. Application call counts do not pretend
to count each internal Lia request. These are stopping controls, not a guaranteed
currency billing cap; an in-flight provider call can complete before a limit is
observed. No automatic paid retry is made by the application worker; Lia's own
existing transport behavior is unchanged.

Lost execution leases fail visibly rather than repeating model calls. Generated
Chat output is stored before delivery; interrupted delivery retries the same
ordered event identities without generating another answer. Cancellation prevents
later steps and publishing proposals; it cannot un-send a provider request already
in flight or roll back an earlier committed source update.

## Saved-note path

Before a Notes write the application records a body-free write intent. After the
existing Brain API save, it stores a deduplicated revision observation and closes
the intent atomically. An interrupted cross-service save is reconciled through
Brain HTTP reads after restart. The source remains PostgreSQL; the new read adapter
creates no temporary note files. Existing Brain write internals remain unchanged,
including their scratch-workspace implementation. Failed background dispatch does not misreport a completed note
save as failed; a warning and retryable observation preserve the distinction.

The existing Lia read workflow supplies grounded context and date explanations.
That context enters the durable handoff inbox. Task/Calendar specialists produce
typed interpretations with exact source quotations; the existing workflow receiver
verifies source revision, commitment identity, target version and protected goals.
Clear supported updates can apply silently. Uncertainty, independent edits and
explicit cancellations go to existing owner review. A missing phrase is never
automatic deletion. Each committed command retains its own receipt even if a
later step fails.

Lia's current reader supplies prose, not a native typed date-event API. This
adapter preserves her response as evidence; application specialists structure it
against the current source body. The original typed producer contract remains
available for a future native Lia producer. Stable identity is still the documented
application reference/producer assertion, not a fabricated immutable Brain ID.

## Interfaces and configuration

Owner-only, existing session/CSRF protection:

- `GET /v1/application/agents/status`: connection issue and recent runs.
- `GET /v1/application/agents/reviews`: exact pending proposals/current values.
- `POST /v1/application/agents/reviews/resolve`: versioned accept/dismiss receipt.

These owner routes alone are added to the browser proxy. Private receiver routes
and their scoped credentials remain inaccessible through it. Local runtime passes
fresh receiver tokens only to the server and worker. Provider/Brain secrets are
excluded from the frontend child environment.

Private runtime `agents` metadata enables the connection, records its activation
time, the existing brain root and optional skill path/model override. It contains
no model credential. Anthropic's key is read privately from the existing backend
environment file. The model catalog exposes only supported names/identities, never
keys. Missing setup disables the worker without preventing the core app starting;
note observations remain durable while the connection is unavailable.

## Explicit limits

No live provider inference is verified during development: the owner chose to
test that connection personally. This is not a claim of semantic/model quality.
Text and small images/text attachments can reach application models; larger files
and unsupported binary formats remain saved with a clear processing error. Direct
Lia attachment ingestion and Brain editing through Chat are not enabled by this
read-only adapter. Whole-note archive/restore HTTP routes remain a Brain-owner
dependency. No engine scratch-file writer is invoked by the new agent adapter or
replaced here; the previously integrated manual Notes write API is unchanged.
Connecting Brain writes through Chat while eliminating those internal workspaces
requires a compatible Claude-owned writer interface, rather than an engine rewrite
inside this application release.

No remote MCP accounts, arbitrary third-party connectors, hosting, native mobile,
voice, notification delivery or energy/scheduling policies are added. The Windows
host continues to share this local backend and build.
