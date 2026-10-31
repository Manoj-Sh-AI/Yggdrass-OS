# Spec: Phase 1b — structural pass

Status: approved (Manoj, 2026-10-25, with criterion 9 tightened); amended 2026-10-31 (library, mentions, opposites; see the last section)
Scoping: [`scoping-phase-1b.md`](scoping-phase-1b.md), open question 2 (ruled 2026-10-25)
Plan: `planning/locked-plan-v1.md`, Phase 1b and register rows D5, D6, D8, D31, D32
Format: [`rationale/decisions/D02-node-identity.md`](../rationale/decisions/D02-node-identity.md) (frozen, D31)

## Summary

A model-free pass that reads every node in a brain and writes the map as `.map/graph.json`. It uses only what is written down: frontmatter and the hand-written `[[links]]`. It keeps what Graphify drops (each link's reason text, and alias resolution), it is deterministic, and it is rebuildable at any time (D6). Graphify's discovery pass is out of scope here; this spec covers only the map.

## Inputs and outputs

| Input | Source | Format |
|---|---|---|
| Brain root | Command-line argument, e.g. `yggdras-brain/demo-brain` | A folder of nodes in the frozen D02 format, with `index.md` at its root |

| Output | Destination | Format |
|---|---|---|
| The map | `<brain repo>/.map/graph.json`, or `--out PATH` | UTF-8 JSON, shape below |
| Summary | Standard output | Counts: nodes, edges, dangling links, errors |

The default output path is `.map/` beside the brain root. For `yggdras-brain/demo-brain` that is `yggdras-brain/.map/graph.json`.

**Proposed `graph.json` shape (for approval):**

```json
{
  "schema": "yggdras-map/1",
  "nodes": [
    {
      "id": "UUID v4 from frontmatter",
      "slug": "kebab-case",
      "name": "string",
      "type": "person | area | topic | source | chunk",
      "path": "path relative to the brain root, with forward slashes",
      "aliases": ["as written in frontmatter"]
    }
  ],
  "edges": [
    {
      "from": "source node id",
      "to": "target node id",
      "from_slug": "slug",
      "to_slug": "slug",
      "reason": "the relation text before [[...]], trimmed",
      "written_as": "the text inside [[...]], exactly as written",
      "resolved_via": "slug | alias",
      "line": 12
    }
  ],
  "dangling": [
    {"from": "id", "from_slug": "slug", "reason": "text", "written_as": "text", "line": 12}
  ],
  "errors": [
    {"path": "relative path", "problem": "what is wrong"}
  ]
}
```

- The file holds no timestamps, absolute paths or run IDs, so byte-identical output is possible.
- `nodes` are sorted by `slug`; `edges` and `dangling` by (`from_slug`, `line`); `errors` by `path`.
- The JSON is written with sorted keys, a two-space indent, `\n` line endings and non-ASCII kept as is.

## Behavior

1. Find every `.md` file under the brain root except `index.md`, and parse its frontmatter and body with the frozen D02 format.
2. Build a lookup from every node's slug and every alias to the node's `id`. Comparison uses the D02 normalization: lowercase, accents stripped, `ß`→`ss`, `ø`→`o`, spaces and underscores to hyphens, punctuation dropped, hyphens collapsed and trimmed.
3. For each line in a node's `## Links` section, take the reason (the text before `[[`, without the leading `- `) and the target (the text inside `[[ ]]`).
4. Resolve the target: first as an exact slug, then as a normalized slug or alias. A match becomes an edge, recording `resolved_via`. No match is recorded as dangling.
5. Write `graph.json` and print the summary. The brain files are never modified (D6).

## Acceptance criteria

1. **Input.** Given a brain with N node files plus `index.md`, when the pass runs, then `nodes` has N entries, `index.md` is not among them, and each entry's `id`, `slug`, `name`, `type`, `path` and `aliases` match its frontmatter.
2. **Output location and shape.** Given a brain root, when the pass runs with no `--out`, then it writes `.map/graph.json` beside the brain root, and the file validates against the shape above, with `schema` set to `yggdras-map/1`.
3. **Reasons kept.** Given the link line `- crippled by [[oxygen-tank-2]]`, when the pass runs, then the edge has `reason` = `crippled by` and `written_as` = `oxygen-tank-2`.
4. **Alias resolution.** Given a link `[[Mattingly]]` and a node (`ken-mattingly`) whose aliases include `Mattingly`, when the pass runs, then the edge's `to` is that node's `id` and `resolved_via` is `alias`. A link written as the slug itself resolves with `resolved_via` = `slug`.
5. **Determinism.** Given an unchanged brain, when the pass runs twice in a row, then the two `graph.json` files are byte-identical.
6. **Dangling links reported.** Given a link to a target that matches no slug or alias, when the pass runs, then it appears in `dangling` with its source, reason, written target and line, appears in no `edges` entry, and is counted in the summary. It is never silently dropped.
7. **Errors reported, not fatal.** Given a file with unparseable frontmatter, or a duplicate slug, when the pass runs, then the problem appears in `errors`, the rest of the brain is still mapped, and the process exits non-zero.
8. **Read-only.** Given any brain, when the pass runs, then no file under the brain root is created, changed or deleted.
9. **Apollo comparison.** Given `yggdras-brain/demo-brain`, when the pass runs, then the report counts every `[[...]]` occurrence across each **whole file** by plain text, independently of the parser, and asserts two things:
   - **143 occurrences inside `## Links` sections, and all 143 become edges** (0 dangling, 0 errors);
   - **0 occurrences outside `## Links` sections.**

   This tests the assumption that links live only in `## Links`, rather than trusting it. If the second number is ever non-zero, the pass stops and reports it; the parser is **not** widened. Links in fact lines would be a node-format question (D31), not a parser fix. *(Superseded 2026-10-31: D31 amendment A6 made links in fact lines `mentions` edges. The pass still stops on a link outside both `## Facts` and `## Links`. The Apollo brain, run with `--flat`, still gives 143 edges, all from `## Links`.)*

## Edge cases

| Case | Expected behavior |
|---|---|
| A link line with text after `]]` | The reason is the text before `[[`; trailing text is ignored. D02 says link lines end at the slug |
| An alias that normalizes to two nodes | Not resolved; reported in `errors` as ambiguous, never guessed. D02 criterion 2 forbids it, so it signals a broken brain |
| `[[...]]` outside `## Links` | Not an edge, since only the Links section holds hand-written links |
| A node linking to itself | Kept as an edge; it was written by hand |
| An empty brain (no nodes) | Writes a valid `graph.json` with empty lists |

## Tradeoffs

- **Simplicity and reliability over coverage.** It maps only what is written, so it finds nothing new; discovery is Graphify's job (D7).
- **Consistency over speed.** Sorting and canonical JSON cost a little time, in exchange for byte-identical output and diffable runs.

## Out of scope

Graphify and the discovery pass (D7, D32). Triggering on file changes (D8; the pass is a manual command for now). The graph view. The connector tools `query_map` and `propose_change`. Any write to the brain.

## Code location

`app/src/yggdras/data/graph/structural.py`, under the layered layout (D28 stays open until phase 2), with tests in `app/tests/`. The command line is `python -m yggdras.data.graph.structural <brain root> [--out PATH]`.

## Amendment 2026-10-31: library, mentions, opposites

Approved by Manoj with D31 amendments A1–A8 (register D5, D29, D31; D02 record).

**Two modes.**

| Command | Reads | Writes |
|---|---|---|
| `structural BRAIN_REPO` | Only `BRAIN_REPO/library/`, and inside it only the numbered shelves in `SHELVES` minus `00-manual` and `14-inbox` | `library/00-manual/generated/map.json`, `relationship-map.md` and `shelf-map.md`. `--out` is refused, so a map never lands outside the brain repo |
| `structural BRAIN_ROOT --flat [--out PATH]` | Every node under a flat brain except `index.md`, as before (the archived Apollo demo, the fixture brain) | `.map/graph.json` beside the root, or `--out` |

**Map shape, schema `yggdras-map/2`.** As above, plus:

- each edge and dangling entry has `kind`: `link` (from `## Links`) or `mention` (a `[[slug]]` in `## Facts`, reason `mentions`);
- a top-level `unknown_verbs` list of `{path, line, verb}` for link lines whose verb is not in `VERBS` or its opposites.

**Relationship map.** For each node, every link as written, plus each incoming link's opposite marked `(added: opposite)`: `part of` adds `contains`, a mention adds `mentioned in`, and a symmetric verb adds itself. An unknown verb gets no opposite and is shown as written.

**New acceptance criteria.**

10. **Library scope.** Given a brain repo with notes in `library/` shelves, the manual, the inbox, and files outside `library/` (`README.md`, `life-evals/`, `archive/`, `private/`, `brain/`), when the pass runs, then only the shelf notes are nodes and there are no errors from anything else.
11. **Unknown shelf.** Given a folder in `library/` that is not in `SHELVES`, then it is reported in `errors` and not read.
12. **Mentions.** Given `[[slug]]` in a fact line, then it is an edge with `kind` `mention` and reason `mentions`; a typed edge exists only for a `## Links` line.
13. **Opposites.** Given `- part of [[b]]` in note `a`, then the relationship map's section for `b` has `- contains [[a]] (added: opposite)`. Every verb's opposite's opposite is the verb.
14. **Output stays in the brain repo.** Given library mode, the only files created are the two maps in `library/00-manual/generated/`, and `--out` is refused.

**Shelf map (added 2026-10-31).** `shelf-map.md` has one line per mapped note, grouped under a heading per shelf: `slug`, `type`, `area`, the one-line `description` and `aliases`, in a table sorted by slug. Pipes inside a value are escaped. It replaces the hand-kept `index.md` (D31 amendment A8). For this, map nodes gain `area` and `description` from frontmatter, and the schema is `yggdras-map/3`.

15. **Shelf map.** Given notes on shelves, when the pass runs in library mode, then `shelf-map.md` has exactly one row per mapped note under its shelf's heading, with slug, type, area, description and aliases, and no row for anything in the manual, the inbox or outside `library/`.

**Code.** `SHELVES`, `NOT_MAPPED` and `VERBS` in `app/src/yggdras/data/graph/structural.py` are the only lists of shelf names and verbs in code. Tests: `app/tests/test_structural_map.py` (flat mode, criteria 1–9) and `app/tests/test_structural_library.py` (criteria 10–15).
