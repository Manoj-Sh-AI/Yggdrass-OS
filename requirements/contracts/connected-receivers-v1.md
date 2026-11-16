# Connected application receivers v1

The following describes the receiving-only release. Its application producer and
worker implementation is now specified in [application agents v1](application-agents-v1.md).
The underlying handoff/update ownership boundaries remain in force.

The agreed chain is **Lia → Yggdras → specialized agent → application database → interface**. This release builds the inboxes, validation, persistence and interfaces around that future chain. It does not create Lia, a semantic/date interpreter, Yggdras routing, an agent executor or an automatic callback from the current Notes editor.

## Separate handoff and update permissions

- Lia-side adapter posts `NoteHandoff` to `POST /v1/receivers/note-signals`, authenticated with the private `note_signals` scope. The payload contains stable source identity, namespace, sequence, previous/current revision, lifecycle, context and typed date expressions. **This endpoint never creates or edits application work.**
- Future Yggdras reads `GET /v1/receivers/handoffs` with the separate `workflow_dispatch` scope. Reading does not remove or consume a handoff. It acknowledges individual IDs explicitly after handling them. Every accepted revision remains in the durable ledger. No router is implemented here.
- A future specialized agent reads the current source/binding cursor through `GET /v1/receivers/workflow/source?handoff_id=…` and posts `SourceChange` to `POST /v1/receivers/workflow/changes`, using the separate `workflow` scope. The update must refer to a matching stored handoff. It includes stable commitment identities and explicit proposed application operations. Lia's handoff token cannot authorize these updates.
- A background provider posts ordered state receipts to `POST /v1/receivers/background/events` under the independent `background` scope. This records unattended state, never human focus time or task completion.

Browser owner sessions cannot use these private receiving endpoints through the frontend proxy. Future tokens are backend-only; scopes are disabled when absent. The local runtime accepts an optional private `receiver_tokens` configuration. No tokens are enabled for actual agents in this release. This is an integration-level scope boundary, not a finished multi-tenant/per-agent authorization system.

## Identity, source verification and delivery

`NoteHandoff` is defined in `handoffs.py`; `SourceChange` and `Interpretation` in `workflow.py`. Their Pydantic schemas are the executable v1 contracts. IDs are stable across retries; a reused ID with different content conflicts. Handoffs arrive in source order and retain context at each revision. Agent commands have a separate source command sequence, which a future router can coordinate using the source cursor; distinct agents share the same Lia source identity and stable local note reference.

Active note revisions are checked through the existing authenticated Brain HTTP reader, outside application write locks. Durable receipts replay without a fresh Brain read. The current Brain reader exposes slug/revision rather than immutable Brain identity; `external_identity` remains a trusted producer assertion, stated explicitly by capabilities. Namespace/source collisions and slug reuse do not silently merge unrelated work. Archive/missing observations are producer assertions, not fabricated Brain HTTP archive operations. Real producer identity, delivery guarantees and handoff generation must be agreed with Claude before connecting an actual producer.

Agent commands require the matching handoff's source identity, slug, revision and lifecycle; a newer handoff prevents stale application mutations. Source references and target creation/update are committed together. Workflow binding targets have actual typed foreign keys. Audit records retain the original command, proposed meaning, anchors, context and outcomes. These are application provenance, not a replacement authoritative Brain or semantic graph.

Existing manual work is never matched by title. The source cursor exposes bounded linked target metadata. An agent can name an explicit `target_id` and `target_version`; first binding requires owner review and reuses that record without creating a duplicate. Subsequent updates follow the binding/version rules. JSON fingerprints are canonical across object-key ordering, including a PostgreSQL JSONB round trip.

## Clear, uncertain and destructive meaning

- A clear, complete deadline can create a task. A date remains a date; an exact deadline needs an offset-aware timestamp and explicit timezone. No work block is fabricated.
- A clear fixed appointment needs an explicit interval/duration, offset-aware time and named timezone. All-day/review ranges use calendar-date records; availability has separate records and consumes no human focus time.
- Month/year/relative precision, preferences and recurrence remain retained proposals requiring clarification; they are not coerced into midnight appointments or invented scheduling rules. Clear historical context creates no task. Uncertain interpretations become quiet owner decisions.
- Independent owner edits, changed goals, started/completed work and removed calendar records are protected. The original goal cannot be replaced by this receiver, even during conflict confirmation. Reconcile a different goal as separate work.
- An absent/removed phrase is not automatic cancellation. An explicit cancellation proposal requires confirmation. Confirmed cancellation retains the task/goal/history and removes active execution blocks, or marks a calendar item removed. It does not delete Brain data.
- Archive/missing observations preserve application work and history and create a decision where work is bound. Rename/restore update the same reference after active revision verification; completed work is not reopened.
- Owner decisions use versions and idempotent receipts. A successful accepted retry does not depend on Brain availability. Newer source revisions supersede old proposals; unrelated proposals from another agent for the same revision remain pending.

## Interface and operational graph

Clear successful updates are silent. Only actual pending decisions expose the shared Review control. The decision view shows source context, proposed changes and current values, permits accepted supported updates or keeping current work, and preserves failed decisions for retry. Unsupported/uncertain proposals require clarification through the source rather than guessed dates.

Today, Calendar and Tasks consume the same canonical tables and refresh on their existing polling/resume paths. Notes shows source links and reverse context. Graph's optional Work connections layer reads real typed relationships with bounded neighborhoods, explicit truncation, pan/zoom, keyboard selection and a list alternative. Its Brain viewer remains unchanged. Large task neighborhoods do not load the complete graph.

Background activity remains collapsed until requested and absent when there are no runs. Its elapsed clock is independent of the sole human timer. Cancellation is a request; a run remains active until its provider sends an ordered terminal receipt. No executor is created.

## Chat destination selection

Agent/model choices belong to backend-owned metadata (`chat_catalog.py`). Conversations persist the next-message destination; messages and response requests snapshot their destination. Switching choices does not retarget an existing request or replay held messages. Explicit resend uses the current valid selection and creates a new request. Replies retain the responding request's agent/model metadata.

The default local catalog offers Yggdras and Lia as disconnected destinations and Provider default as the model placeholder. Actual model options come from a registered backend catalog; tests use clearly synthetic options only. Unavailable selections may preserve intent/history but cannot queue processing. Unknown or incompatible agent/model pairs are rejected. The optional private `chat_catalog` metadata contains no keys or tools. No model provider is called in this release.

## Explicit remaining boundary

The receiving-side contracts can be exercised with synthetic producers now. Actual note-save triggering in Lia, Yggdras dispatch, specialized agent implementations, semantic relationship maintenance and model provider execution are later work owned by the agreed components. Whole-note Brain archive/restore HTTP writes remain unavailable until the Brain owner supplies them. Application capabilities report this rather than pretending those operations work.
