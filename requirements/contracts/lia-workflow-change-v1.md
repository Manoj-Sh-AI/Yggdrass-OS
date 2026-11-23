# Lia → application workflow contract: original proposal

Implementation update, 2026-11-15: [Connected receivers v1](connected-receivers-v1.md) is the current application contract. The owner clarified the chain as Lia → Yggdras → specialized agent → application updates. Lia's date/context handoff is stored separately and never directly mutates tasks or calendar. The receiving side is now implemented and tested with synthetic producers; no live interpreter, router or agents are connected. The original proposal below remains architectural context, not a claim of an upstream Brain endpoint.

This describes an integration boundary, not an implemented Brain endpoint or a new interpreter. Claude owns the producer, semantic reasoning, and memory graph. The app owns validation and canonical task/event writes. Transport/endpoint names await the producer contract.

## Committed note change

The producer must supply a stable Brain namespace/instance identity, durable change identity, note identity, previous/current revisions, change kind (create/update/archive/restore), commit time, and correlation/causation references. Slug alone is not a safe identity after rename or reuse. Current HTTP reads expose slug/revision; rename/reuse handling remains unresolved. An application callback after a Brain write cannot make the two independent databases one transaction.

Delivery must survive restarts and changes made outside this editor. Consumers acknowledge individual changes and deduplicate their effects; sequence allocation is not a global commit-order cursor. Retain/reconcile failed work. Do not silently lose intermediate saves by treating the latest polled note as its entire revision history.

## Application-relevant interpretation

Each interpretation needs:

- A stable identity for the underlying commitment that persists across note revisions, plus the interpretation/revision identity.
- The source change, note identity/revision, and revision-bound source anchor. The original phrase may be transported for validation, but reference tables do not become a second note store.
- Meaning: deadline, fixed appointment, flexible work preference, availability, review, recurrence, historical context, or explicit cancellation. A removed phrase is not automatically a cancellation.
- Precision: date, offset-aware datetime with named timezone, interval, month/year precision, or unresolved/relative reference. Keep date-only deadlines as dates; do not invent exact hours or durations.
- Clear/uncertain disposition, relevant uncertainty/conflict, and producer/validator version. No invented numeric confidence cutoff.
- Proposed action and existing application binding/version when this revises prior work. Titles are not commitment identity.

## Application behavior

Clear, complete, current interpretations may create the appropriate canonical record automatically under the owner's approved policy. Uncertain or contradictory interpretations require a quiet actionable question. Neither missing connections nor review failure reverses a successful manual note save.

The application validates required fields, supported precision, timezone/DST, source revision, duplicate identity, and current target version. A fixed event requires an explicit interval/duration; a deadline alone creates no work block. Historical dates remain context. Availability, coarse reviews, relative timing, and recurrence cannot be coerced into existing event/task fields to bypass missing representations.

Bind the interpretation to the target in the same application transaction as creation/update. Retries reconcile that binding. Changes made manually to the target, work already started/completed, archive/restore, removal, and conflicting sources need explicit reconciliation policy before automatic destructive updates. Preserve original goals and execution history. Avoid feedback loops by retaining causation and distinguishing owner edits from derived changes.

Successful processing remains silent; only decisions requiring the owner interrupt the interface. Backend processing/failure state must remain observable. Do not label unsaved work as saved or silently overwrite newer edits.

## Current implementation boundary

`POST /v1/application/connections/from-note` is an authenticated, explicit owner-command bridge. It verifies a source revision and atomically creates work plus a source link. Its command key deduplicates retries of that command; it is not an interpretation identity or a durable note-change consumer. `capabilities.automatic_interpretation` remains false.

Next: confirm the Brain producer's identity/change contract and typed outputs, then implement/evaluate the application-side consumer using synthetic revisions before connecting real saves. Specialist agents and orchestration follow these independently tested components.
