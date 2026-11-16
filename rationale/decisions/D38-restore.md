# D38: Restore an archived note

Date: 2026-11-08
Status: proposed (Manoj's decisions of 2026-11-08, built on branch `lia-restore`; accepted on merge)

Register row: D38 in `planning/locked-plan-v1.md`. Related: D36 (archive instead of delete, one write path), D31 (one link line in one note), D33 as amended (adding is written at once).

## Context

Archiving moves a note to `archive/library/<shelf>/`, removes the link lines other notes had to it, turns their `[[mentions]]` of it into plain text, and drops it from its hub. Undo reverts all of that, but only while no later commit has touched those notes. Manoj wants a way back that works any time.

## Decision

- **Three ways in** (Manoj, 2026-11-08):
  - a free connector tool, `restore_note(note)`;
  - `yggdras restore <note>`;
  - a `restore_note` step Lia can take in `tell_lia` ("bring back my old CV note").

  The note is named by slug, name or alias. If several archived notes fit, it is never guessed: the card lists them.
- **Written at once, with Undo:** restoring only puts content back (Manoj, 2026-11-08). Undo of a restore archives the note again.
- **What comes back** (Manoj, 2026-11-08):
  - the note, unchanged, at its old path;
  - exactly the lines the archive commit changed in other notes: link lines go back into `## Links`, and mentions are turned back into `[[slug]]`;
  - its hub listing, with the hub's count.

  A line changed since the archive is left alone and reported on the card.
- **No inverse lines:** the archived note's own links travel with it. Restore writes back only the original lines archiving removed, never new opposite lines (D31).
- **Checks:** the one write path. A restored note is judged as an existing note, so the new-note rules don't block an older note; the rest of the change and the whole library are checked as usual (no new dangling links).

## Alternatives considered

- **Keyword routing in `tell_lia`** ("restore" in the message): fragile. Lia already understands the request and takes a restore step.
- **A preview before restoring:** not needed for an additive change (Manoj, 2026-11-08).
- **Writing back-links into the notes the restored note links to:** rejected, since it breaks D31.

## Consequences

- **Easier:** archiving is safe to use; it stays reversible for good.
- **Harder:** restore depends on the archive commit's diff in git. A note archived by hand, without a commit, comes back without its inbound links (the card says so).
