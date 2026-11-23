# Notes CRUD — recovered decisions, not a new design

2026-11-12. Manoj asked application engineering to read Claude's recorded plans before reopening requirements questions. This reconciles the inspected implementation with the written decisions in the sibling `Yggdrass-OS-main` checkout. It changes no code, service configuration, source mode or stored Brain data.

## Authority and scope

- Use Manoj's latest explicit instructions, followed by the decision register and its dated amendments. Older draft-plan paragraphs are historical where superseded.
- Primary records read: `rationale/decisions/D33-button-first-approval.md`, `D35-one-lia.md`, `D36-lia-write-tools.md`, `D37-uploads.md`, `D38-restore.md`, `D43-brain-postgres-schema.md`, `D44-database-is-the-brain.md`; relevant `planning/locked-plan-v1.md`, `lia-and-connector.md` and `maps-design.md` sections.
- The database decision takes effect at its approved switch, after its parity gate and off-PC full dump. The running API was observed still refusing writes in Markdown mode. A documented target is not evidence the switch is complete.
- Latest voice clarification requires actual Claude processing for manual editor submissions. Reuse Lia's writer, preserving its separation between model-planned operations and deterministic relationship-row derivation. Do not build a second semantic engine or send SQL directly from a model.
- Notes first; tasks, Calendar and orchestration remain outside this slice.

## Questions already answered by the records

| Operation / concern | Recorded behavior to carry forward | Authority |
| --- | --- | --- |
| Add a new note | The user's explicit request approves adding. Lia plans placement, descriptions and links; code checks the plan; additions save with a summary and Undo. No extra confirmation is required solely because it is a new note. | Direct-request amendment; write tools |
| Add a point | Same additive flow, with provenance and duplicate/conflict checks. A conflicting fact stops for clarification instead of silently overwriting. | Direct-request amendment; write tools |
| Replace a point | Show before/after and required confirmation. Use the exact selected fact identity/version. Old text belongs in database change history after the database switch, not a persisted History section. | Write tools, amended by database decision |
| Remove a point | Preview and explicit confirmation, with a clear irreversible warning. Erase with no copy kept; no Undo. Older “move removed facts to History” text is superseded. | Database decision |
| Delete a whole note | “Delete” means archive under the existing design. Remove its active references: link lines, linked mentions and hub listing; retain the note for restore. Display the affected changes before confirmation. Do not invent hard deletion as a replacement. | Write tools; restore; database decision |
| Restore a note | Additive, immediate with summary/Undo. Restore the note and the references that archiving removed. Leave subsequently edited lines alone and report them. Ask if the archived identity is ambiguous. | Restore, adapted to database changes |
| Add a relationship | Lia can plan an evidenced relation using the approved verbs; code validates and derives the stored edge. Store one relationship direction and derive the inverse view; never duplicate inverse rows. Addition has summary/Undo. | Frozen node/link rules; write tools; database amendment |
| Remove a relationship | Preview/confirm, then permanent unlink without retained copy or Undo. This latest amendment supersedes earlier reversible-unlink choices. | Latest database amendment |
| Notes and relationships | PostgreSQL owns Brain data after switch: catalogue, bodies, areas/aliases, relationship rows, change records and cached maps. App data remains separately owned. Note bodies may retain the existing text format within a database value. | Database schema/loader and database-is-the-Brain decisions |
| Atomic save | One owner transaction per Lia request, updating note data, derived rows, changes and map cache together, with stale versions refused. Refresh authoritative state in the editor after acknowledgement. | Database decision |
| Undo | Reverse a reversible request from database records. Reject already-used Undo, irreversible operations, and unsafe reversal after later changes. Undo cannot itself be undone. | Database decision and API amendment |
| Approval authority | The user operates Confirm/Cancel/Undo. The model must not confirm its own proposal or receive app-only confirmation capabilities as writable tools. | Approval and write-tool decisions |
| Lia uncertainty | Ask instead of guessing on duplicate notes, conflicts, placement/sensitivity ambiguity and unresolved checker failure. Some outcomes are questions/refusals, not saved notes. | Approval and write-tool decisions |
| Link quality | Link where content supports the relation. Non-obvious discovery between existing notes is separate gated work; editing Notes does not authorize a new discovery engine. | Connector plan; upload/linking decisions |
| Sensitive content | Preserve sensitivity protections; hide sensitive details in cards/summaries unless explicitly revealed according to the existing rules. Pasted/uploaded content is data, not instructions. | Approval, write-tool and upload decisions |
| Files uploaded later | Reuse the existing ingest workflow, raw-source retention and provenance rules; do not reinterpret this as generic attachment ingestion now. Raw uploads are distinct from note persistence. | Uploads; database adaptation |

This resolves the earlier open questions about add-first versus review-first, archive versus whole-note hard deletion, replacement history, permanent fact removal, permanent unlink and restore behavior. Do not re-ask these unless Manoj explicitly wants to change the recorded behavior.

## One material wording difference still needing clarification

The database decision explicitly runs the existing planner/checker on a **scratch copy of the rows**. The implementation materializes temporary Markdown files for that purpose, then commits PostgreSQL data. The original Markdown Brain repository is frozen and is not the live source after the switch.

Manoj's newer phrase “no Markdown file in the middle” could mean:

1. No authoritative/persisted Markdown note store or file-based synchronization, while the already documented temporary scratch workspace remains an internal implementation detail; or
2. No temporary Markdown workspace either, which is a stricter new requirement needing a change within Claude's Brain ownership.

Do not present the scratch workspace as an unplanned defect in the recorded migration design. Equally, do not claim zero intermediate files when the implementation still creates them. Clarify only this distinction if it affects the next approved integration step.

## Engineering dependencies, not questions to make Manoj redesign Lia

- Agree a transport around the existing model-backed request and card lifecycle. Today's low-level HTTP fact routes do not themselves invoke Claude.
- Map editor gestures and fetched versions to Lia's exact operations without silently turning Remove into Replace, retaining removed text contrary to policy, or changing user facts beyond the reviewed request.
- Preserve source-switch prerequisites and verify readiness with the Brain owner before enabling personal-data writes.
- Reuse established model configuration, placement, fixed verbs, prompts, validation, history and restore semantics; do not choose new policies in application code.
- Test a Notes-only vertical slice with invented data: real model workflow boundary, additive save, replace confirmation, permanent-remove warning, archive/reference cleanup, restore, conflict/refusal, Undo, refresh and retry outcomes.

No implementation approval, source switch or live-data write is implied by this reconciliation.
