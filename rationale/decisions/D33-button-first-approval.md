# D33: Button-first approval

Date: 2026-11-01
Status: accepted (Manoj, 2026-11-01)

Register row: D33 in `planning/locked-plan-v1.md`. Related: D8, D12, D22, D23 and D27 (amended the same day), and the plan in `planning/lia-and-connector.md`.

## Context

Knowledge will reach the brain from several chat apps (Claude desktop and web, Claude Code, Codex, later the phone): lasting facts spotted in conversation, pasted text and uploaded files. Principle 4 says nothing enters without approval. The first plan had Lia draft a full proposal (notes, links, diff) for Manoj to approve. That costs a model call for every candidate, including the ones he rejects, and puts a large diff in front of him every time.

## Decision

- **Approval comes first, on the candidate itself.** Every candidate is shown on a card with Approve and Reject. No model is called before Approve.
- **Reject** is logged in local SQLite and costs nothing.
- **Approve** is the only path to Lia's write side. Lia then chunks, places, describes and links; runs the deterministic checker and lint; writes; commits in the brain repo; and returns a summary card with Undo (a `git revert`).
- **Lia stops and asks** with a second card instead of writing on a checker failure, a likely duplicate (an exact name or alias match, or token overlap ≥ 0.6), a conflicting fact, or an unsure placement (more than one plausible shelf, or the placement rule fails).
- **Approve, the second-card answers and Undo are never model-callable:** app-only MCP Apps buttons, a Claude Code elicitation form, or the `yggdras` CLI.
- **Limits:** one card per reply; uploads capped at 5 MB.
- **Sensitive notes:** keep `sensitivity: high`, and their hidden parts never appear on cards or summaries unless Manoj presses Show.

## Alternatives considered

- **Proposal first:** Lia drafts, Manoj approves the full diff. Every placement and link is reviewed before the write, but every candidate costs a model call (rejects included) and there's a large review each time.
- **Write first, review later** (Basic Memory, Mem0, Letta, the Karpathy LLM wiki): no friction, but it breaks principle 4.

## Tradeoffs

- **Gives up:** review of Lia's placement and links before they are written. A wrong-but-valid link can sit in the brain, and be cited, until Manoj reads the summary or presses Undo.
- **Gains:**
  - cost (rejects are free);
  - simplicity (one click per candidate);
  - consistency (every write is checked by free code, and every change is one revert away).

## Consequences

- **Easier:** capturing facts from any app; rejecting noise; undoing a mistake.
- **Harder:** link quality rests on Lia and the checker, so it must be measured before the write side is switched on (pass bars T5, T7, T11, T12), and Undo must stay safe when later commits touch the same notes (T4).
- **Revisit:** if Undo is used often, approving the candidate alone is letting too many wrong links through.

## Amendment 2026-11-07: direct requests

Decided by Manoj on 2026-11-07, for the first write round (D36):

- **Manoj's own words are the approval for adding.** When he asks in a chat to create a note, add a fact or add a link, Lia writes it at once and returns a summary card with Undo. No Approve card comes first.
- **Changing or removing waits for a confirm.** Replacing or removing a fact, unlinking and archiving a note show a before → after preview, written only after he confirms it. The preview is held in local SQLite (D12) and expires after 24 hours.
- **Confirm, cancel and Undo stay out of the model's reach:**
  - in Claude Desktop, MCP Apps buttons on the card; the tools are app-only and need the card's token, which travels only in the result's `_meta`;
  - in Claude Code, a form (elicitation) inside `tell_lia`;
  - anywhere, `yggdras confirm`, `cancel` or `undo` in a terminal.
- **Stop and ask still holds**, with a question card and nothing written: a checker failure after two tries, a likely duplicate, a conflicting fact, or unsure placement or sensitivity. Manoj answers in his next message.
- **Later rounds:** cards for facts Lia spots in conversation (the button-first flow above), and uploads for ingest.

**Why:** a fact Manoj states himself needs no second click, and adding is always one Undo away. Changing or removing loses the current line from Facts, so it waits for him. Even then nothing is deleted: the line goes to History.

