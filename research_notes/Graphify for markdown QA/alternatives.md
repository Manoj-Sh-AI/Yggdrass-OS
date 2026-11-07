# Alternatives to Graphify for typed link proposal and graph-aware retrieval over a personal markdown KB

Research date: 2026-10-26. Repo stats (stars, licence SPDX, last push, latest release) were pulled from the GitHub REST API on this date. Star counts are a popularity signal, not a quality signal.

## Q1. Candidate landscape: what each does, maturity, cost, markdown handling, typed relations, privacy, fit

### Takeaway
No surveyed tool does both jobs (typed, justified link proposals for review, plus fact-carrying graph retrieval) out of the box on a wikilinked markdown vault. The closest fits are: **Basic Memory** (same data model as Yggdras, deterministic, no LLM at index time, but no link *proposal*), **Graphiti** (typed edges via Pydantic, each edge stores a `fact` sentence plus source-episode provenance) and **LlamaIndex SchemaLLMPathExtractor** (hard vocabulary constraint with `strict=True`). The big GraphRAG family (MS GraphRAG, LightRAG, nano-graphrag, HippoRAG 2, Kotaemon) ignores wikilinks and frontmatter and builds its own entity graph from chunks.

### Cited Findings

**Activity snapshot (GitHub API, 2026-10-26)**

| Repo | Stars | Licence | Latest release | Last push |
|---|---|---|---|---|
| Graphify-Labs/graphify (current tool) | 136,009 | Apache-2.0 | v0.9.96, 2026-10-26 (pinned 0.9.95) | 2026-10-26 |
| microsoft/graphrag | 36,453 | MIT | v3.3.0, 2026-10-08 | 2026-10-26 |
| HKUDS/LightRAG | 40,348 | MIT | v1.5.7, 2026-09-02 | 2026-10-22 |
| gusye1234/nano-graphrag | 4,004 | MIT | v0.0.8, 2024-10-01 | 2026-01-27 |
| OSU-NLP-Group/HippoRAG | 4,077 | MIT | v1.0.0, 2025-02-27 | 2026-10-06 |
| topoteretes/cognee | 32,781 | Apache-2.0 | v1.6.6rc1, 2026-10-23 | 2026-10-26 |
| getzep/graphiti | 32,246 | Apache-2.0 | v0.31.2, 2026-10-20 | 2026-10-26 |
| run-llama/llama_index | 52,673 | MIT | v0.14.25, 2026-09-21 | 2026-10-23 |
| neo4j-labs/llm-graph-builder | 5,283 | Apache-2.0 | v0.8.7, 2026-07-23 | 2026-10-23 |
| mem0ai/mem0 | 67,856 | Apache-2.0 | ts-v3.3.1, 2026-09-25 | 2026-10-26 |
| basicmachines-co/basic-memory | 4,362 | AGPL-3.0 | v0.24.1, 2026-10-23 | 2026-10-26 |
| khoj-ai/khoj | 37,841 | AGPL-3.0 | 2.0.0-beta.28, 2026-03-26 | 2026-08-02 |
| neuml/txtai | 13,038 | Apache-2.0 | v9.14.0, 2026-10-06 | 2026-10-26 |
| Cinnamon/kotaemon | 25,830 | Apache-2.0 | v0.12.0, 2026-05-31 | 2026-07-14 |
| brianpetro/obsidian-smart-connections | 5,523 | custom "Smart Plugins License" (source-available) | 4.7.2, 2026-08-06 | 2026-10-10 |
| logancyang/obsidian-copilot | 7,891 | AGPL-3.0 | 4.0.16, 2026-10-23 | 2026-10-26 |
| glowingjade/obsidian-smart-composer | 2,332 | MIT | 1.2.9, 2026-01-26 | 2026-02-16 |
| nhaouari/obsidian-textgenerator-plugin | 1,993 | MIT | 0.8.7, 2026-04-27 | 2026-08-06 |
| SkepticMystic/graph-analysis | 535 | GPL-3.0 | 0.15.4, 2022-01-31 | 2026-01-12 |
| noduslabs/infranodus-obsidian-plugin | 175 | AGPL-3.0 | 0.10.0, 2026-08-04 | 2026-08-04 |
| MarkusPfundstein/mcp-obsidian | 4,499 | MIT | no GitHub releases | 2026-08-31 |
| cyanheads/obsidian-mcp-server | 701 | Apache-2.0 | v3.7.2, 2026-10-26 | 2026-10-26 |

Sources: GitHub repos — [graphify](https://github.com/Graphify-Labs/graphify), [graphrag](https://github.com/microsoft/graphrag), [LightRAG](https://github.com/HKUDS/LightRAG), [nano-graphrag](https://github.com/gusye1234/nano-graphrag), [HippoRAG](https://github.com/OSU-NLP-Group/HippoRAG), [cognee](https://github.com/topoteretes/cognee), [graphiti](https://github.com/getzep/graphiti), [llama_index](https://github.com/run-llama/llama_index), [llm-graph-builder](https://github.com/neo4j-labs/llm-graph-builder), [mem0](https://github.com/mem0ai/mem0), [basic-memory](https://github.com/basicmachines-co/basic-memory), [khoj](https://github.com/khoj-ai/khoj), [txtai](https://github.com/neuml/txtai), [kotaemon](https://github.com/Cinnamon/kotaemon), [smart-connections](https://github.com/brianpetro/obsidian-smart-connections), [obsidian-copilot](https://github.com/logancyang/obsidian-copilot), [smart-composer](https://github.com/glowingjade/obsidian-smart-composer), [textgenerator](https://github.com/nhaouari/obsidian-textgenerator-plugin), [graph-analysis](https://github.com/SkepticMystic/graph-analysis), [infranodus plugin](https://github.com/noduslabs/infranodus-obsidian-plugin), [mcp-obsidian](https://github.com/MarkusPfundstein/mcp-obsidian), [obsidian-mcp-server](https://github.com/cyanheads/obsidian-mcp-server)

**Per-tool findings**

- **Basic Memory** — Markdown files are the source of truth; edits to files update a local knowledge-graph DB. Note = YAML frontmatter (`title`, `type`, `tags`, `permalink`, custom fields kept as `entity_metadata`) + observations `- [category] content #tag (context)` + explicit relations `- relation_type [[Target]] (context)`; bare `[[Target]]` becomes a `links_to` relation; observations/relations are detected by syntax anywhere in the doc. — [Basic Memory NOTE-FORMAT.md](https://github.com/basicmachines-co/basic-memory/blob/main/docs/NOTE-FORMAT.md)
- Basic Memory advertises "Local-first. Plain text on your disk", an MCP server for Claude Code/Codex/Cursor/ChatGPT/Obsidian, a schema system (`bm_schema` infer/validate/diff), optional reranking via local FastEmbed cross-encoder or LiteLLM, and an optional hosted cloud with bidirectional sync. — [Basic Memory README](https://github.com/basicmachines-co/basic-memory)
- Basic Memory telemetry is Logfire-based and `configure_telemetry()` returns early unless `enable_logfire` is set (off by default in that function signature). — [basic_memory/telemetry.py](https://github.com/basicmachines-co/basic-memory/blob/main/src/basic_memory/telemetry.py)
- **Graphiti (Zep)** — temporal "context graph"; edges are Entity→Relationship→Entity triplets with validity windows; developer-defined entity and edge types via Pydantic ("prescribed") or learned ontology; every entity/relationship traces back to source episodes; hybrid retrieval (semantic + keyword + graph traversal); supports local OpenAI-compatible servers (Ollama, vLLM, llama.cpp, LM Studio) via `OpenAIGenericClient`, with a warning that non-OpenAI/Gemini providers "may result in incorrect output schemas and ingestion failures". — [Graphiti README](https://github.com/getzep/graphiti)
- Graphiti `EntityEdge` has a `fact: str` field ("fact representing the edge and nodes that it connects"), `fact_embedding`, `episodes: list[str]`, `valid_at`, `invalid_at`. — [graphiti_core/edges.py](https://github.com/getzep/graphiti/blob/main/graphiti_core/edges.py)
- Graphiti custom edge types are Pydantic models with docstrings, passed as `edge_types`; `edge_type_map` keyed by `(source_type, target_type)` lists allowed edge types; when a pair has no mapping, the extracted predicate is kept as the edge name with no custom schema (i.e. not a hard constraint). — [Graphiti docs: custom entity and edge types](https://help.getzep.com/graphiti/core-concepts/custom-entity-and-edge-types)
- Graphiti needs a graph DB (examples use Neo4j at `bolt://localhost:7687`). — [Graphiti README](https://github.com/getzep/graphiti)
- **LlamaIndex PropertyGraphIndex** — `SchemaLLMPathExtractor` takes `possible_entities`, `possible_relations` (Literal types) and `kg_validation_schema` (entity type → allowed relations); `strict=True` rejects triples outside the schema. `DynamicLLMPathExtractor` takes type lists as guidance only. `ImplicitPathExtractor` builds paths from existing `node.relationships` with no LLM. Triples are attached to their source chunk; retrievers (`LLMSynonymRetriever`, `VectorContextRetriever`, `TextToCypherRetriever`, `CypherTemplateRetriever`, custom) can return source chunk text with `include_text=True`. Docs do not mention per-triple justification. — [LlamaIndex PropertyGraphIndex guide](https://developers.llamaindex.ai/python/framework/module_guides/indexing/lpg_index_guide/)
- **Microsoft GraphRAG** — `extract_graph` is LLM-based with configurable `entity_types` (list) and a prompt file plus `max_gleanings`; `extract_claims` is off by default "because claim prompts really need user tuning"; an NLP-based `extract_graph_nlp` path (regex_english / syntactic_parser / cfg, SpaCy) exists that avoids LLM extraction. — [GraphRAG YAML config docs](https://microsoft.github.io/graphrag/config/yaml/)
- **LightRAG** — needs LLMs in four roles; LLM entity-relation extraction runs on every chunk; query modes local/global/hybrid/mix/naive; default storages are in-memory JSON/NanoVectorDB/NetworkX "not suitable for production"; supports incremental update and selective deletion; native markdown parser handles images/tables; recommends local models (Qwen3-30B-A3B-Instruct minimum for local extraction, bge-m3 embeddings); notes that without auth every server endpoint is public. — [LightRAG README](https://github.com/HKUDS/LightRAG)
- **HippoRAG 2** — builds on Personalized PageRank from HippoRAG with "deeper passage integration"; claims to beat standard RAG on factual, sense-making and associative tasks (+7% associative over SOTA embedding model). — [arXiv 2502.14802](https://arxiv.org/abs/2502.14802). Repo supports OpenAI-compatible/local vLLM endpoints, local Parquet embeddings, and an MCP server (`hipporag-mcp`). — [HippoRAG README](https://github.com/OSU-NLP-Group/HippoRAG)
- **Cognee** — "Runs locally for free — no API key required": without an LLM key it extracts the graph with a local GLiNER model and local embeddings; with a key it uses OpenAI by default; supports Ollama; custom data models and ontologies; a Postgres-only graph store is a "demo feature" with the production version "available as a licensed product". — [Cognee README](https://github.com/topoteretes/cognee)
- Cognee ontology support reads OWL (RDF/XML); extracted entities are grounded to ontology classes/individuals and marked `ontology_valid=True`; default `annotate` mode keeps unmatched entities; `strict` mode drops non-matching nodes and their edges. Docs do not say relation types are constrained. — [Cognee ontology guide](https://docs.cognee.ai/guides/ontology-support)
- **Neo4j LLM Graph Builder** — upload files/web sources, choose LLM, extract nodes/relationships/properties into Neo4j; supports a custom schema (node and relationship labels) in extraction settings; Ollama supported in dev deployment. — [llm-graph-builder README](https://github.com/neo4j-labs/llm-graph-builder)
- **Mem0** — in OSS v3, "the external graph store integration is removed from OSS; graph memory is now a built-in, always-on Mem0 Platform feature" (`enable_graph`/`graph_store` removed). — [Mem0 OSS v2→v3 migration](https://github.com/mem0ai/mem0/blob/main/docs/migration/oss-v2-to-v3.mdx)
- **Kotaemon** — RAG web UI with local LLMs (Ollama, llama-cpp-python) and GraphRAG integration; README notes "Official MS GraphRAG indexing only works with OpenAI or Ollama API". — [Kotaemon README](https://github.com/Cinnamon/kotaemon)
- **txtai** — "embeddings database" combining sparse/dense vector indexes, graph networks and relational DB; run local. — [txtai README](https://github.com/neuml/txtai)
- **Smart Connections** — ships a local embedding model, embeddings local by default, no API key; lists related notes with a similarity score; you drag a result into a note to create a link (no auto-insert); inline suggestions are Pro; no typed relations or explanations described; "source available" under a custom licence that restricts competing general-purpose Obsidian offerings; cloud model integrations moved to Smart Chat Pro. — [Smart Connections repo](https://github.com/brianpetro/obsidian-smart-connections)
- **InfraNodus plugin** — builds a concept graph of vault text, topical clusters, betweenness centrality, "gaps" between clusters and AI-suggested bridging ideas; text you visualize is sent to InfraNodus servers (stated as not saved) and graph structure plus some statements to OpenAI; subscription with free trial, API key needed for setup. README does not describe proposing note-to-note links. — [infranodus-obsidian-plugin](https://github.com/noduslabs/infranodus-obsidian-plugin)
- **LLM Wiki (Karpathy-style) Obsidian plugin** — LLM extracts entities/concepts into standalone wiki pages with bidirectional `[[links]]`; retrieval walks the wikilink graph with Personalized PageRank (no embeddings); "Lint wiki" finds duplicates, dead links, orphans, contradictions; `reviewed: true` protects a page; auto-maintenance off by default; local models via Ollama/LM Studio, but large-vault ingest "usually needs a long-context cloud model"; v1.28.0, Apache-2.0, ~65k downloads (repo GD4AI/obsidian-llm-wiki). Listing is promotional. — [Obsidian community listing: LLM Wiki](https://community.obsidian.md/plugins/karpathywiki)
- **Other Obsidian link-suggesters found:** Lumina (local-embedding related-note and tag suggestions, one-click `[[link]]` insert), Note Linker (scans for mentions of other note titles/aliases and presents candidates for confirmation), Notemd (LLM generates wiki-links for key concepts and creates concept notes). — [Obsidian AI plugins search results: Lumina](https://community.obsidian.md/plugins/lumina), [Note Linker](https://www.obsidianstats.com/plugins/obisidian-note-linker), [Sean Kim blog on AI linking plugins](https://blog.imseankim.com/obsidian-ai-plugin-smart-note-linking-auto-tagging-local-llm/)
- **Neural Composer** — community Obsidian plugin running a local LightRAG server that starts/stops with Obsidian, with a hybrid mode combining file reads and graph queries; graph is stored with the vault. — [Obsidian Forum: Neural Composer](https://forum.obsidian.md/t/neural-composer-local-graph-rag-made-easy-lightrag-integration/109891)

### Inferences
- Basic Memory's format is almost a superset match for Yggdras (frontmatter, one-line categorised facts with source context, verb-typed wikilinks). It is the strongest *storage/retrieval-side* comparator and a design reference, but it does not propose links; the AI writes them via MCP. AGPL-3.0 matters only if redistributed/served.
- For use case (1), the most controllable pipeline is a self-built extractor using LlamaIndex `SchemaLLMPathExtractor(strict=True)` or Graphiti custom edge types, fed with the Yggdras relation vocabulary and roster, writing candidates to a review queue. Graphiti's `fact` field gives a ready-made natural-language justification per edge; LlamaIndex gives chunk provenance but no rationale string.
- For use case (2), Graphiti and HippoRAG 2 both return fact/passage text with graph hits, which addresses Graphify's core weakness (no fact text in query output). LightRAG returns entity/relation descriptions plus chunks.
- nano-graphrag (last release 2024-10) and Graph Analysis (last release 2022-01) look stagnant; Mem0 OSS no longer offers graph memory, so it drops out.
- Under D32 (use Graphify whole), any of these would be an additional tool, not a Graphify modification.

### Gaps
- Exact LLM-call counts per document at build time for each tool were not found in primary docs (GraphRAG gleanings, LightRAG per-chunk extraction plus merge, Graphiti per-episode calls). Only qualitative statements are cited.
- Whether MS GraphRAG / LightRAG relations are free-text descriptions vs typed labels was not confirmed from the fetched pages (my prior knowledge: free-text description plus weight/keywords; unverified here).
- HippoRAG 2's OpenIE triple and synonym-edge details were not confirmed (only the abstract was fetched).
- Khoj, Smart Composer, Text Generator, Copilot for Obsidian and the MCP servers were not examined beyond activity stats; from their positioning they are chat/RAG/editing tools, not link-proposers (unverified).
- No independent stars/activity for Lumina, Note Linker, Notemd, Neural Composer, LLM Wiki repo.

## Q2. Which tools produce typed, explained relation proposals for an accept/reject queue, and which can be constrained to a vocabulary?

### Takeaway
Hard vocabulary constraint: LlamaIndex `SchemaLLMPathExtractor(strict=True)`; Cognee `strict` ontology mode (constrains nodes, not clearly relations); Neo4j LLM Graph Builder custom schema. Soft constraint plus per-edge explanation: Graphiti (edge types + `fact` sentence + episode provenance). None ships a human review queue for link proposals; the closest UX is Smart Connections / Note Linker / Lumina (suggest, user confirms) but those emit untyped links with no reasons.

### Cited Findings
- `SchemaLLMPathExtractor` with `strict=True` rejects triples outside `possible_relations` / `kg_validation_schema`; `DynamicLLMPathExtractor` only guides. — [LlamaIndex PropertyGraphIndex guide](https://developers.llamaindex.ai/python/framework/module_guides/indexing/lpg_index_guide/)
- Graphiti keeps the raw extracted predicate when no `edge_type_map` entry matches, so custom types are not a hard filter; each edge carries a `fact` string and source `episodes`. — [Graphiti custom types docs](https://help.getzep.com/graphiti/core-concepts/custom-entity-and-edge-types); [graphiti edges.py](https://github.com/getzep/graphiti/blob/main/graphiti_core/edges.py)
- Cognee strict ontology mode drops nodes whose type/name does not match and removes their edges; default mode keeps everything. — [Cognee ontology guide](https://docs.cognee.ai/guides/ontology-support)
- Neo4j LLM Graph Builder lets users define node and relationship labels for extraction. — [llm-graph-builder README](https://github.com/neo4j-labs/llm-graph-builder)
- GraphRAG constrains only `entity_types`; relation vocabulary config not shown. — [GraphRAG config](https://microsoft.github.io/graphrag/config/yaml/)
- Smart Connections suggests related notes with a similarity score; user drags to link; no typed relations or explanation described. — [Smart Connections repo](https://github.com/brianpetro/obsidian-smart-connections)
- Note Linker presents candidate links (title/alias mentions) for user confirmation before applying. — [Note Linker listing](https://www.obsidianstats.com/plugins/obisidian-note-linker)

### Inferences
- A Yggdras review queue would need to be built in-house regardless; the tool choice is only about the extractor. Strict schema extraction directly addresses Graphify's "everything is `conceptually_related_to`" problem.
- Note Linker's alias/title-mention approach is deterministic and $0, analogous to the alias-resolution work already scoped in Phase 1b; it could be a cheap first-pass baseline before any LLM.

### Gaps
- No tool found that outputs a separate "reason" field distinct from the relation fact (Graphiti's `fact` is the closest). Not verified whether LlamaIndex's prompt can be extended to return a rationale without custom parsing.
- No published precision numbers for strict-schema extraction on personal notes.

## Q3. Which tools respect existing wikilinks as ground truth and only add?

### Takeaway
Only the markdown-native tools treat wikilinks as first-class: Basic Memory (parses relations/wikilinks deterministically), LLM Wiki plugin (PPR over the wikilink graph, `reviewed: true` protection), Note Linker / Smart Connections (user-confirmed additions). The GraphRAG-family tools ingest text chunks and build a separate graph; they do not read or preserve wikilinks as edges.

### Cited Findings
- Basic Memory: files are source of truth; bare `[[Target]]` → `links_to`, `verb [[Target]]` → typed relation. — [NOTE-FORMAT.md](https://github.com/basicmachines-co/basic-memory/blob/main/docs/NOTE-FORMAT.md)
- LLM Wiki retrieval walks the `[[wiki-link]]` graph with Personalized PageRank; `reviewed: true` protects pages from overwrite. — [LLM Wiki listing](https://community.obsidian.md/plugins/karpathywiki)
- LlamaIndex `ImplicitPathExtractor` builds graph paths from existing node relationships with no LLM. — [LlamaIndex guide](https://developers.llamaindex.ai/python/framework/module_guides/indexing/lpg_index_guide/)
- A blog report says dashboard and map-of-content notes retrieve poorly because "embedding models don't read structure". — [productivity.dev local RAG over Obsidian](https://www.productivity.dev/local-rag-obsidian-vault/)

### Inferences
- With LlamaIndex, Yggdras's `graph.json` edges could be pre-loaded as relationships (via ImplicitPathExtractor or direct upsert into the property graph store) so the LLM extractor only adds; this is a plausible design, not a documented recipe.
- With Graphiti, existing edges would have to be inserted manually as typed edges; Graphiti's dedup/invalidation logic could then mark or merge LLM-proposed duplicates. Unverified behaviour.

### Gaps
- No tool documents an explicit "existing links are immutable, propose only new ones" mode.

## Q4. What do users report about quality on personal notes?

### Takeaway
Evidence is thin and anecdotal: a handful of blog/forum posts about LightRAG over Obsidian vaults, reporting low cost and better "connecting the dots" than vector search, but no measured accuracy. No independent evaluation on personal notes was found for any tool.

### Cited Findings
- Neural Composer's author built it because "standard vector search plugins weren't connecting the dots" in their vault. — [Obsidian Forum](https://forum.obsidian.md/t/neural-composer-local-graph-rag-made-easy-lightrag-integration/109891)
- One writer reports ~4,200 notes ingested for about $0.43 with Gemini 2.5 Flash and near-zero daily query cost (self-reported). — [DEV Community post](https://dev.to/numbpill3d/the-missing-piece-every-obsidian-user-needs-local-rag-that-actually-works-in-2026-2gfp)
- obsidianGraphRAG (personal project, LightRAG + local embeddings + Gemini) reports 15–30 min ingest per 1,000 notes. — [Jinstronda/obsidianGraphRAG](https://github.com/Jinstronda/obsidianGraphRAG)
- Duke post argues a vault is not automatically a RAG system without an added retrieval step. — [Duke DDMC](https://sites.duke.edu/ddmc/2026/05/30/can-obsidian-act-like-a-lightweight-rag-sometimes/)
- LightRAG's own README warns extraction needs stronger LLMs than plain RAG and local extraction needs at least a Qwen3-30B-A3B-class model. — [LightRAG README](https://github.com/HKUDS/LightRAG)
- LLM Wiki listing says local models work for queries but large-vault ingest usually needs a long-context cloud model. — [LLM Wiki listing](https://community.obsidian.md/plugins/karpathywiki)

### Inferences
- Since Yggdras already scores 35/35 on its retrieval eval, the bar for a retrieval replacement is high; the real gap is link proposal quality, where no user reports exist. The existing 81-pair link-recovery protocol is the right way to compare a candidate.

### Gaps
- No Reddit r/ObsidianMD or r/PKMS threads with quantitative quality comparisons were retrieved (search budget). Benchmarks in project READMEs (HippoRAG 2, Mem0 LoCoMo) are on public QA datasets, not personal notes.

## Q5. Licences and data handling

### Takeaway
All core libraries are MIT/Apache-2.0 except Basic Memory, Khoj, Obsidian Copilot, InfraNodus plugin (AGPL-3.0) and Smart Connections (custom source-available). Most support local models via Ollama/vLLM/OpenAI-compatible endpoints. Telemetry is on by default in Graphiti (PostHog) and present in Mem0, Cognee and Khoj; InfraNodus sends text to its servers and OpenAI.

### Cited Findings
- Graphiti telemetry: PostHog, controlled by `GRAPHITI_TELEMETRY_ENABLED`, default enabled (disabled during pytest). — [graphiti telemetry.py](https://github.com/getzep/graphiti/blob/main/graphiti_core/telemetry/telemetry.py)
- Mem0 has telemetry modules (`mem0/memory/telemetry.py`, env `MEM0_TELEMETRY`). — [mem0 repo](https://github.com/mem0ai/mem0/blob/main/mem0/memory/telemetry.py)
- Cognee has a `TELEMETRY_DISABLED` switch (in `cognee/shared/utils.py`). — [cognee repo](https://github.com/topoteretes/cognee/blob/main/cognee/shared/utils.py)
- Khoj has a telemetry service and docs page. — [Khoj telemetry docs](https://github.com/khoj-ai/khoj/blob/master/documentation/docs/miscellaneous/telemetry.md)
- Basic Memory telemetry (Logfire) is opt-in via `enable_logfire`. — [basic-memory telemetry.py](https://github.com/basicmachines-co/basic-memory/blob/main/src/basic_memory/telemetry.py)
- LightRAG: no telemetry module found by code search; server endpoints are public without auth (bind to 127.0.0.1). — [LightRAG README](https://github.com/HKUDS/LightRAG)
- Local model support: Graphiti (Ollama, vLLM, llama.cpp, LM Studio), HippoRAG (vLLM/OpenAI-compatible), Cognee (GLiNER without LLM; Ollama), LightRAG, Kotaemon, Neo4j builder (Ollama), txtai. — READMEs linked in Q1.
- InfraNodus: text to InfraNodus servers, graph + statements to OpenAI. — [infranodus plugin](https://github.com/noduslabs/infranodus-obsidian-plugin)
- Smart Connections: "Private and offline by default"; custom licence restricts competing Obsidian offerings. — [Smart Connections repo](https://github.com/brianpetro/obsidian-smart-connections)

### Inferences
- If any tool is trialled, set telemetry env vars off (Graphiti, Mem0, Cognee) and record that in config; this fits the "config from env in one place" convention.
- InfraNodus is a poor fit for a private second brain given cloud processing.

### Gaps
- Exact default state of Cognee and Mem0 telemetry (on vs off) not confirmed from the code.
- Query logging behaviour of each tool (beyond telemetry) not examined.
- Telemetry presence in MS GraphRAG, LlamaIndex, HippoRAG, txtai not checked.
