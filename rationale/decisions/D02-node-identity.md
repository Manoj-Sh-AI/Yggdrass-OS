# D02: Node identity and schema

Date: 2026-10-24
Status: accepted (2026-10-24), frozen 2026-10-24 (D31)

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
