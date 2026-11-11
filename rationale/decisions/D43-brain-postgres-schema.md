# D43: The brain in local PostgreSQL (schema and loader only)

Date: 2026-11-11
Status: proposed (Manoj's spec of 2026-11-11, built on branch `brain-postgres`; accepted on merge)

Register row: D43 in `planning/locked-plan-v1.md`. Related: D1 (markdown is the source of truth), D13 (never a cloud-queryable store), D31 (one link line in one note), D34 (Lia reads maps, opens notes to cite). Numbered D43 because D38 (restore, PR #42) and D39–D42 (the app drafts) are taken.

## Context

The maps are rebuilt from the files on every change. Manoj wants the brain in PostgreSQL, so that shelves, links and dated items can be queried, while Lia keeps reading prebuilt map text. This step is the schema and a loader only: Lia's reading and writing are unchanged.

## Decision

- **Where the database runs** (Manoj, 2026-11-11): a PostgreSQL on this PC, reached through `BRAIN_DATABASE_URL` in `.env`. D13 stands unchanged. Hosting is a separate, later decision.
- **D1 stands:** the tables are derived. The loader wipes and refills them from the markdown, and the markdown stays the thing that can't be lost.
- **The schema** (Manoj's spec), all in schema `brain`:
  - nine tables;
  - the catalogue (`notes`) and the text (`note_bodies`) apart, so a shelf read never pulls bodies;
  - `changes` never cascades: a deleted note's history stays, with `slug` set to null;
  - migrations in versioned up/down files.
- **Maps:** Lia reads them from `map_cache`. Each map is rendered from rows ordered byte-wise (`COLLATE "C"`). `map_version` is a hash of the text, so it changes when, and only when, the text does.

Choices made while building, open to Manoj's review:

- **`shelf_no`** is the number of the note's folder (`11` for `11-people/`). It is display and sort only. It drives the atlas registries line.
- **`note_bodies.body`** holds the whole file, frontmatter included. Fields without a column (`id`, `created`, `pages`, extra `also` areas) are therefore not lost.
- **Chunks** have no path column. A chunk is a sources-shelf note with `pages` (the format allows pages on chunks only), and its parent is the note it is `part_of`.
- **Inverse verbs:** a link line written with an inverse verb (`has_part`) is stored once, the other way round (`part_of`). There is one row, as D31 asks.
- **Verbs** are read from the brain's own verb table in `00-manual/node.md`. None are invented.
- **Dated items** come from the frontmatter only: `date` → event, `start`, `end`, `review`, `decided`. Dates inside fact lines are not loaded; they would need a mapping to these kinds.
- **History survives a reload:** the loader never wipes `changes`, and it re-attaches the rows by `slug_text`.
- **Copy guard:** the loader refuses the path in `YGGDRAS_BRAIN`, and refuses outright when that isn't set, unless `--real` is passed.

## What does not fit yet (listed by the loader, never forced in)

- **Notes of area `cross`:** `areas` holds 01–08 and `area_code` is required. These notes are not loaded, and neither are their links and aliases.
- **`[[mentions]]`:** the verb list has no verb for them, so they are not stored. Today's relationship map shows them.
- **Aliases:** they have no order column. The maps list them alphabetically; today they keep the written order.

## Consequences

- **Easier:** the brain can be queried by shelf, link or date. The maps have a cache with an exact version.
- **Harder:** two copies of the brain must agree, so the loader's count report is the check. Before Lia reads from rows, the three gaps above need a decision.
