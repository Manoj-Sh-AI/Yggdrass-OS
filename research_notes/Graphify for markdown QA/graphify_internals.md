# Graphify 0.9.95 internals for markdown QA: retrieval surfaces and extraction-quality controls

Scope: `graphifyy` 0.9.95 as installed at `C:\Users\shman\AppData\Roaming\uv\tools\graphifyy\Lib\site-packages\graphify` (called `PKG` below). Line numbers refer to that install. Nothing was run except `graphify --help` and `graphify export --help`. GitHub was read through `gh api` (releases, issues, branch `v8`).

Source shorthand used in citations:
- PKG = `file:///C:/Users/shman/AppData/Roaming/uv/tools/graphifyy/Lib/site-packages/graphify/`
- Releases = https://github.com/Graphify-Labs/graphify/releases

Version note: v0.9.96 came out 2026-10-26T15:18Z, after the pinned 0.9.95 (released 2026-10-23). `v8` is the active development branch: its latest commits are "chore: bump version to 0.9.96" and a watch fix ([Releases](https://github.com/Graphify-Labs/graphify/releases); `gh api repos/Graphify-Labs/graphify/commits?sha=v8`). The repo CHANGELOG.md on `main` is stale and stops at 0.1.8 ([CHANGELOG](https://raw.githubusercontent.com/Graphify-Labs/graphify/main/CHANGELOG.md)), so the GitHub release notes are the real changelog.

---

## 1. What each retrieval surface outputs, and which attributes it renders

### Takeaway
No released 0.9.95 surface (CLI `query`/`explain`/`path`, MCP `query_graph`/`get_node`/`get_neighbors`/`get_community`/`shortest_path`, wiki, Obsidian, graph.html) ever prints a node's `rationale`, its frontmatter, or any source-note text. The richest node fields a reader can see are `label`, `source_file`, `source_location`, community name, `file_type`/degree (from `get_node`/`explain`), and a free-form `attributes` dict when present. Rationale is used for scoring only. The only way to read it is to open `graphify-out/graph.json` directly. An opt-in `--rationale` / `include_rationale` flag exists only as an open, unmerged PR (#4576) and is not on `v8` either.

### Cited Findings

**`graphify query` (CLI) / MCP `query_graph`. Both go through `serve._query_graph_text` → `_render_query` → `_subgraph_to_text`.**
- CLI usage: `graphify query "<question>" [--dfs] [--context C] [--seed X] [--budget N] [--graph path]`. The CLI hard-codes `depth=2` and default budget 2000 ([PKG cli.py L1546-1665](PKG/cli.py)). MCP `query_graph` takes `question`, `mode` (bfs|dfs), `depth` (default 3, described as "1-6"), `token_budget` (default 2000), `context_filter` (array), and an optional `project_path` added to every tool ([PKG serve.py L2305-2325, L2440-2455](PKG/serve.py)).
- Header line: `Graph: <path> (<N> nodes) | Traversal: BFS depth=2 | Start: [labels] | [Unresolved seeds (skipped): …] | [Context: <filters> (explicit|heuristic)] | <n> nodes found` ([PKG serve.py `_render_query` L1491-1531](PKG/serve.py)).
- NODE line format: `NODE <label> [src=<source_file> loc=<source_location> community=<community_name or community id>[ learning=<status>[:stale]][ attrs={k=v, …}]]` ([PKG serve.py `_subgraph_to_text` L1207-1214](PKG/serve.py)).
  - `attrs={…}` appears only if the node has a dict under the key `attributes`. It shows at most 10 pairs, values over 60 chars are cut to 57+"...", and the whole summary is cut at 200 chars ([PKG serve.py L1177-1206](PKG/serve.py)).
  - `learning=` comes from the `graphify reflect` work-memory sidecar ([PKG serve.py L1170-1176](PKG/serve.py)).
  - The renderer never reads `rationale`, `frontmatter`, `file_type`, `author`, `source_url` or `captured_at`.
- EDGE line format: `EDGE <src label> --<relation> [<confidence>[ context=<context>]]--> <tgt label>[ at=<edge source_file>:<edge source_location>]`. `context=` appears only if the edge has a `context` attribute, and `at=` only if the edge has a `source_location` ([PKG serve.py L1215-1246](PKG/serve.py)). Parallel edges each get their own line (#4500) ([PKG serve.py L1218-1222](PKG/serve.py)).
- Rationale is used only for retrieval scoring: `_node_rationale_text` (L409) feeds `_node_search_text` (L423-467) and `_score_query`'s rationale tier, with `_RATIONALE_MATCH_BONUS = 0.75` (below a label substring hit, above a source-path hit, and not counted toward term coverage) (#2293) ([PKG serve.py L338-346, L645, L708-711](PKG/serve.py)). Node `attributes` text is also searchable, with `_ATTRIBUTE_MATCH_BONUS = 0.75` ([PKG serve.py L347, L361-374](PKG/serve.py)).
- Matching is case-folded substring plus IDF, with "no stemming, no synonyms, no cross-language match". The skill workflow therefore expands the question against `graphify-out/.vocab.txt` before querying ([PKG skills/claude/references/query.md L25, L48](PKG/skills/claude/references/query.md)).
- The skill tells the answering agent to "Answer using only what the graph contains. Quote `source_location` when citing a specific fact" ([PKG skills/claude/references/query.md L75-76](PKG/skills/claude/references/query.md); [PKG skill.md L771](PKG/skill.md)).

**`graphify explain "<node>" [--all] [--graph path]` (CLI)**
- Prints these lines: `Node:`, `ID:`, `Source: <source_file> <source_location>`, `Type: <file_type>`, `Community:`, optional `Lesson:` (reflect overlay), and `Degree:`. Then it prints `Connections (N):` as lines of the form `--> / <-- <neighbor label> [<relation>] [<confidence>] <edge source_file>:<loc>`, sorted by neighbor degree ([PKG cli.py L2092-2190](PKG/cli.py)).
- Without `--all`, it shows the 20 connections with the highest-degree neighbors, then "... and N more", grouped by file. `--all` only removes that 20-row cap ([PKG cli.py L2102, L2165-2200](PKG/cli.py)). `--all` was added in v0.9.86 (#4323) ([Releases v0.9.86](https://github.com/Graphify-Labs/graphify/releases)).
- `explain` does not print rationale, `attributes` or edge `context` ([PKG cli.py L2124-2190](PKG/cli.py)).

**`graphify path "A" "B" [--directed|--undirected]` (CLI) / MCP `shortest_path(source, target, max_hops=8, undirected=false)`**
- Output: `Shortest path (<hops> hops):` followed by `A --<rel>[ [conf]]--> B <--<rel>-- C …`. When a hop has no relation, it says `related` instead of inventing `calls` (#2074). Only labels, relations and confidences are shown ([PKG cli.py L2040-2084](PKG/cli.py); [PKG serve.py `_shortest_path_text` L2067-2148](PKG/serve.py)).
- The search is directed by default (#2487). MCP adds ambiguity warnings when the top two match scores are within 10% ([PKG serve.py L2090-2104](PKG/serve.py)).

**MCP `get_node(label | node_id)`**
- Lines: `Node:`, `ID:`, `Source: <source_file> <source_location>`, optional `Defined in:` (C/C++ header and impl split), `Type: <file_type>`, `Community:`, `Degree:`, and `Attributes: <json>` only if a node `attributes` dict exists, capped at 1000 chars ([PKG serve.py `_tool_get_node` L2487-2518](PKG/serve.py)). No rationale, no frontmatter, no edges.

**MCP `get_neighbors(label | node_id, relation_filter?, token_budget=2000)`**
- Lines: `Neighbors of <label>:` then `  --> <label> [<relation>] [<confidence>][ at=<file>:<loc>]` (successors) and `  <-- …` (predecessors). `relation_filter` is a substring test on the relation name. The output is cut by `_cut_lines_to_budget` ([PKG serve.py `_neighbor_lines` L2193-2227, `_tool_get_neighbors` L2520-2534](PKG/serve.py)). It applies no context filter and renders no edge `context`.

**MCP `get_community(community_id)`, `god_nodes`, `graph_stats`**
- `get_community` prints `Community N — Name (k nodes):` followed by `  <label> [<source_file>]` lines ([PKG serve.py L2536-2553](PKG/serve.py)). The other two return labels and counts ([PKG serve.py L2555-2578](PKG/serve.py)).

**Open issues/PRs on the gap (not released)**
- Issue #2821 (open, filed against 0.9.42): `semantic_cleanup` writes `rationale` onto nodes but "Nothing ever reads it back". On a 3-document markdown corpus, 50 of 75 nodes carried about 8,900 chars of rationale that no read surface could reach ([#2821](https://github.com/Graphify-Labs/graphify/issues/2821)).
- PR #4576 (open, rebased onto `v8`, supersedes #2830) adds opt-in `graphify query … --rationale`, `explain … --rationale`, and MCP `include_rationale` on `query_graph`/`get_node`. Query would append ` WHY <text>`, and get_node/explain would print `Rationale: <text>` ([#4576](https://github.com/Graphify-Labs/graphify/pull/4576); [#2830](https://github.com/Graphify-Labs/graphify/pull/2830)).
- The `v8` branch's `serve.py` has no `include_rationale`, so the PR is not merged there either (checked via `gh api …/contents/graphify/serve.py?ref=v8`).

### Inferences
- For our 42-note brain (0 of 43 nodes had `rationale`, and no node had an `attributes` dict), label-only NODE lines are exactly what 0.9.95 is designed to output. Getting fact text to the answering model needs a step outside Graphify. That fits D32 if Graphify is used unmodified as a locator: take the `src=` / `loc=` values from `query` / `get_node` output, then read those files ourselves.
- MCP `query_graph` defaults to depth 3 while CLI `query` is fixed at depth 2. Experiments comparing the two surfaces should control for this.

### Gaps
- I did not verify whether arbitrary extra keys the LLM emits (for example a node `attributes` object, or an edge `context`) survive `build_from_json` into graph.json. If they do, they would render as `attrs={…}` / `context=`. In the installed code only `extractors/terraform.py` (L459) writes `attributes` (plus a dedup fold in `dedup.py` L1468).

---

## 2. When extraction populates `rationale`, edge `context` and specific relation verbs; what deep mode, `--token-budget`, chunking and `--max-concurrency` change; any way to steer the prompt

### Takeaway
The headless `graphify extract` prompt (`llm._EXTRACTION_SYSTEM`) gives the model a fixed edge-`relation` enum of seven verbs: `calls|implements|references|cites|conceptually_related_to|shares_data_with|semantically_similar_to`. It asks for `rationale` only for explicit WHY / trade-off text, has no `context` field for edges, and has no `attributes` field. That fully explains our result of 54 of 57 generic edges and 0 rationale. There is no flag, env var or `.graphifyrc` key that changes the prompt or the relation vocabulary. `--mode deep` appends a short suffix. `--token-budget` and `--max-concurrency` only change packing and parallelism.

### Cited Findings

**The prompt and its schema**
- System prompt rules: EXTRACTED / INFERRED / AMBIGUOUS definitions, plus "Rationale (WHY decisions were made, trade-offs, design intent): store as a `rationale` attribute on the relevant node… If the source does not explicitly provide a reason, omit this attribute (do not restate descriptions)" ([PKG llm.py L502-511](PKG/llm.py)).
- Output schema: node keys are `id, label, file_type, source_file, source_location, source_url, captured_at, author, contributor, rationale`. Edge keys are `source, target, relation, confidence, confidence_score, source_file, source_location, weight`, and the relation enum is the seven verbs above. There is no edge `context` and no node `attributes` ([PKG llm.py L541](PKG/llm.py)).
- The source_file rule tells the model to model a linked or cited file as a node "and link to it with a `references` or `cites` edge" ([PKG llm.py L521-529](PKG/llm.py)). This matches our observed 6 `references` + 3 `cites`.
- Relation names are not validated against a vocabulary. `validate.py` checks only `file_type` (six values), `confidence`, and the required edge fields `source, target, relation, confidence, source_file` ([PKG validate.py L4-7, L48-71](PKG/validate.py)). A model could emit other verbs, but the prompt steers it to the enum.
- Each file is wrapped in an `<untrusted_source>` block, and the model is told never to obey instructions inside one ([PKG llm.py L512-519, `_read_files` L632-689](PKG/llm.py)). Text in the notes therefore cannot steer extraction, by design.
- Each file is capped at `_FILE_CHAR_CAP = 20_000` chars. Larger splittable docs are pre-split into `FileSlice`s (#1369) ([PKG llm.py L31, L2760-2763](PKG/llm.py)).

**Deep mode**
- `--mode deep` appends `_DEEP_EXTRACTION_SUFFIX`: "include additional INFERRED edges only for concrete architectural signals (shared data contracts, explicit lifecycle coupling, or multi-step flow dependencies…). Avoid broad conceptual similarity edges. Mark uncertain ones AMBIGUOUS instead of omitting" ([PKG llm.py L544-557](PKG/llm.py)). It does not change the relation enum or the rationale rule.
- Deep mode uses its own cache namespace (`cache/semantic-deep/`). On an incremental run it widens the semantic pass to every live doc, paper and image (#1894) ([PKG cli.py L4067-4093](PKG/cli.py)).
- The skill/subagent path describes deep mode differently from the headless path. `extraction-spec.md` says "DEEP_MODE… be aggressive with INFERRED edges - indirect deps, shared assumptions, latent couplings" ([PKG skills/claude/references/extraction-spec.md](PKG/skills/claude/references/extraction-spec.md)), while `llm.py` says to avoid broad similarity edges.

**The skill-path prompt (`extraction-spec.md`) differs from the headless one**
- Its relation enum adds `rationale_for`. It includes a `semantically_similar_to` rubric (INFERRED, 0.6-0.95), a discrete confidence_score set (0.95/0.85/0.75/0.65/0.55), a `coverage` object, and "If a file has YAML frontmatter… copy source_url, captured_at, author, contributor onto every node". It tells doc files to "extract named concepts, entities, citations" and store rationale as an attribute ([PKG skills/claude/references/extraction-spec.md](PKG/skills/claude/references/extraction-spec.md)).
- This spec is used by `/graphify` agent subagents (and `cache-check --prompt-file`), not by `graphify extract`. `--prompt-file` only fingerprints the cache namespace ([PKG cli.py L5221-5267](PKG/cli.py); [PKG cache.py L167-186](PKG/cache.py)).

**How `rationale` actually gets onto nodes**
- `semantic_cleanup.py` removes nodes with `file_type` "rationale" or "concept" that read like sentences and are sources of a `rationale_for` edge, and folds their label into a `rationale` attribute on the target node ([PKG semantic_cleanup.py L176-233](PKG/semantic_cleanup.py)). Since the headless enum has no `rationale_for`, this path mostly fires for the skill path. On the headless path, the model must fill `rationale` itself, and only when the source states an explicit reason.

**Edge `context`**
- Only AST/code extractors produce `context`, with values like call/import/field/parameter_type/return_type/generic_arg/attribute/export (the vocabulary in `_CONTEXT_FILTER_ALIASES`) ([PKG serve.py L912-953](PKG/serve.py)). The LLM schema has no `context`, and `extract_markdown` edges carry none ([PKG extractors/markdown.py `add_edge` L470-479](PKG/extractors/markdown.py)). A markdown `raw_calls` entry has a `context` (the code-span text), but that is a code-symbol mention, not a link verb ([PKG extractors/markdown.py L449](PKG/extractors/markdown.py)).

**Chunking, `--token-budget`, `--max-concurrency`**
- `extract_corpus_parallel(token_budget=60_000, max_concurrency=4, deep_mode=…)`. Files are greedily packed into chunks up to the token budget, grouped by parent directory, so cross-file edges are more likely within a chunk. A chunk is truncated on output (finish_reason=length) it is bisected and retried, up to `max_retry_depth`, which defaults to 3 and can be overridden with `GRAPHIFY_MAX_RETRY_DEPTH` ([PKG llm.py `_pack_chunks_by_tokens` L2285-2328, `extract_corpus_parallel` L2692-2770](PKG/llm.py)).
- `--max-concurrency` is the size of the thread pool. It is forced to 1 for ollama and claude-cli unless `GRAPHIFY_OLLAMA_PARALLEL=1` / `GRAPHIFY_CLAUDE_CLI_PARALLEL=1` is set ([PKG llm.py L2793-2801](PKG/llm.py)).
- The CLI flags are `--token-budget N` (default 60000), `--max-concurrency N` (default 4), `--mode deep`, `--model`, `--backend`, `--api-timeout`, `--no-dedup`, `--code-only`, and `--force` ([graphify --help](PKG/cli.py); [PKG cli.py L3756-3830](PKG/cli.py)). v0.9.85 notes say "a smaller `--token-budget` is the lever" for semantic omission (#4101, #4280) ([Releases v0.9.85](https://github.com/Graphify-Labs/graphify/releases)).
- Neither flag changes the prompt text or the relation enum.

**Steering knobs (or the lack of them)**
- `_extraction_system(deep)` returns a module constant. No env var or flag injects text into it ([PKG llm.py L553-557](PKG/llm.py)). A grep for `GRAPHIFY_PROMPT`, `relation_vocab`, `custom_prompt` and `extra_instructions` found nothing.
- Env vars that do exist on the LLM path: `GRAPHIFY_MAX_OUTPUT_TOKENS`, `GRAPHIFY_LLM_TEMPERATURE`, `GRAPHIFY_API_TIMEOUT`, `GRAPHIFY_MAX_RETRIES`, `GRAPHIFY_MAX_RETRY_DEPTH`, `GRAPHIFY_DISABLE_THINKING`, `GRAPHIFY_CLAUDE_CLI_MODEL`, `ANTHROPIC_MODEL` (default `claude-sonnet-4-6`), `ANTHROPIC_BASE_URL`, and `GRAPHIFY_BACKEND` (`none` disables LLM work) ([PKG llm.py L130-131, L332-500, L1898](PKG/llm.py); [PKG cli.py L4147-4166](PKG/cli.py)).
- `.graphifyrc` supports only `viz_node_limit=<int>` and `language.<ext>=<lang|.ext>` ([PKG rcfile.py L1-27](PKG/rcfile.py)).
- On the `claude-cli` backend, Claude Code still layers in local CLAUDE.md/AGENTS.md, skills and MCP context from the working directory, so graphify puts the schema in the user turn ([PKG llm.py L1849-1885](PKG/llm.py)).

### Inferences
- The only released levers on relation quality are the choice of model (`--model` / `ANTHROPIC_MODEL`), `--mode deep`, and `--token-budget` (smaller chunks give more attention per file but fewer cross-file pairs inside a chunk). None can stop the seven-verb enum, so specific verbs like "replaced by" will not appear through `graphify extract` unmodified.
- Using a CLAUDE.md in the working directory to steer extraction on the claude-cli backend is an unintended side channel, not a supported feature. Within D32 it would be fragile.
- Because the prompt caps verbs, a pre-registered experiment should treat relation specificity as fixed by Graphify. Variation should come from retrieval design, for example reading the source files that `src=` points to.

### Gaps
- I did not measure how much `--mode deep` or a smaller `--token-budget` changes the generic-edge share on our corpus. That needs an extract run, which was out of scope.

---

## 3. What `--wiki` / `export wiki` and `export obsidian` produce, and whether they include fact text

### Takeaway
Both exporters are generated purely from the graph: labels, relations, confidence, source paths and community stats. Neither reads the source notes, and neither renders rationale. They do not include fact text.

### Cited Findings
- `graphify export wiki [--graph PATH] [--labels PATH]` writes `graphify-out/wiki/index.md` ("agent entry point") plus one article per community and per god node. It refuses to run if `.graphify_analysis.json` is missing ([PKG cli.py L3221-3235, L3519-3535](PKG/cli.py)). `/graphify <path> --wiki` is the skill-path equivalent ([PKG skill.md L33, L625](PKG/skill.md)).
- Community article (`_community_article`): `# <label>`, a "> N nodes · cohesion x" line, "## Key Concepts" (`- **label** (degree connections) — \`source_file\``), "## Relationships" (cross-community link counts), "## Source Files", and "## Audit Trail" (EXTRACTED/INFERRED/AMBIGUOUS percentages) ([PKG wiki.py L121-199](PKG/wiki.py)).
- God-node article: `# label`, a "> God node · N connections · `src`" line, the community link, and "## Connections by Relation" with `### <relation>` lists of linked neighbor labels and confidence, capped at 20 per relation ([PKG wiki.py L202-245](PKG/wiki.py)). The string "rationale" does not appear in wiki.py.
- Obsidian node note: YAML frontmatter (`source_file`, `type`, `community`, `location`, `tags`), `# label`, and "## Connections" with `- [[neighbor]] - \`relation\` [confidence]`, plus inline tags. Before 0.9.96 it showed only the first edge per neighbor pair ([PKG export.py `to_obsidian` L760, L868-901](PKG/export.py)). v0.9.96 lists every parallel relation (#4731) ([Releases v0.9.96](https://github.com/Graphify-Labs/graphify/releases)).
- `graph.html` node data carries `source_file`, `file_type` and `degree`. It has no rationale ([PKG exporters/html.py L175, L265-272](PKG/exporters/html.py)).
- `GRAPH_REPORT.md` filters `rationale` and `concept` nodes out of community listings (v0.9.72, #3836) ([PKG report.py L160-171](PKG/report.py); [Releases v0.9.72](https://github.com/Graphify-Labs/graphify/releases)).

### Inferences
- The wiki/Obsidian exports would give an answering model the same label and relation skeleton as `query`, just pre-grouped. For fact-based QA they are unlikely to beat `query` output.

### Gaps
- I did not inspect the `svg`, `graphml`, `neo4j` and `falkordb` exporters for rationale. graph.json itself does keep `rationale` when the LLM sets it.

---

## 4. The inferred context filter (#2529): any opt-out, and how `--context` treats edges with no context

### Takeaway
There is no released opt-out: no env var, no flag, no MCP parameter. If the question contains any hint word, `_infer_context_filters` turns on a filter that keeps only edges whose `context` equals the inferred value. Edges with no `context`, which is every edge in an LLM or markdown graph, are all dropped, and traversal collapses to the seed nodes. An explicit `--context` / `context_filter` replaces the inferred filter but filters the same way. Issue #2529 is still open.

### Cited Findings
- `_CONTEXT_HINTS` in 0.9.95 ([PKG serve.py L906-913](PKG/serve.py)):
  - call: call, calls, called, caller, callers, invoke, invokes, invoked
  - import: import, imports, imported, module, modules
  - field: field, fields, member, members, property, properties
  - parameter_type: parameter(s), param(s), argument(s)
  - return_type: return, returns, returned
  - generic_arg: generic(s), template(s)
- The question is lower-cased, has diacritics folded, has "?" and "," replaced by spaces, and is split on whitespace. Matching is whole-token ([PKG serve.py `_infer_context_filters` L972-981](PKG/serve.py)).
- `_resolve_context_filters`: an explicit non-empty filter wins ("explicit"); otherwise the inferred filter applies ("heuristic"); otherwise no filter ([PKG serve.py L984-991](PKG/serve.py)). There is no sentinel value such as "none" or "all".
- `_filter_graph_by_context` keeps every node but only edges where `data.get("context") in filters`. An edge without `context` therefore never passes ([PKG serve.py L994-1008](PKG/serve.py)).
- The header shows `Context: <filters> (heuristic)` when inference fired, which is the only signal ([PKG serve.py L1517-1518](PKG/serve.py)).
- Issue #2529 ("`query` silently infers a context filter from the wording of the question and collapses the result to the seed nodes"), filed 2026-08-07 against 0.9.34, is still **open**. It describes the filter as "opt-out rather than opt-in" and gives a repro on an 81-node graph whose edges have no `context` ([#2529](https://github.com/Graphify-Labs/graphify/issues/2529)).
- Surfaces with no context filtering: MCP `get_neighbors`, `get_node`, `shortest_path`, and CLI `explain` / `path` ([PKG serve.py L2487-2534, L2067](PKG/serve.py); [PKG cli.py L1912-2215](PKG/cli.py)).

### Inferences
- Released workarounds that stay within D32:
  - Strip or replace the hint tokens in the question string before calling `query`. For example, "Which module…" or "who returned…" will trigger the filter.
  - Use `--seed` plus a hint-free question.
  - Use `explain`, `get_neighbors` or `path`, which ignore context.
- Any experiment that sends natural-language questions should log the header's `Context:` field to detect a collapse.
- In the Apollo questions, words like "returned" (for example "returned to Earth") would trigger `return_type` and cut every edge.

### Gaps
- None of the 0.9.80-0.9.96 release notes mention a change to `_CONTEXT_HINTS`. Whether `v8` has changed the list since 0.9.95 was not diffed.

---

## 5. Budget behaviour: how `_subgraph_to_text` cuts, seeds, BFS vs DFS, `--seed`, depth, and the "Complete answer over budget" notice

### Takeaway
The budget is about 3 chars per token (`char_budget = token_budget*3`). Seeds render first and are never cut. Other nodes are ordered by hop distance from the seeds, then by degree descending. All NODE lines come before any EDGE line, so the cut drops edges first. "Complete answer over budget" means every node fit but nodes plus edges exceeded the budget. In that case the full output is returned anyway, with a notice that raising `--budget` will not shrink it.

### Cited Findings
- Seeds come from `_pick_seeds` over `_score_query`'s ranking plus a per-term guarantee. Relational-intent verbs (call, uses, imports, references, …) are dropped from the per-term guarantee (#2507). A question that exactly names several nodes is refused with exit code 3 (#4511) ([PKG serve.py L1456-1488, L885-904](PKG/serve.py); [Releases v0.9.93](https://github.com/Graphify-Labs/graphify/releases)).
- `--seed X` (repeatable; node id, label or file path) replaces keyword seeding. Unresolved seeds are reported and skipped, and if no seed resolves the query fails closed (v0.9.88, #4293) ([PKG serve.py L1424-1455](PKG/serve.py); [Releases v0.9.88](https://github.com/Graphify-Labs/graphify/releases)).
- `_bfs`: expands layer by layer up to `depth`, but does not expand through non-seed hubs whose degree is at or above `max(50, p99 degree)`. `_dfs`: stack-based with the same hub rule. Both then call `_complete_induced_edges`, which adds edges between any two visited nodes (#2323/#4314) ([PKG serve.py L1011-1117](PKG/serve.py)). Traversal runs on an undirected view and keeps the true direction in `_src` / `_tgt` ([PKG serve.py `_traversal_view` L1360-1410](PKG/serve.py)).
- Render order: seeds, then other nodes sorted by `(hop distance from seeds, -degree, id)`, then all EDGE lines ([PKG serve.py L1131-1163](PKG/serve.py)).
- Cut logic: if the output exceeds `char_budget`, it is cut at the last newline before the budget, extended if needed so the whole seed block survives ([PKG serve.py L1248-1258](PKG/serve.py)).
  - If no NODE line was cut, it returns `[i] Complete answer over budget: all N nodes and M edges shown (~T tokens vs the requested ~B-token budget). Edges are never dropped once every node fits…` with the **full** output (#2601/#2784) ([PKG serve.py L1259-1290](PKG/serve.py)).
  - Otherwise it prepends `[!] TRUNCATED: showing k of N nodes… raise the token budget to <full_budget>…` and appends `... (truncated — X more nodes cut…)`. Here `full_budget` is the smallest budget that keeps every NODE line ([PKG serve.py L1291-1308](PKG/serve.py)).
- `get_neighbors` / `get_community` use `_cut_lines_to_budget` with the same 3-chars-per-token rule and a top-of-output notice ([PKG serve.py L1311-1336](PKG/serve.py)).
- The skill's inline NetworkX fallback uses about 4 chars per token and a plain truncation marker. Its arithmetic differs from the CLI's ([PKG skills/claude/references/query.md L146-167](PKG/skills/claude/references/query.md)).

### Inferences
- On a 43-node / 57-edge graph, a depth-2 BFS often reaches most of the graph. Then `--budget 2000` (about 6000 chars) mostly holds label lines, and the over-budget notice is likely. More budget adds only labels, not facts.

### Gaps
- None.

---

## 6. The deterministic markdown extractor: what it does, whether any released CLI path runs it without the LLM, and whether it reads wikilink verb text

### Takeaway
`extractors/markdown.extract_markdown` is a pure line parser. It produces one `page` node per file (frontmatter parsed onto it as a `frontmatter` key), one node per heading, `contains` edges, and one `references` edge per distinct resolved link target. The link target can be an inline link, a reference-style link, or a `[[wikilink]]`, including links in frontmatter. It discards the surrounding verb text and the body lines, so "- replaced by [[jack-swigert]]" becomes just `page --references--> jack-swigert.md`, and `## Facts` lines are not captured. `graphify update <path>` (and `watch`) runs it on .md files with no LLM. `graphify extract` sends .md to the LLM, or skips docs under `--code-only` / `GRAPHIFY_BACKEND=none`.

### Cited Findings
- Nodes ([PKG extractors/markdown.py L369-418, L459-468, L481-484, L560-577](PKG/extractors/markdown.py)):
  - The file node has `node_kind:"page"`, label = file name, and `frontmatter` = the sanitized parsed YAML.
  - Heading nodes have `node_kind:"heading"`.
  - Every node is `file_type:"document"` with `source_location:"L<n>"`.
- Edges ([PKG extractors/markdown.py L493-540, L543-549](PKG/extractors/markdown.py)):
  - parent `contains` heading.
  - file `references` resolved target. There is one edge per target per file (`linked_targets` dedup), and the edge carries no verb or context.
  - `_MD_WIKILINK_RE` captures only the target (aliases and anchors are dropped). Links are scanned on every non-fenced line, including frontmatter.
- Inline code spans become `raw_calls` that the `markdown_mentions` resolver turns into `references` to code symbols. They never become `calls` ([PKG extractors/markdown.py L395-405, L432-457](PKG/extractors/markdown.py)).
- Wikilinks are resolved Obsidian-style: lexical first, then a vault-wide index (`_build_link_index`, `_vault_lookup`) ([PKG extractors/markdown.py L125-230, L259-335](PKG/extractors/markdown.py)). Releases v0.9.74 (#3905, dotted names), v0.9.80/0.9.85 (spaces and percent-encoding, #4178), and v0.9.93 (vault-relative wikilinks, #4559) fixed wikilink resolution ([Releases](https://github.com/Graphify-Labs/graphify/releases)).
- Routing:
  - `.md`/`.mdx`/`.qmd`/`.skill` map to `extract_markdown` in `_DISPATCH` ([PKG extract.py L8751-8754](PKG/extract.py)).
  - `detect.DOC_EXTENSIONS` includes `.md`, so `graphify extract` classifies notes as documents and sends them to the semantic pass ([PKG detect.py L49](PKG/detect.py); [PKG cli.py L4031-4052](PKG/cli.py)).
  - `--code-only` and `GRAPHIFY_BACKEND=none` both drop doc files entirely ("indexing code only") ([PKG cli.py L4053-4064, L4147-4162](PKG/cli.py)).
- `graphify update <path>` ("re-extract code files… (no LLM needed)") calls `watch._rebuild_code` ([PKG cli.py L2796-2845](PKG/cli.py)). That function adds every document with an AST extractor (.md) to the AST pass: "Include document files that have AST extractors (e.g. .md, .mdx, .qmd)" ([PKG watch.py L1827-1833](PKG/watch.py)).
  - A doc that already has a semantic (LLM) layer in the existing graph.json is skipped (#1915). The quick scan "stays as a fallback for docs with no semantic layer (the no-LLM doc-structure feature)" ([PKG watch.py L1841-1900, L1973-1979](PKG/watch.py)).
  - Running `graphify update` on a fresh copy of the brain (no graph.json) therefore produces a pure structural graph.
- v0.9.96 extends the watch quick scan to markdown that `detect()` classifies as a paper (#4750/#4751) ([Releases v0.9.96](https://github.com/Graphify-Labs/graphify/releases)).
- `frontmatter` is not under the `attributes` key, so `query` / `get_node` do not render it ([PKG serve.py L1177-1214, L2495-2500](PKG/serve.py)).

### Inferences
- Within D32, `graphify update <copy-of-brain>` is a released, LLM-free way to get a deterministic link graph. Running it on the brain *with* links intact would reproduce the authored [[wikilink]] structure exactly, though with every verb collapsed to `references`. Running it on the links-removed copy gives only page→heading `contains` edges.
- The NODE lines would show `loc=L<n>` for headings. With `--seed <file path>` and `explain`, that could point a reader to the right section, but the fact text still has to be read from disk.
- Calling `graphify.extractors.markdown.extract_markdown(path)` as a library function is also possible without editing Graphify. It is a public module function, re-exported in `graphify.extractors.__init__` L26/L61.

### Gaps
- I did not verify end to end that `update` on a directory with no prior graph writes a clustered graph.json for a docs-only corpus. The code path suggests it does: code_files includes the .md files, and it returns early only when both code_files and graph.json are absent. The help text frames the command as "code files".

---

## 7. Release notes ~0.9.80-0.9.96 relevant to docs corpora, rationale and query output

### Takeaway
No release in this range adds rationale rendering, a context-filter opt-out, or a prompt or verb-vocabulary control. The relevant changes are markdown link resolution, query correctness, and truncation honesty.

### Cited Findings (all from [Releases](https://github.com/Graphify-Labs/graphify/releases))
- **0.9.96** (2026-10-26, after the pin):
  - watch quick-scans markdown classified as a paper (#4750).
  - Obsidian export lists parallel relations (#4731).
  - An Ollama context sizing fix (#4761).
  - dedup namespaces a colliding cross-document reference stub instead of dropping it (#4743).
- **0.9.95** (2026-10-23):
  - `.yaml`/`.yml` are now structural code (#4706).
  - Skill-install security fix (#4513).
- **0.9.94**:
  - A markdown bare method name links only when its class is cited (#4617).
  - MCP `get_node` / `get_neighbors` and `explain` refuse a substring-only near-miss and suggest candidates (#4618).
- **0.9.93**:
  - Obsidian vault-relative wikilinks resolve (#4559).
  - Credential-shaped text in rationale labels is redacted (#4566).
  - `query` refuses an exact name shared by several nodes (#4511/#4517).
- **0.9.92**:
  - MCP keeps parallel edges through the graph.json round-trip and query output (#4500).
  - The extraction prompt pins source_file to the dispatched file (#4487).
- **0.9.90**:
  - dedup keeps same-name documents in different folders apart (#4410).
  - The query fallback keeps induced-subgraph edges (#4315).
- **0.9.88**:
  - `query --seed` added (#4293).
  - dedup path-qualifies `a/x.md` vs `b/x.md` (#4362).
  - LLM field aliases are folded: `file`/`filepath` to `source_file`, `relationship` to `relation` (#4391).
  - wiki index rows link to the correct same-label article (#3033).
- **0.9.87**: MCP `query_graph` seed order is by match strength (#4358).
- **0.9.86**:
  - `explain` refuses within-file ambiguity (#4320).
  - `explain` / `query` say how to get the full answer when truncated, and `explain --all` is added (#4323).
- **0.9.85**:
  - The incomplete-extraction message names a smaller `--token-budget` as the lever (#4280).
  - Markdown links to file names with spaces resolve (#4178).
- **0.9.80**:
  - Markdown links with spaces and percent-encoding resolve (#4178).
  - MCP caches the traversal view, about 1.6x faster `query_graph` (#4192).
- Earlier but relevant:
  - 0.9.72: GRAPH_REPORT drops rationale/concept nodes from listings (#3836), and wikilink escaped-alias parsing is fixed (#3772).
  - 0.9.76: same-heading document nodes in different files no longer merge (#4065).
  - 0.9.74: dotted-name wikilinks resolve (#3905).
- Still open: #2821 / #4576 / #2830 (rationale rendering), #2529 (inferred context filter), #2381 (rationale nodes hijacking seeds), and #2420 / #3143 (explain's 20-row cap and degree ranking) ([GitHub issue search](https://github.com/Graphify-Labs/graphify/issues?q=rationale)).

### Inferences
- Upgrading to 0.9.96 would not change any retrieval surface this study depends on. Staying on the 0.9.95 pin is safe for these questions.

### Gaps
- I did not check whether graphify.com docs or llms-full.txt describe surfaces differently. The installed source was treated as authoritative for 0.9.95.
