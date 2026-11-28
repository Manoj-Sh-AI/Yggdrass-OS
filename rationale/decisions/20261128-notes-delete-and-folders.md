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
- Not done: free folders. The shelf numbering and the graph read the fixed list in code
  (`store.py` `SHELF_FOLDERS`, `structural.py` `SHELVES`), and an empty folder needs a place
  to exist: a `brain.folders` table, i.e. a brain-schema migration on the hosted brain.
  There is no hosted brain migration tool yet (Phase 3 of the OS plan); applying one needs
  Manoj's go-ahead.
