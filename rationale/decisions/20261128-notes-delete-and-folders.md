# Notes app: delete is permanent; folders are free; maps stay code-built

Date: 2026-11-28. Decided by Manoj (in-session answers), recorded by Claude.

## Decisions

1. **Deleting a note is permanent** (chosen over "archive + undo"). Amends D36 ("nothing
   deleted; archive instead") and D44's archive-only removal for whole notes.
   - A preview comes first: the title and the notes that link to it.
   - In one transaction the note's row goes, with its body, links, aliases and dates
     (`ON DELETE CASCADE`). In other notes, a `## Links` line pointing at it is dropped and
     any other `[[slug]]` becomes plain text (its title), so no link points at a gone note.
   - History keeps only the title (`brain.changes`, kind `remove`): no copy of the text.
     No undo id is issued.
2. **Folders are fully free** (chosen over sub-folders inside areas, or tags). Manoj can
   create and delete folders like in a note app. Amends A1 and A17 (the fixed folder list
   in code, frozen numbers) and the frozen node format D31 where it names folders.
3. **Deleting a folder moves its notes to the Inbox** (chosen over "only empty folders" or
   "delete the notes too").
4. **The graph and Lia's maps update by code, not by a model.** Every brain write already
   rebuilds `brain.map_cache` inside its transaction and re-renders the graph after it
   (principle 3: obvious is free). Delete follows the same path.

## Status

- Done (branch `claude/20261127-phone-batch-2`): permanent note delete end to end (brain,
  proxy, web), with tests.
- Done (branch `claude/20261128-free-folders`): free folders, as **areas**. In the app a
  folder is what the Notes list shows under "Shelves & areas": a note's `area`. So a new
  folder is a new `brain.areas` row numbered from 20 (`20-swimming`), and no schema
  migration is needed (`brain.areas` already takes any two-digit code and name; folder
  history is a `brain.changes` row with section `folder` and no slug).
  - The area rules (`structural.areas()`, the checker, the loader, placement) accept the
    user's folders; the row store reads them from `brain.areas` with every snapshot, so the
    check inside each write's lock sees the current list.
  - A note in a user folder sits on shelf `10-ideas` when its type has no shelf of its own
    (shelf_no is display and sort only; the folder is the area). [derived]
  - Removing a folder: only the user's own (20-99). The life areas 01-08 and cross can't
    be removed: they are the taxonomy Lia's manual describes. Its notes move to **cross**,
    the catch-all area, in the same transaction (`area:` rewritten; dropped from `also`).
    "Inbox" was read as cross: the `14-inbox` shelf is left out of the graph and Lia's
    maps, so notes moved there would vanish from answering. [derived; Manoj to confirm]
  - Not built: renaming a folder, moving a note between folders.
