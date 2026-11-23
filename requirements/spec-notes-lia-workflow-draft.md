# Notes through Lia — clarified requirements (draft contract)

Captured from Manoj's voice clarification on 2026-11-12. This records the requested next Notes slice, not approval to change Lia's memory engine, enable live writes, delete real notes, or run paid model calls during investigation. Implementation contracts still require review.

Read this together with `notes-crud-decisions-reconciled.md`, which recovers answers from the original decisions and their database amendments. Its resolved baseline replaces the historical open items below where stated; do not ask Manoj to redesign behavior that is already recorded.

**Latest user clarification:** `notes-save-then-lia-review.md` supersedes this draft's synchronous model-on-Save assumption. Manual edits save to PostgreSQL first; Lia reviews the committed change separately afterward. Historical workflow acceptance criteria below must be reconciled with that confirmed sequence before implementation.

## Confirmed product intent

- Finish Notes before extending this pattern to tasks, Calendar or other features.
- Saved editor contents must come from the real Brain PostgreSQL database through the authenticated service. No synthetic-note fallback in the dedicated Notes view.
- Every submitted manual note change must invoke an actual Claude model through Lia's existing workflow. Calling only today's deterministic fact-write endpoints does not satisfy this requirement. Do not interpret a keystroke as a separately approved model invocation.
- Support both levels: whole-note creation/removal/relationships, and additions/replacements/removals of points inside a note.
- Reuse Lia's existing reasoning, retrieval, relationship planning, validation, confirmation and persistence. Application engineering owns transport, editor integration and feedback; it must not reimplement semantic linking or the memory engine.
- Approved changes must persist in PostgreSQL and refresh the saved note and affected relationships in the app. No authoritative Markdown note store or file synchronization in the final path. Whether the newer wording also excludes the database plan's documented temporary scratch workspace remains the one product-level clarification; text formatting within a database value is distinct from a file store.
- Note removal must handle affected connections consistently through Lia's existing semantics, not leave dangling displayed relationships or run independent application SQL cleanup.
- Preserve human review for changes that alter/remove stored memory. Keep drafts on rejection, model/service failure and stale versions. Never display a successful save before authoritative persistence is acknowledged.
- Application data and Brain data remain logically separate; credentials remain backend-only.

## Acceptance criteria to approve with the upstream contract

1. An application-submitted note creation invokes the existing Claude-backed workflow, returns the authoritative saved note and its resulting links, and survives reload.
2. A submitted point addition/replacement/removal uses that workflow with the correct note identity, version, old/new content and user intent. Proposed semantic changes and destructive effects are reviewable before confirmation where required.
3. A whole-note removal uses the explicitly approved archive/delete behavior. Tests verify inbound/outbound links, mentions, related hub listings and subsequent reads according to that behavior; the app does not invent its own cleanup.
4. A confirmed operation updates notes, relationship data, change history and derived map state consistently through the Brain owner. Reloading the editor displays committed state, not merely local recovery state.
5. Stale edits, duplicate retries, partial/unknown outcomes, model refusals, clarification questions, cancellations, timeouts and permanent-operation warnings have defined service responses and UI handling.
6. A transport-level test proves the model-backed workflow is invoked for submitted manual changes and that the deterministic HTTP fact routes are not silently substituted. It need not require a second model call merely to confirm an already reviewed plan unless the upstream contract specifies one.
7. Verify PostgreSQL authority and no live Markdown Brain-repository writes. If the stricter no-temporary-files interpretation is confirmed, its verifier must be supplied/approved by the Brain owner; changing only the source flag cannot establish that stricter property.
8. Use invented notes and an isolated database for automated write verification. Personal-data writes and source switching remain separate explicit actions after readiness review.

## Decisions not invented here

- Whether a multi-point Save is one Claude request or several; Save/Confirm processing must preserve the user's exact intent and avoid duplicate paid work.
- Resolved baseline from the original write/restore decisions: note deletion means archive with reference cleanup. Do not reopen hard deletion unless Manoj explicitly requests changing that behavior.
- Which service transport exposes the existing writer to the app, its authentication, request/response types, session ownership and retry guarantees.
- Clarify whether “no Markdown file in the middle” excludes the scratch workspace explicitly allowed by the database decision, or excludes only an authoritative Markdown note store. Elimination of temporary workspaces is not an already agreed migration requirement.
- Resolved baseline from the addition/approval decisions: Lia's additive placement/links can be included in the saved addition's summary and Undo. Changes/removals still need review. New non-obvious discovery remains separately gated, not a silent expansion of the editor's scope.
- Whether draft/preview/Undo metadata may keep the existing local support store; PostgreSQL-only Brain data must not be confused with an unapproved migration of every auxiliary service store.
