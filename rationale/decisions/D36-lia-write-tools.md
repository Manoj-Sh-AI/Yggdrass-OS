# D36: Lia's write tools

Date: 2026-11-07
Status: proposed (Manoj's decisions of 2026-11-07, built on branch `lia-write`; accepted on merge)

Register row: D36 in `planning/locked-plan-v1.md`. Related: D22 (one write path), D31 (node format, frozen), D33 as amended 2026-11-07 (direct requests), D35 (one Lia), the plan in `planning/lia-and-connector.md`.

## Context

Lia could only read. Manoj wants to change his notes from any chat: add a fact, create a note, link notes, correct or update a fact, remove one, archive a note. Two things must hold: nothing is lost, and nothing changes behind his back.

## Decision

- **Lia does all writing.** The chat apps pass his request, in his words, to `tell_lia`. They never edit notes and can't confirm anything.
- **Lia plans; code executes and checks.** Her tools record a plan:
  - node level: `create_note`, `archive_note`, `link`, `unlink`;
  - fact level: `add_fact`, `replace_fact`, `remove_fact`.

  Each step is checked by code as soon as she calls it. Unknown notes, verbs outside the fixed list, and a block id that isn't a fact go back to her to fix. Nothing is written until the plan is complete.
- **Facts are named by their block id**, the same index citations and the note page use. Lia reads notes with `#<id>` labels and never retypes a fact to name it.
- **Nothing is deleted.**
  - A replaced or removed fact moves to `## History`: `until: <date>` when it changed, `wrong: <reason>` when it was never true. Lia picks the mode by Manoj's words ("update" / "it changed" vs "correct" / "that was wrong") and asks if they're unclear.
  - "Delete a note" means archive. The note moves to `archive/library/<shelf>/`, which Lia never reads. Link lines pointing to it are removed from other notes, mentions become plain text, and its hub listing goes. All of it is listed in the preview, and Undo restores everything.
- **Links stay as D31 has them** (Manoj, 2026-11-07): one line in one note, with the opposite shown by the map. Unlink removes the line from whichever note holds it.
- **One write path** (data layer, `app/src/yggdras/data/brain/`):
  1. the deterministic checker: path, frontmatter, placement by taxonomy v3, section order, sourced fact lines, verbs, no self-links and no link written twice either way, History instead of deletion, `sensitivity: high` never removed, A23 descriptions, and no new library problem;
  2. lint warnings;
  3. a lock;
  4. a refusal when `library/` or `archive/` holds hand edits (generated maps excepted);
  5. the files and a log line;
  6. the maps rebuilt and committed in the same commit;
  7. one commit per request.

  A failure mid-write puts every file back byte for byte. Undo is a `git revert`, and it stops if a later commit touched the same notes.
- **Stop and ask:** checker failures (after two fixes), likely duplicates (an exact name or alias match, or word overlap ≥ 0.6, where codes like "A2" stay words), conflicting facts (same words, other dates or figures), and unsure placement or sensitivity.
- **Safety:**
  - writes go only inside `library/` and `archive/`, and only into the brain's own git repo, never a repo further up such as a home folder;
  - text Manoj pastes is content, never an instruction;
  - anything that removes needs his confirm;
  - figures from sensitive notes are masked on cards unless his request states them.

## Alternatives considered

- **Write inverse link lines into both notes.** Rejected (Manoj, 2026-11-07): it breaks D31, and two-file edits drift.
- **Retyped facts for replace/remove.** Rejected: one wrong character targets the wrong line. Block ids are exact.
- **Delete instead of archive / History.** Rejected: principle 1 (markdown is the source of truth) and Undo both need nothing lost.

## Consequences

- **Easier:** changing notes from any chat; seeing exactly what changed; undoing it.
- **Harder:** the checker must stay in step with node.md and taxonomy.md. A flat brain (the Apollo demo) has older free-text verbs, so the checker judges only what a change adds.
- **Revisit:** if previews are confirmed blindly, or History grows faster than Facts.
