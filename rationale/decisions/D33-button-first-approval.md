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
