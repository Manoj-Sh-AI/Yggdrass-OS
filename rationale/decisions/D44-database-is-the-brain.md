# D44: The local database is the source of truth for the brain

Date: 2026-11-12
Status: proposed (Manoj's ruling of 2026-11-12; built on branch `brain-rows`; takes effect at the switch, which waits on the parity gate and the dump below)

Supersedes D1. Amends D31 and D36 (History sections retired) and big-picture principle 1. D13 is unaffected: the database stays local, and hosting remains undecided. Builds on D43 (schema and loader) and D38 (restore).

## Decision (Manoj, 2026-11-12)

- **The database is the brain.** From the switch, Lia reads and writes rows, and nothing writes markdown.
- **The markdown files** are frozen at the switch and kept on disk as a rollback option for the first days only. They are NOT a backup: they stop reflecting the brain at the first write after the switch.
- **Condition:** a full database dump exists before the switch, held outside this PC. A manual dump is acceptable; having none is not.
- **History sections are retired** (amends D31 and D36):
  - a replaced fact's old text lives only in `changes` (kind `replace`);
  - Remove erases with no copy kept, and its preview says in plain words that it cannot be undone;
  - the loader turns existing `## History` lines into `changes` rows (`until:` → replace, `wrong:` → remove) and strips them from the note body;
  - the shelf map's H flag comes from `changes` and renders the same bytes as today.
- **Generated files** (the graph viewer) go to `local-data/brain-view/` and are served at `127.0.0.1:8765/graph`. The brain repo is never touched.
- **The parity gate** runs right after the load, before any write.

## How it is built

- **Reading.** `RowLibrary` reads one snapshot:
  - the live notes' bodies (`archived_at` is null);
  - their History, rendered back from `changes`;
  - the maps from `map_cache`, never a live query at question time;
  - the manual from its own table.

  Lia's tools (`open_note`, `search_notes`, citations, every check) are unchanged and receive the same text. On a copy of the real brain, all 82 notes give identical text and citable lines, and all 82 name searches return identical results.
- **Writing:** one transaction per request.
  - The planner and the checker run unchanged on a scratch copy of the rows.
  - The save writes the bodies and re-derives every row with the loader's parser.
  - It appends one `changes` row per changed line, with its place, so Undo rebuilds the note exactly.
  - It rebuilds `map_cache` in the same transaction.
  - A note whose version moved since it was read is refused ("reload and review").
- **Undo** reverses one request from its rows.
  - It refuses a request that removed a fact: removal is permanent, by design.
  - It refuses when later requests touched the same notes.
  - An Undo can't itself be undone.
- **Restore** (D38) works from rows: it puts back exactly the lines the archive's `changes` rows took from other notes.

Choices made while building, open to Manoj's review:

- **Migration 0003** adds `changes.request_id`, `section`, `pos` and `tag`, a `changes` kind `unlink`, and a `manual` table. An unlinked line keeps its text, so unlink can be undone; only Remove is final.
- **The imported History section** is kept verbatim, in one extra `changes` row with section `## History`, so Lia reads each note byte for byte as before.
- **An app edit** (`write_note`) that changes a fact counts as a replace: the old text goes to `changes`.
- **Raw uploads** go to `local-data/brain-raw/raw/`; the source note records `raw/<name>` as before.
- **`00-manual/log.md`** is no longer written: `changes` is the log.
- **The switch** is `YGGDRAS_BRAIN_SOURCE=rows`; the default stays `markdown` until the gate passes and the dump exists.

## Consequences

- **Easier:**
  - writes are atomic;
  - there's a single history;
  - Undo no longer depends on git;
  - the app has endpoints it can use.
- **Harder:**
  - losing the database means losing the brain, hence the off-PC dump;
  - the markdown fallback goes stale at the first write;
  - removal is final.

## Amendment 2026-11-12: the app's write API (Manoj)

- **Routes:** the brain API (`interface/brain_api.py`) serves `/api/` on the note server at 127.0.0.1. Every route, read or write, needs HTTP Basic Auth (`BRAIN_API_USER`, `BRAIN_API_PASSWORD`). Without both, the API does not start; Lia and the note pages start anyway.
- **Writes:**
  - add note, add fact and link are written at once, with an `undo_id`;
  - replace previews, then writes, with an `undo_id`;
  - remove fact and unlink preview, then erase for good.
  - Undo records live in a new table, `brain.undo` (migration 0004). An Undo can be used once: 409 when reused, 404 when unknown, 400 for remove and unlink, which are permanent.
- **Unlink is permanent everywhere**, for Lia too: no copy is kept, and there is no Undo. This replaces the earlier choice that kept unlinked lines.
- **D31 stands:** a link is one row, one direction. The link preview shows how the reverse reads (its inverse verb) but never writes it, and `back_link` is ignored.
- **Text is the truth:**
  - a link is a line in its note, and link detection is the loader's regex derivation, never a model;
  - a replace that drops a `[[link]]` lists it in the preview, and the row goes with the line on Confirm.
- **Before the switch:** API writes return 409 until `YGGDRAS_BRAIN_SOURCE=rows`. The markdown is still the truth, and a reload would erase them.
