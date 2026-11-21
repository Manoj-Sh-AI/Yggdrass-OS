# D43: The brain in local PostgreSQL (schema and loader only)

Date: 2026-11-11, amended 2026-11-12
Status: proposed (Manoj's spec of 2026-11-11 and his fixes of 2026-11-12, built on branch `brain-postgres`; accepted on merge)

Register row: D43 in `planning/locked-plan-v1.md`. Related: D1 (markdown is the source of truth), D13 (never a cloud-queryable store), D31 (one link line in one note), D34 (Lia reads maps, opens notes to cite). Numbered D43 because D38 (restore, PR #42) and D39–D42 (the app drafts) are taken.

## Context

The maps are rebuilt from the files on every change. Manoj wants the brain in PostgreSQL, so that shelves, links and dated items can be queried, while Lia keeps reading prebuilt map text. This step is the schema and a loader only: Lia's reading and writing are unchanged.

## Decision

- **Where the database runs** (Manoj, 2026-11-11): a PostgreSQL on this PC, reached through `BRAIN_DATABASE_URL` in `.env`. D13 stands unchanged. Hosting is a separate, later decision.
- **D1 stands:** the tables are derived. The loader wipes and refills them from the markdown, and the markdown stays the thing that can't be lost.
- **The schema** (Manoj's spec), all in schema `brain`:
  - the catalogue (`notes`) and the text (`note_bodies`) apart, so a shelf read never pulls bodies;
  - `changes` never cascades: a deleted note's history stays, with `slug` set to null;
  - versioned up/down migrations: 0001 (the nine tables), 0002 (the fixes below).
- **Maps:** Lia reads them from `map_cache`. Each map is rendered from rows ordered byte-wise (`COLLATE "C"`). `map_version` is a hash of the text, so it changes when, and only when, the text does. On a well-formed brain, the rendered maps are byte-identical to the markdown-built ones, apart from `map_version`.

Fixes of 2026-11-12 (Manoj), in migration 0002:

- **A note in several areas:** `note_areas` (slug, area_code, is_primary, ord) replaces `notes.also_area`.
  - Each note has exactly one primary area, equal to `notes.area_code`. This is checked at commit.
  - A note may have any number of secondary areas.
  - `area: cross` is a real area, `09-cross`. The maps still show it as today: a `## cross` section and the registries' cross-area count, not an atlas row.
  - The loader never drops a note for its area. An area value that fits no area stops the whole load, and nothing is written.
- **Dates inside fact lines** are loaded by the upcoming view's own code. History lines and hubs are left out, as today. The kinds: a fact date becomes `event`, a `valid:` start becomes `start`.
  - The report checks that every item today's upcoming code finds (over all dates, not just the next 120 days) is in `dated_items`.
- **Mentions** are stored as relationships with verb `mentions` and kind `mention`. The loader adds the verb (inverse `mentioned_in`), which the code already defines.
- **Alias order:** `aliases.ord`; the maps render aliases in the order they are written.
- **Chunks:** `notes.parent_slug` → notes, nullable, ON DELETE SET NULL, deferred. It is read from the chunk's folder (`13-sources/<parent>/`), as the markdown maps read it.

Choices made while building, open to Manoj's review:

- **`note_areas.ord`** keeps secondary areas in written order (the `A:` flag shows them in that order). This column was not in the 2026-11-12 spec.
- **A missing `area`** loads as `cross`, as today's maps read it, and is reported.
- **`shelf_no`** is the number of the note's folder (`11` for `11-people/`). It is display and sort only, and drives the atlas registries line.
- **`note_bodies.body`** holds the whole file, frontmatter included, so fields without a column (`id`, `created`, `pages`) are not lost.
- **Inverse verbs:** a link line written with an inverse verb (`has_part`) is stored once, the other way round (`part_of`). There is one row, as D31 asks.
- **Verbs** are read from the brain's verb table in `00-manual/node.md`; `mentions` is the only verb added.
- **History survives a reload:** the loader never wipes `changes`, and it re-attaches the rows by `slug_text`.
- **Copy guard:** the loader refuses the path in `YGGDRAS_BRAIN`, and refuses outright when that isn't set, unless `--real` is passed.

## What still does not fit (listed by the loader, never forced in)

Only malformed input:

- an alias that another note already has;
- a `review` or `decided` value that is no date;
- a chunk whose folder names no note;
- links to missing notes, self-links and unknown verbs.

Only these make the rendered maps differ from today's.

## Consequences

- **Easier:** the brain can be queried by shelf, area, link or date. The maps have a cache with an exact version.
- **Harder:** two copies of the brain must agree, so the loader's count report is the check.
- **Area 09:** `structural.py` keeps 09 "free for a future area"; `cross` now takes that code in the database.
