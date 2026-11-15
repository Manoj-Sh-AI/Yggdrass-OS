# Lia integration audit — Notes first

Read-only investigation, 2026-11-12, following Manoj's clarified requirement for actual Claude processing of manual editor changes. No application/Brain code, configuration, database contents, source mode or model behavior was changed by this audit. This draft and its companion requirements record the result for review.

**Authority reconciliation:** subsequently read the original approval/write/restore/database decisions and their amendments. See `requirements/notes-crud-decisions-reconciled.md`. The database plan explicitly allows a scratch copy of rows: temporary workspaces are a documented compatibility choice, not an unplanned implementation defect. Literal elimination of all temporary note files is a stricter interpretation of the new voice requirement and needs clarification. Archive (rather than hard-delete), additive immediate save, confirmation for changes/removals, and permanent fact removal/unlink are already decided baselines; earlier open questions below are historical where superseded by the reconciled record.

**Latest user direction:** `requirements/notes-save-then-lia-review.md` now records direct manual save followed by separate Lia review. The synchronous editor → model-backed writer proposal below is historical. The user is handling Markdown-file removal/backups; application work must integrate the approved database save and post-commit review boundary without redesigning memory internals.

## Verified implementation, not assumptions

The inspected sibling checkout is `Yggdrass-OS-main`. Paths below are relative to that checkout unless marked application.

| Layer | Existing implementation | Consequence |
| --- | --- | --- |
| App reads | Application `app/api/src/yggdress_app/notes_proxy.py` delegates to authenticated Brain HTTP search/note reads | Dedicated Notes reads the configured PostgreSQL-backed Brain API; the earlier live check returned 82 notes. This is not an independent migration-parity audit. |
| App saves today | `interface/brain_api.py` calls `data/brain_db/writes.py:BrainWrites` | These routes perform deterministic checked fact/link operations, not Claude-backed semantic planning. The current editor adapter therefore does not yet satisfy the clarified requirement. |
| Live write gate | `BrainWrites._open()` checks the selected source | A preview-only request against a nonexistent diagnostic note returned the Markdown refusal during this audit. No real note was targeted or modified. Database migration alone has not enabled this running server's writes. |
| Model-backed writes | `processing/lia/write.py:WriteSide.tell()` runs its model/tool loop and plans create/add/replace/remove/link/unlink/archive/restore operations | Reuse this existing behavior rather than adding another linker or model tool implementation in application code. |
| Service entry point | `interface/mcp_server.py:LiaService.tell()`, exposed as the `tell_lia` MCP tool | A model-backed request path already exists. The inspected HTTP router does not expose the same workflow; the app needs an agreed bridge/transport contract. |
| Database-backed writer selection | `interface/writing.py:row_write_side()` instantiates the existing WriteSide/IngestSide with RowStore; LiaService chooses this when initialized with rows | There is already a way to retain Lia's model behavior while using PostgreSQL as the Brain owner. Selecting it in the running service is a separately reviewed readiness/configuration step. |
| Human review | WriteSide produces summary/preview/question/refused/message cards; MCP exposes confirm/cancel/Undo | The app must represent these outcomes and preserve token ownership and original reviewed versions. Some additive plans currently commit before returning a summary; do not pretend all calls are side-effect-free previews. |
| Whole-note removal | `data/brain/ops.py:Builder.archive_note()` removes references from other notes, adjusts hub listings and unwraps mentions, then archives the node | Existing behavior is archive, not an approved hard-delete contract. Do not add raw application SQL deletion or different semantic cleanup. |
| Graph/database consistency | `data/brain_db/store.py:RowStore._transact()` checks versions, updates derived rows/history and rebuilds map cache in one transaction | Use the existing owner transaction and return/refetch authoritative state; do not synchronize a separate application-owned graph. |
| No-file requirement | `RowStore.refresh()` materializes a temporary Markdown workspace. `_transact()` also materializes a temporary workspace and reads it back before synchronizing SQL | PostgreSQL is authoritative in rows mode, but the inspected implementation still has intermediate Markdown files. A source-mode switch alone cannot meet the literal clarified requirement. This work belongs to Claude's Brain ownership. |

Archive/restore and relationship consistency cases exist in `app/tests/test_brain_rows.py`, including removal from note reads/maps and restoration of prior links. These test cases were inspected, not rerun as part of this audit; do not confuse them with a fresh verification of the proposed integration.

## Proposed integration boundary

1. Editor submits the user's intended operation and fetched note/version through the application backend. Preserve the editor's current appearance and local failure recovery.
2. Backend invokes the existing Lia service's Claude-backed workflow through an approved authenticated transport. Do not import/rebuild the memory engine in the application service or issue direct model-generated SQL.
3. Lia owns retrieval, semantic planning, duplicate/conflict questions, validation and relationship changes. Actual Anthropic calls stay in Lia's existing model client, not in the browser.
4. App renders the service's actual outcome. Where review is required, show affected facts/nodes/relationships and warnings and send the original service confirmation token back; do not create a second incompatible confirmation system.
5. The Brain owner commits approved changes to PostgreSQL and supplies affected slugs/versions/outcome. The app refreshes notes, backlinks and relevant graph data through that owner. No optimistic success claim before acknowledgement.
6. Test the complete note lifecycle on invented data before any application-driven personal-data writes. Keep tasks, Calendar, agents and orchestration outside this slice.

This is a proposed contract, not an implemented transport or a claim that every semantic relationship is discovered. The model may ask questions or decline; the interface must show that result accurately.

## Smallest next independently testable task

Agree and exercise one app-to-Lia **point-addition** request on an invented PostgreSQL note: prove that the existing Claude-backed workflow is invoked, represent its returned card/confirmation, acknowledge persistence and reload the note plus affected relationships. Add a transport fixture first; do not use real notes or silently fall back to deterministic writes.

Before claiming the requested end-to-end behavior, resolve the upstream no-intermediate-files implementation and the database-source readiness gate. Before whole-note removal, resolve archive versus permanent delete. An HTTP wrapper around an existing mutating workflow must also specify safe retry and pending-request semantics before it can be used by the editor.

## Ownership and tradeoffs

- Reusing Lia trades service/model latency and cost for consistent reasoning and one owner of semantic relationships. A separate application model path would duplicate engine behavior and is rejected by the existing ownership boundary.
- A bounded, versioned service contract favors consistency and maintainability over a quick source-switch workaround. The current low-level fact API can remain for its existing clients but cannot stand in for the newly required model step.
- Requiring literal absence of temporary Markdown files is stricter than PostgreSQL being authoritative. Treat the distinction explicitly; do not conceal a filesystem-based planning/checking path behind the word “database.”

## Engineering assessment and recommended order (review, not implementation approval)

The existing core is worth retaining: model plans are checked by deterministic operations, destructive changes require review, versions prevent stale overwrites, and RowStore commits note/relationship/history/map changes together. Archive reference cleanup is implemented centrally rather than delegated to the UI. This assessment is based on inspected code and existing test cases, not a new live evaluation of semantic-link quality.

The PostgreSQL port is still a compatibility implementation: it materializes note files for planning/checking, and `_transact()` materializes a snapshot while holding its transaction/advisory lock. In `RowStore.sync()`, only changed catalogue/body values receive updates, but areas, aliases, dated items and relationships are rebuilt over all live notes. This preserves the older derivation semantics but adds filesystem/whole-Brain work to an individual edit; it should not be described as fully incremental database-native persistence.

Recommended sequence, subject to review:

1. Connect the application to the existing model-backed workflow with explicit request identity, version, original user edit, status and authoritative outcome. A submitted Save can run Lia's tool workflow; do not equate every keystroke with a paid request. Model-suggested extra changes must remain distinguishable from the user's literal edit.
2. Have the Brain owner replace temporary-file adapters with an equivalent approved no-file path. Preserve checker/link/undo semantics and migration parity; application code must not perform this rewrite.
3. Define archive versus permanent delete, fact-removal/history semantics, and relationship cleanup as one consistent service contract. The low-level HTTP fact API and Lia's higher-level operations have different behavior; exposing both without explicit routing is not a coherent editor contract.
4. Make persistence/derived updates incremental over the affected note set and relevant neighbours under the Brain owner's design. Keep atomicity and stale-version protection. Do not independently implement graph maintenance in the application backend.
5. Prove a Notes-only vertical slice before tasks/Calendar: exact manual-edit preservation, model workflow invoked, expected related/unrelated link cases, creation, point changes, archive cleanup, cancellation, stale versions, retry/timeout outcomes, authoritative reload and no temporary note files. Structural graph consistency is distinct from semantic relevance; test both and do not infer semantic correctness from foreign keys or a successful commit.

Expose Lia's existing status/trace/cost outcomes through the agreed application boundary where useful. This is an integration/observability recommendation, not a new application-owned reasoning engine or approval to run real model/write tests.
