# D02: Node identity and schema

Date: 2026-10-24
Status: accepted (2026-10-24), frozen 2026-10-24 (D31), amended 2026-10-31 (A1–A8, then A9–A21, below)

Register row: D2 in `planning/locked-plan-v1.md`. Related: D1 (markdown is the source of truth), D29 (type enum), the provenance rule under "Node schema".

## Context

Every later phase depends on the node format: Graphiti extracts from it (1b), the connector validates it (2), agents write to it (3–4). The format has to stay parseable by a model without ambiguity, and editable by hand in any text editor. Build order step 2 requires writing it down before the first node exists.

Identity is the part that is expensive to change later. If links point at file paths or names, every rename breaks them.

## Decision

**Identity.** Each node has a UUID v4 in frontmatter (`id`). It never changes and is never reused. The filename and `slug` are labels: renaming a node changes its slug and filename, and the old slug moves to `aliases`. Links resolve slug or alias → index → uuid → path, and `index.md` lists each node's aliases next to its description, so a renamed or merged-away slug keeps resolving.

**Normalization.** Aliases are stored as written, for name matching. Resolution and uniqueness checks normalize both sides first, in this order:

1. Lowercase.
2. Unicode NFKD, then strip combining marks (`ü` → `u`, `é` → `e`).
3. Map the letters NFKD leaves alone: `ß` → `ss`, `ø` → `o`.
4. Runs of spaces and underscores become one hyphen.
5. Drop punctuation: anything that is not a letter, digit or hyphen.
6. Collapse runs of hyphens into one, and trim hyphens from both ends (`Power BI - Reports` is `power-bi-reports`). An alias that normalizes to an empty string is invalid.

`Bank Work`, `bank work` and `bank_work` are all `bank-work`; `Universität` is `universitat`, `Straße` is `strasse`, `Master's thesis` is `masters-thesis`. No per-language transliteration (`ü` → `ue`): it breaks on the first non-German accent. Normalization is for matching only; the alias is displayed exactly as written.

**One file per subject**, one subject per file, under about 50 lines. A node lives in exactly one folder: `people/`, `areas/`, `topics/` or `sources/`. Chunks live under their source folder (`sources/<source-slug>/`), with slug `<source-slug>-ch-<nn>`, so the filename still equals the slug and stays unique across sources.

**Frontmatter fields:**

| Field | Type | Required | Rule |
|---|---|---|---|
| `id` | UUID v4 | Yes | Set once, never changes |
| `slug` | kebab-case | Yes | Unique across the brain; matches the filename |
| `name` | string | Yes | Human title, as said aloud |
| `type` | enum | Yes | `person`, `area`, `topic`, `source`, `chunk` (D29) |
| `description` | one line | Yes | Written as a search snippet; copied into `index.md` |
| `created` | ISO date | Yes | Set once |
| `updated` | ISO date | Yes | Touched on every write |
| `aliases` | list | No | Former slugs and other names, stored as written. Unique across the brain after normalization |
| `pages` | range | Chunks only | Page span in the original, written `"<first> to <last>"` using the printed page labels (`"11 to 16"`, `"5-4 to 5-6"`); a single page is just its label |

**Body.** Two required sections after the frontmatter, in this order: `## Facts`, then `## Links`. A node with no facts is invalid; `## Links` may be empty.

- A fact line is `- [tag] <fact> (src: <source>, <YYYY-MM-DD>)`, where tag is `stated`, `observed` or `derived`. Every fact has a source; with no external source, the author and the date written are the source, written `(src: self, <date>)` and tagged `[stated]`.
- The source is always the **final** parenthetical group on the line. Anything earlier in brackets belongs to the fact.
- A superseded fact is rewritten in place with its history: `<new value> (was <old value>, changed <YYYY-MM-DD>[ by <change source>]) (src: <source>, <YYYY-MM-DD>)`. The final group stays the **original** citation (a page, a meeting). When the change came from a different source (an erratum, a later meeting), that source goes inside the history as `by <change source>`, so neither citation is lost. Example: `Saves 30 percent of water (was 35 percent, changed 2030-02-04 by erratum) (src: Okafor 2029 p.15, 2030-02-02)`. Amended 2026-10-24 (f02 fix).
- A link line is `- <relation> [[slug]]`, where the relation text is required.

The template is `templates/node.md`, kept only in the public repo. Its YAML comments are stripped on copy, so real nodes carry none; the explanations live here. Its placeholder `id` (all zeros) must be replaced with a freshly generated UUID, and is rejected by name. Rules are checked by hand for the first 10 nodes, then by a validator in `app/` (`validation/`).

## Alternatives considered

- **Readable IDs (slug as identity).** Simpler to read and write by hand. But every rename breaks links unless a redirect is kept, which is the job the UUID does. The register keeps this as D2's revisit trigger.
- **Path as identity (plain wiki links to files).** Zero ceremony, but couples identity to folder placement, so moving a node between folders breaks it.
- **Free-form body.** Easier to write, but extraction (1b) and validation (2) would have to guess at structure.

## Tradeoffs

Gives up some **simplicity** (each node carries a UUID nobody reads, and the index has to map slug to uuid) for **reliability** and **maintainability**: renames and moves never break links. Strict fact-line syntax costs writing speed by hand, in exchange for **consistency** for every machine reader later.

## Consequences

- Easier: renaming and moving nodes; extraction and validation can parse lines without heuristics.
- Merging forward makes the newer slug an alias of the surviving node.
- Harder: writing by hand needs a UUID generator, and `index.md` has to be kept in sync manually during phase 1a.
- The format freezes at the end of phase 1a (build order step 9). After that, changes to this record are register amendments.

## Amendments 2026-10-31 (A1–A8)

Approved by Manoj and recorded against D29 and D31 in the register. Where a rule above conflicts with this section, this section wins.

- **A1, shelves.** A node lives in exactly one numbered shelf inside the brain repo's `library/`. The shelf names are one list in code (`structural.SHELVES`). The structural pass reads only `library/`, minus `00-manual/` (the manual and the generated maps) and `14-inbox/` (rough captures that may skip the format). Nothing outside `library/` is read: evals, the archive and private notes stay out of every map.
- **A2, types.** `person`, `place`, `project`, `goal`, `decision`, `event`, `source`, `concept`, `framework` (D29). `topic` became `concept`.
- **Chunks are sources.** There is no `chunk` type. A chunk of a long source is a `source` note stored under its parent: `13-sources/<source-slug>/<source-slug>-ch-<nn>.md`, with `pages` set and a `part of [[<source-slug>]]` link. Facts cite the chunk with a page (`src: <source-slug>-ch-<nn> p.<page>`), so page citations keep working as before.
- **A3, area.** A new `area` frontmatter field names the life area a note serves. On an area shelf it matches the folder without its number; on a shared shelf it is optional.
- **A4, size.** One subject per file, soft limit about a page; a longer note is split and linked with `part of`.
- **A5, verbs.** A link line's relation must be one of 19 verbs, each with an opposite (`structural.VERBS`). A link is written once, in either form; the generated relationship map adds the other direction. Any other verb is flagged in the map's `unknown_verbs`.
- **A6, mentions.** `[[slug]]` may appear on first mention inside `## Facts`. The map records it as a plain `mentions` edge (`kind: mention`); typed verbs come only from `## Links`. A `[[link]]` anywhere else still stops the pass.
- **A7, template.** The working template is the brain repo's `library/00-manual/node.md`. `templates/node.md` here stays as the generic, invented example.
- **A8, index.** A generated shelf map in `library/00-manual/generated/` replaces the hand-kept `index.md`.

Why: the real brain is organised by life area rather than by node kind, and the first life questions need places, goals, decisions and events as notes. Writing each link once removes a way for two notes to contradict each other.

## Amendments 2026-10-31, second round (A9–A21)

Approved by Manoj after the node-template and folder-structure research reports. There is no A16 (identity stays with `id`). Where this section conflicts with anything above, this section wins. The full template is the brain repo's `library/00-manual/node.md`; the folder rules are its `taxonomy.md`.

- **A9, fact lines.** `- <one self-contained fact, subject named>. (src: <source>, <recorded date>[; valid: <from>..<to> | as of <date>][; inferred])`. The `[stated]`, `[observed]`, `[derived]` tag is dropped; a line is stated by default and `inferred` marks the exception (trial).
- **A10, history.** A fact is never overwritten or deleted. When it stops being true it moves to `## History` with `until: <date>`; a fact that was never true moves there with `wrong: <reason>`. This replaces the inline `(was …, changed …)` form.
- **A11, sections.** Every note has `# Title`, `## Summary`, `## Facts`, its type sections, `## Links` (at least one link) and an optional `## History`. A `[[link]]` in Summary, Facts or a type section is a `mentions` edge; a link in History stays out of the current map; a link outside any section stops the structural pass. Text after a link line's `[[slug]]` (`— since …`) is ignored for now.
- **A12, area.** Every note has an `area` (replaces A3).
- **A13, fields and type sections.** `status` is essential for projects, goals and decisions; `review` for decisions; plus `last_contact`, `answers` (trial), `scope` and per-type sections.
- **A14, verbs.** 21 content verbs in snake_case, each with an inverse that code adds, replacing A5's 19. `precedes` stays in any cut, because chunking uses it.
- **A15, aliases.** Include nicknames, abbreviations, German and English names. No alias may match another note's slug or alias after normalization; the structural pass reports it as an error.
- **A17, folders v3.** `library/` holds `00-manual`, `01-health`, `02-relationships`, `03-work-career`, `04-learning`, `05-money`, `06-purpose`, `07-home-admin`, `08-rest-joy`, `10-ideas`, `11-people`, `12-places`, `13-sources`, `14-inbox`, `15-journal`. `09` is free. Placement is type first, then raw or dated, then the area of the activity. Numbers are frozen from here.
- **A18, area values.** One of the eight life areas (`01-health` … `08-rest-joy`) or `cross`, plus an optional `also:` list of the same values.
- **A19, hub.** A structural type: one per area and for `10-ideas`, a summary plus `lists [[note]]` links (22nd verb, inverse `listed_in`, marked as hub links so discovery can ignore them). A hub holds no facts.
- **A20, journal.** A structural type for dated entries in `15-journal/`: date slug, one-line description, free text; links in the free text are mentions.
- **A21, sub-folders.** Created only when about 7 notes need one; never deeper than `area/sub-folder/note`.

Why: the research reports found that self-contained, dated facts, a history that is moved rather than overwritten, sharp descriptions and aliases, and typed links give the measured gains; and that a shallow, type-first tree with hubs as searchable summaries avoids double homes.
