# Graphify on non-code corpora (docs, markdown notes, Obsidian vaults): community usage, guidance and measured QA results

Research date: 2026-10-26. All GitHub data pulled with `gh` from Graphify-Labs/graphify on that date. Read-only; Graphify was not installed or run.

Version context (important correction to the brief): the repo's **default branch is `v8`**, and releases are cut from it. Release `v0.9.96` (published 2026-10-26, after the 0.9.95 release of 2026-10-23) has `targetCommitish: v8`, and `compare v0.9.96...v8` returned `identical` (0 ahead, 0 behind) on 2026-10-26. So "targets v8" does not mean a separate future major version: a PR merged into `v8` ships in the next 0.9.x patch release. Unmerged PRs against `v8` are still unreleased. A few older PRs target the stale `main` or `v6` branches and look abandoned. — [gh release view / compare, Graphify-Labs/graphify](https://github.com/Graphify-Labs/graphify/releases/tag/v0.9.96)

## 1. What do issues, discussions, PRs, the README and docs recommend for docs, notes, Obsidian vaults and personal knowledge bases?

### Takeaway
The official material is about code. It offers no doc-QA or notes-QA guidance; markdown and Obsidian appear only as input types and as an *export* target. Recommendations for notes come from users. Their main point is that authored structure (wikilinks, markdown links, frontmatter) should be parsed deterministically, not re-discovered by the LLM. Several of those asks are still open or unmerged.

### Cited Findings
**Official docs / README (state on 2026-10-26)**
- The README pitch: `/graphify` "maps your entire project (code, docs, PDFs, images, videos) into a knowledge graph you can query instead of grepping". Code goes through tree-sitter; "Docs, PDFs, images and video use your assistant's model, or a configured API key, for a semantic pass". — [README (v8)](https://github.com/Graphify-Labs/graphify)
- `graphify install` "tells your assistant to consult the knowledge graph for codebase questions, preferring scoped queries like `graphify query "<question>"` over reading the full report". This matches the #580/#891 fix. — [README](https://github.com/Graphify-Labs/graphify)
- The docs "Ask better graph questions" guide covers `query` (BFS by default, `--dfs`), `explain` and `path`, using `--budget 1500` in its examples. It frames everything as "codebase questions". It gives **no guidance for docs, notes or markdown**, does not mention `get_node`/`get_neighbors` or the wiki, and tells the assistant to cite paths and source references and to flag INFERRED/AMBIGUOUS edges. — [docs.graphify.com/guides/querying](https://docs.graphify.com/guides/querying)
- graphify.com's llms-full.txt calls Graphify "the knowledge graph control plane for enterprise software: a code knowledge graph your AI coding assistant queries instead of grepping". It lists "Markdown & docs" as a data source and "Obsidian" as an export. Non-code inputs are "read by the model backend you configure and connected to the code it describes, tagged INFERRED". — [graphify.com/llms-full.txt](https://graphify.com/llms-full.txt)
- The README's `--wiki` flag ("build a markdown wiki from the graph") is meant as an agent entry point. But #2006 (open, 2026-07-18) shows `wiki/` is written only by an explicit `export wiki` and never refreshed by `update`, watch or hooks, while `AGENTS.md` says "If `graphify-out/wiki/index.md` exists, navigate it instead of reading raw files". The proposed fix is #2024 (staleness nudge). — [#2006](https://github.com/Graphify-Labs/graphify/issues/2006)
- #228 (open, 2026-04-11): the wiki's `index.md` uses `[[label]]` links that don't match the `_safe_filename()` files on disk, so agents outside Obsidian can't follow them. The fix PR #674 targets the stale `v6` branch and is unmerged. — [#228](https://github.com/Graphify-Labs/graphify/issues/228), [PR #674](https://github.com/Graphify-Labs/graphify/pull/674)

**User recommendations for vaults and notes**
- #295 (open, 2026-04-13, adelaidasofia) asks for a structural pre-pass for wikilinks and frontmatter before the LLM runs. On their 566-file vault, regex produced 10.4 edges/file (11,809 edges) in under 2 s, against 7.3 edges/file from the LLM on a 200-file batch. They estimate 50-65% token savings on link-heavy vaults. A 2026-05-29 comment (DavidPalazonUPCT, Obsidian PhD vault, ~700 nodes) found that after reinjecting `[[...]]` as EXTRACTED edges, "~97% of edges became EXTRACTED", and argues the wikilinks are the ground truth for a hand-curated vault. — [#295](https://github.com/Graphify-Labs/graphify/issues/295)
- #951 (open, 2026-05-20): on 1,256 Intercom help articles, 2,905 nodes were extracted and **1,636 (56%) were isolated** (≤1 connection), because LLM extraction "focuses on conceptual entity extraction, not syntactic link parsing". The user asked for markdown links as first-class edges. PR #1216 targets the stale `main` branch and is unmerged. — [#951](https://github.com/Graphify-Labs/graphify/issues/951)
- Released behaviour: a deterministic markdown extractor now exists (`graphify/extractors/markdown.py`). It emits heading nodes, `contains` edges and `references` edges for inline/reference links and `[[wikilinks]]` at EXTRACTED confidence. — [#2383](https://github.com/Graphify-Labs/graphify/issues/2383)
- **But** #2383 (open, 2026-08-02, 0.9.32) found that in the Claude Code `/graphify` skill pipeline, `.md` files are classified as `document` and sent to the LLM, so `extract_markdown` never runs. Later comments say headless `graphify extract --backend claude-cli` (0.9.57, 2026-09-11) has the same gap, and on an already-semantic docs-only corpus `graphify update` cannot close it either (2026-09-18). The fix PR #3614 (into `v8`) is open. — [#2383](https://github.com/Graphify-Labs/graphify/issues/2383), [PR #3614](https://github.com/Graphify-Labs/graphify/pull/3614)
- Wikilink resolution fixes that have shipped:
  - #2413: sibling-only resolution dropped **1,030 of 2,323 authored links (44%)** in a 499-file Obsidian vault. Closed 2026-09-06.
  - #3904: wikilinks to names containing a dot. Closed 2026-09-28.
  - #4177: links to file names with spaces. Closed 2026-10-07.
  - #3190: `update` dropped wikilinks to semantic-backed docs. Closed 2026-08-29.
  - #4559: wikilinks prefixed with the scan folder name. Fixed in 0.9.93, 2026-10-20.

  — [#2413](https://github.com/Graphify-Labs/graphify/issues/2413), [#3904](https://github.com/Graphify-Labs/graphify/issues/3904), [#4177](https://github.com/Graphify-Labs/graphify/issues/4177), [#3190](https://github.com/Graphify-Labs/graphify/issues/3190), [#4559](https://github.com/Graphify-Labs/graphify/issues/4559)
- Still open: #3333 (2026-09-04), where `[[#Heading]]` same-page anchors are dropped and `#Heading` fragments discarded; PRs #3348 and #3450 are unmerged. #224 (2026-04-11) asks for edge-labelled (typed) wikilinks. — [#3333](https://github.com/Graphify-Labs/graphify/issues/3333), [#224](https://github.com/Graphify-Labs/graphify/issues/224)
- #4750 (closed 2026-10-26): a `.md` note with arXiv markers and an "Abstract" heading gets classified as `paper`, and `graphify update` then gave it **zero nodes**. This "silently dropped 6 Markdown notes" in a knowledge-base repo. Fixed in **0.9.96**. — [#4750](https://github.com/Graphify-Labs/graphify/issues/4750)
- #4281 (open, 2026-10-13): doc node IDs drop the path, so `a/x.md` and `b/x.md` collide and one is lost. This matters for vaults that reuse note names in different folders. — [#4281](https://github.com/Graphify-Labs/graphify/issues/4281)

**Obsidian export (graph to vault, not vault to graph)**
- #1968 (open, 2026-07-17, 0.9.16): a docs-only corpus (167 Claude Code docs pages, ~650K words) gave 1,490 nodes, 1,916 edges and 149 communities. Every exported note was a bare stub (frontmatter, H1, Connections). The user's workaround was a post-processing pass that copies sources into `sources/` and links each note. PR #1973 `--with-sources` (into `v8`) is unmerged. — [#1968](https://github.com/Graphify-Labs/graphify/issues/1968), [PR #1973](https://github.com/Graphify-Labs/graphify/pull/1973)
- Chase AI blog (2026-06-08) describes the same workflow on the same Claude Code docs: 145 docs, 591 nodes, 685 links, 67 communities. Stubs are "bare bones" until sources are wired in. It recommends quarantining the export in a subfolder of the main vault and says the overhead isn't worth it for many uses. It reports no token or accuracy measurements. — [chaseai.io](https://www.chaseai.io/blog/graphify-obsidian-claude-code-second-brain)
- Discussions: #1340 (2026-06-16) wants a non-flat wiki layout for a knowledge base; the only reply suggests a separate classify-then-place step. #200 (2026-04-11) asks about Logseq/Foam vault creation (unanswered in what I saw). #117 (2026-04-09) is an RFC for a multi-corpus workspace (code, papers, meeting notes). — [Discussion #1340](https://github.com/Graphify-Labs/graphify/discussions/1340), [#200](https://github.com/Graphify-Labs/graphify/discussions/200), [#117](https://github.com/Graphify-Labs/graphify/discussions/117)

### Inferences
- Our setup (YAML frontmatter, one-line facts, `[[wikilinks]]`) is close to the case users say Graphify handles worst by default. Through the skill/LLM path the authored links get replaced by LLM-inferred concept edges, which is consistent with the `conceptually_related_to` noise we saw. How much of our graph came from `extract_markdown` versus the LLM depends on which entry point built it; it is worth checking the edge `confidence` mix in our graph.json.
- No official source recommends Graphify as a QA engine over notes. The only notes-oriented guidance is community-sourced.

### Gaps
- No docs.graphify.com page dedicated to notes or Obsidian input was found. I did not fetch the "Supported inputs" or "How it works" pages, so their markdown sections were not checked.
- Discussion #200 had no visible answer.

## 2. Reported benchmarks or evaluations on doc corpora (token reduction, accuracy, recall): what works and what fails?

### Takeaway
No published accuracy or recall benchmark exists for Graphify `query` on a markdown or notes corpus. The only measured retrieval-quality results from users are on code or mixed vaults, and they consistently show `query`/`explain` **below BM25**. The project's headline numbers either measure tokens only (71.5x) or come from a separate conversational-memory harness (LOCOMO/LongMemEval) built with embeddings, not the CLI `query` path.

### Cited Findings
- **The 71.5x claim** is a token ratio, not accuracy. The lucasrosati Obsidian+Graphify setup calls it a "historical illustration": about 20,000 tokens of source context against about 280 tokens of graph output, "not a measured reduction in complete session usage". It assumes the smaller output answers the same question, publishes no payloads or tokenizer, and reports no accuracy. Its corpus was a 126-file React/Supabase codebase, not notes. graphify.com's llms-full.txt still quotes "71.5x fewer tokens per session in an Obsidian, Claude Code and Graphify setup". — [lucasrosati/claude-code-memory-setup](https://github.com/lucasrosati/claude-code-memory-setup), [llms-full.txt](https://graphify.com/llms-full.txt)
- An X post by Connected Data (April 2026) repeats "1/71.5 of the original method" as a mixed-corpus result. — [X/Connected_Data](https://x.com/Connected_Data/status/2041827996806340736)
- **BENCHMARKS.md (v8, last updated 2026-07-05)**:
  - LOCOMO (n=300): QA accuracy 45.3%, recall@10 0.497 for "graphify (graph-expand)", against BM25 31.3%/0.362, hybrid RRF 43.3%/0.493 and dense RAG 41.3%/0.439.
  - LongMemEval-S (n=50): 76%, tied with dense RAG.
  - Graphs were built "AST-only with no LLM" plus a local BGE-m3 embedder. The reader and judge model was Kimi K2.6.
  - This is conversational memory, not markdown notes, and graph-expand barely beats hybrid RRF (45.3% vs 43.3%).

  — [BENCHMARKS.md (v8)](https://github.com/Graphify-Labs/graphify/blob/v8/BENCHMARKS.md)
- #1706 (open, 2026-07-07): the memory harness (`memory/runner.py`, the adapters) is not in the public repo. A maintainer-side reply (TPAteeq) confirms the build is deterministic, using "local embeddings (BGE-m3) plus structural edges, no LLM at ingest". — [#1706](https://github.com/Graphify-Labs/graphify/issues/1706)
- #3690 (closed 2026-10-05): BENCHMARKS.md was a 404 on `main`, and the headline metrics "test conversation memory, not code graphs". — [#3690](https://github.com/Graphify-Labs/graphify/issues/3690)
- **#3143 (open, 2026-08-27, ryantokam) is the closest analogue to our test**, run on a vault:
  - `explain` ranks neighbours by degree and caps at 20. Same vault, same 15 concepts: useful-source coverage was 34/75 at 5,694 nodes and **19/75 after a rebuild to 9,870 nodes**.
  - Plain BM25 filled 72/75 slots.
  - On blind relevance grading, BM25 precision@5 was **0.627** against **0.107** for `explain`.
  - Contributing causes: hub nodes crowd out the top 20, and 2,211 docstring `rationale` nodes add noise.

  — [#3143](https://github.com/Graphify-Labs/graphify/issues/3143)
- #4341 (open, 2026-10-11): `graphify benchmark` "measures answer size but never whether the answer is right". On 177 SWE-bench Lite issues (0.9.85), `query_graph` with MCP defaults (BFS, depth 3, ~2000 tokens) put the right file first 25% of the time, in the top 5 38%, and anywhere 62%. BM25 got 32% / 64% / 92% (top 50). — [#4341](https://github.com/Graphify-Labs/graphify/issues/4341)
- #4347 (closed 2026-10-11): `graphify benchmark` counted its own copy of the query instead of the answer `query_graph` returns. Older token numbers from it are suspect. — [#4347](https://github.com/Graphify-Labs/graphify/issues/4347)
- #3308 (open, 2026-09-03): in a two-agent comparison (5 cross-file questions × 2 repos), `graphify query` used **more** tool calls and tokens than plain Read/Grep: 13 vs 10 calls and 79.6k vs 53.1k tokens; 14 vs 12 and 83.5k vs 62.1k. `query` returns "a BFS/DFS node-and-edge listing", for example `TRUNCATED: showing 41 of 73 nodes (~2000-token budget)`, with no synthesized answer, and agents re-read source because node text is "a paraphrase, not a citable quote". — [#3308](https://github.com/Graphify-Labs/graphify/issues/3308)
- #3307 (open, 2026-09-03): `source_location` is null on most edges, so results can't cite lines. — [#3307](https://github.com/Graphify-Labs/graphify/issues/3307)
- #580 (closed 2026-04-28) was titled "Graphify not improving token efficiency in Claude Code sessions". A third-party page cites an open issue from a user who saw no improvement, and says "a third-party review of daily tasks reported around 49x". That third-party review was not traced to a primary source. — [#580](https://github.com/Graphify-Labs/graphify/issues/580), [nathanhodgson.com (updated 2026-09-22)](https://nathanhodgson.com/airesources/g/graphify-vs-obsidian-for-claude-code/)
- #3325 (open, 2026-09-03) offers a ground-truth doc corpus: GeoMind, 201 documents with 7,356 manual cross-links. No results have been posted. — [#3325](https://github.com/Graphify-Labs/graphify/issues/3325)

### Inferences
- Our result (7/35 from label-only `query` output, ~25/35 when Graphify only picks notes and we supply our own fact lines, 35/35 for our own pipeline) fits the community evidence. Graphify's node and edge dump is a weak *answer* surface. It is a moderate *selector*, and even as a selector user measurements put it below BM25.
- The project's strong LOCOMO numbers come from an embedding-based "graph-expand" adapter in an unreleased harness, so they say nothing about what `graphify query --budget 2000` returns on our vault.

### Gaps
- I found no published accuracy or recall evaluation of Graphify `query` specifically on markdown or Obsidian notes, by maintainers or users, beyond the vault-based `explain` measurement in #3143.
- I could not confirm whether the "graph-expand" adapter is available in released 0.9.x.

## 3. Blog posts, Reddit, HN, X, YouTube, dev.to/Medium write-ups: what workflows and results do they describe?

### Takeaway
Community write-ups mostly pair "Graphify for code" with "Obsidian for human notes", or use Graphify's Obsidian *export* for browsing. None that I found reports a measured QA result on notes. The recurring complaints are bare stub notes and the need to wire source content back in.

### Cited Findings
- Chase AI (2026-06-08): runs `graphify --obsidian` on the Claude Code docs, quarantines the export as a subfolder, then wires concept stubs to source docs (658 stubs to 146 docs). It claims Graphify is faster and more accurate than grep but gives no data, and notes the vault is "a markdown mirror of the graph". — [chaseai.io](https://www.chaseai.io/blog/graphify-obsidian-claude-code-second-brain)
- lucasrosati/claude-code-memory-setup: in skill form, `/graphify . --obsidian --obsidian-dir ~/vault/graphify/<project>` writes one note per function or module. The headless CLI lacks `--obsidian`, so the author symlinks `graphify-out/` into the vault. The setup is code-centred. — [GitHub](https://github.com/lucasrosati/claude-code-memory-setup)
- nathanhodgson.com (updated 2026-09-22) frames Graphify as mapping the code and Obsidian as holding decisions and notes, so the two are complementary. It recommends measuring your own before/after and using strict mode (`graphify install --project --strict`). — [nathanhodgson.com](https://nathanhodgson.com/airesources/g/graphify-vs-obsidian-for-claude-code/)
- Search results also surfaced these community repos and guides. Their content was not fetched or verified beyond the search summary:
  - graphsidian: an Obsidian vault of Claude Code project knowledge with Graphify graphs for "semantic search and impact analysis".
  - A dev.to guide pairing Graphify with code-review-graph, listing browser-only, per-project-vault and global-vault modes.
  - An Analytics Vidhya guide (2026-04).

  — [graphsidian](https://github.com/vinchen-dev/graphsidian), [dev.to](https://dev.to/mir_mursalin_ankur/graphify-code-review-graph-build-a-self-updating-knowledge-graph-for-claude-code-and-other-ai-j1m), [Analytics Vidhya](https://www.analyticsvidhya.com/blog/2026/04/graphify-guide/)
- Origin: Graphify went viral as a response to Karpathy's "LLM Knowledge Bases" / LLM-Wiki post (2026-04-03). It was pitched for personal knowledge management, with the 71.5x token figure. — [Towards Deep Learning](https://www.towardsdeeplearning.com/andrej-karpathy-asked-for-a-tool-48-hours-later-graphify-went-viral-10d8ead5f50e), [X/Connected_Data](https://x.com/Connected_Data/status/2041827996806340736). #1472 (2026-06-26) asks whether anyone has combined Graphify with an LLM-Wiki and has no replies. — [#1472](https://github.com/Graphify-Labs/graphify/issues/1472)
- Critique from a competitor: PENgram's dev.to post argues that Graphify doesn't type its relationships, so it can't say whether one note contradicts or supersedes another. This is a vendor claim, seen only in a search snippet. — [dev.to/penfieldlabs](https://dev.to/penfieldlabs/we-fixed-karpathys-llm-wiki-pengram-is-the-typed-knowledge-graph-pipeline-everyone-asked-for-j3j)
- Alternative pattern for vault QA: Jesse Vincent's knowledge-graph-tools (2026-03-20, not Graphify) treats every vault note as a node and every `[[wikilink]]` as an edge, plus SQLite and vector search. In anecdotal use on a ~3,300-note vault, the agent skipped `Originated by:` frontmatter and answered wrongly (5 of 13 results misattributed). The author's lesson: structure shows that a connection exists, content shows what it means, and metadata shows whose it is. — [blog.fsck.com](https://blog.fsck.com/agent-blog/2026/03/20/knowledge-graph/)
- PR #2859 (open, 2026-08-18) proposes a `graphify idea` workflow that sends idea text to InfraNodus and writes an Obsidian note plus a Cytoscape graph. It is unmerged. — [PR #2859](https://github.com/Graphify-Labs/graphify/pull/2859)

### Inferences
- Users who get value from Graphify on notes use it for browsing or for picking files, then read the source content. That is the same pattern as our ~25/35 "Graphify chooses notes, we send fact lines" arm.

### Gaps
- Searches turned up **no Reddit (r/ObsidianMD, r/LocalLLaMA, r/ClaudeAI) or Hacker News threads** on Graphify for notes, and no YouTube transcripts were checked. That signal is missing, not negative.
- Medium and Analytics Vidhya posts were not fetched.

## 4. Open issues and roadmap items that would change doc-corpus QA

### Takeaway
Several open PRs into `v8` (the release branch) would directly improve notes QA: rationale rendering, frontmatter/body seeding, routing markdown through the structural extractor, and file-type-weighted seeding. None is merged as of 0.9.96. There is no public roadmap or milestones.

### Cited Findings
- **Rationale rendering**: #2821 (open, 2026-08-17). PR #4576 (into `v8`, opened 2026-10-20) adds an opt-in `--rationale` for `query`/`explain` and `include_rationale` for `query_graph`/`get_node`, sanitised and capped. It supersedes PR #2830, which has conflicted since 2026-08-20. A commenter says "825 of 2170 semantic nodes carry a `rationale` and none is printed today". Unmerged. — [#2821](https://github.com/Graphify-Labs/graphify/issues/2821), [PR #4576](https://github.com/Graphify-Labs/graphify/pull/4576)
- **Rationale scoring has shipped** (separate from rendering): #2293 was fixed in **v0.9.54** (2026-09-05). The scorer ranks a rationale match as its own tier between exact-label and source-path. So rationale can pick seeds but is still not printed. — [#2293](https://github.com/Graphify-Labs/graphify/issues/2293)
- **Descriptions not surfaced**: #3026 (open, 2026-08-24). `query`, `explain` and all `serve` MCP tools omit `node.description`, and only `get_node` shows `community_name`. PR #3245 is referenced. — [#3026](https://github.com/Graphify-Labs/graphify/issues/3026)
- **Frontmatter is invisible to query**:
  - #3313 (open, 2026-09-03): seeding ignores node attributes.
  - In a PR #3636 comment (2026-10-04), sortakool reports that 0.9.73 `extract_markdown` stores YAML frontmatter on the page node but `_node_search_text` never reads it. On a 379-file one-fact-per-file memory vault, "4/4 description-only terms return 'No matching nodes found'".
  - The PR author then made `extract_markdown` derive a `body` from frontmatter `description` (falling back to `summary`) and score it at a lower weight (0.35 vs rationale 0.75), because an unweighted body match measured *worse*.
  - PR #3636 (into `v8`) is unmerged.

  — [#3313](https://github.com/Graphify-Labs/graphify/issues/3313), [PR #3636](https://github.com/Graphify-Labs/graphify/pull/3636)
- **Markdown routing**: PR #3614 (into `v8`, open) would send markdown through the structural pass in the skill pipeline (#2383). — [PR #3614](https://github.com/Graphify-Labs/graphify/pull/3614)
- **Seed ranking**:
  - #2384 (open, 2026-08-02): local variables win seeds, answers tunnel into one community, and edge confidence and weight "never affect retrieval", so AMBIGUOUS edges rank the same as EXTRACTED ones.
  - PR #4601 (into `v8`): weight seed scoring by file type.
  - PR #2975: downweight rationale-prefix seeds.
  - #2381: doc/test rationale nodes hijack seeds.
  - #2962: descriptive docstring verbs out-seed real identifiers.

  — [#2384](https://github.com/Graphify-Labs/graphify/issues/2384), [PR #4601](https://github.com/Graphify-Labs/graphify/pull/4601), [#2381](https://github.com/Graphify-Labs/graphify/issues/2381), [#2962](https://github.com/Graphify-Labs/graphify/issues/2962)
- **Context-filter inference**: #2529 (open, 2026-08-07) is still reproducible on 0.9.82 (2026-10-09 comment). — [#2529](https://github.com/Graphify-Labs/graphify/issues/2529)
- **No synthesized answer mode**: #3308 (open) asks for a `graphify ask` that returns a cited answer. — [#3308](https://github.com/Graphify-Labs/graphify/issues/3308)
- **Relation vocabulary**: #377 (2026-04-16). Maintainer safishamsi says the relation set (`calls|implements|references|cites|conceptually_related_to|shares_data_with|semantically_similar_to|rationale_for`) was chosen to span code, docs and papers. `conceptually_related_to` is "soft semantic affinity when no harder edge fits". No issue proposing a richer vocabulary for notes was found. — [#377](https://github.com/Graphify-Labs/graphify/issues/377)
- Related: #3948 (open), where `semantically_similar_to` is chunk-scoped and never emitted across chunks; #4199 (closed 2026-10-07), where AMBIGUOUS edges distorted suggested questions and clustering; #207 and #296 (open), entity canonicalisation to merge duplicate concepts across files. — [#3948](https://github.com/Graphify-Labs/graphify/issues/3948), [#4199](https://github.com/Graphify-Labs/graphify/issues/4199), [#207](https://github.com/Graphify-Labs/graphify/issues/207)
- **Markdown parser bugs** opened 2026-10-26: #4787, fence tracking is a toggle so code in `~~~` or nested fences becomes headings (PR #4788); #4790, heading labels keep trailing `#`s and headings indented 1-3 spaces are dropped (PR #4791). — [#4787](https://github.com/Graphify-Labs/graphify/issues/4787), [#4790](https://github.com/Graphify-Labs/graphify/issues/4790)
- **Obsidian export** is still open: #1968/PR #1973 `--with-sources`, #2204 colour groups, #2650 case collisions, PR #2767 filtering weak links. Released in 0.9.96: Obsidian notes list every parallel relation between two nodes, not just the first (#4731). — [0.9.96 release notes](https://github.com/Graphify-Labs/graphify/releases/tag/v0.9.96)
- Agent write-back: #939 (open, 2026-05-19) proposes AGENT_INFERRED edges learned during sessions, motivated by Obsidian vaults. — [#939](https://github.com/Graphify-Labs/graphify/issues/939)
- `gh api .../milestones` returned nothing, so there are no public milestones. — [Graphify-Labs/graphify](https://github.com/Graphify-Labs/graphify)

### Inferences
- If PRs #4576 and #3636 (plus #3614) merged, a later 0.9.x would let `query` print rationale and match frontmatter `description`. That is the gap behind our 7/35 label-only result. Under D32 (adopt whole, never fork), we would have to wait for upstream releases rather than apply these branches.
- The volume of open ranking PRs (#4341 cites 20+) means `query` behaviour may shift between patch releases. Pin the version for eval comparisons.

### Gaps
- No maintainer comment on whether or when #4576, #3636 or #3614 will merge.
- No roadmap document was found.

## 5. Is there maintainer guidance on whether Graphify is meant for doc QA or for code navigation?

### Takeaway
Current official positioning is code-first ("code knowledge graph ... for enterprise software"), with docs as supporting context attached to code. The original April 2026 pitch was broader (Karpathy-style personal knowledge base). I found no maintainer statement endorsing Graphify as a QA engine over notes.

### Cited Findings
- The repo description (2026-10-26) reads: "Turn any codebase, with its docs, SQL schemas, configs, and PDFs, into a queryable knowledge graph. A /graphify skill for Claude Code, Cursor, Codex, and Gemini CLI". — [Graphify-Labs/graphify](https://github.com/Graphify-Labs/graphify)
- graphify.com describes "a code knowledge graph your AI coding assistant queries instead of grepping", with non-code inputs "connected to the code it describes". — [llms-full.txt](https://graphify.com/llms-full.txt)
- The README leads with Graphify Cloud ("Cut agent token spend by 80%") and team code workflows. — [README](https://github.com/Graphify-Labs/graphify)
- #245 (open, 2026-04-12) asked whether to lead with "coding-assistant skill" or "persistent personal/work knowledge graph" (the latter tied to the Penpax site). Community replies favoured leading with code. No maintainer reply was seen. — [#245](https://github.com/Graphify-Labs/graphify/issues/245)
- safishamsi's GitHub profile describes Graphify as turning "a folder of code, docs, papers, images, or video into a queryable knowledge graph". — [github.com/safishamsi](https://github.com/safishamsi)
- Maintainer activity on doc and notes bugs is real: #4559 and #4750 were fixed within days in 0.9.93 and 0.9.96. Notes corpora are supported, but as ingest and graph correctness work, not QA tuning. — [#4559](https://github.com/Graphify-Labs/graphify/issues/4559), [#4750](https://github.com/Graphify-Labs/graphify/issues/4750)

### Inferences
- Graphify's design point is navigation (seed, traverse, hand the agent pointers), not answer synthesis. Its own guidance tells the agent to check sources for details. Using it as a note *selector* in front of our own fact lines is consistent with how the tool is meant to be used. Expecting answers from `query` output alone is not.

### Gaps
- No explicit maintainer statement ("Graphify is or is not intended for notes QA") was found in issues, discussions or docs.
