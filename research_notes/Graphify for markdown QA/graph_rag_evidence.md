# Graph-based retrieval (GraphRAG-style KGs) vs simpler retrieval for QA over small curated markdown knowledge bases

Scope note: research done 2026-10-26. Measured results are separated from authors' claims where possible. Nearly every published benchmark uses corpora far larger and messier than Yggdras (about 1M+ tokens, Wikipedia passages, novels, news). No study found evaluates a hand-linked personal vault, so applicability to Yggdras is inferred, not measured.

## Q1. What do benchmarks say about accuracy, cost and latency of graph RAG vs simpler RAG? When does it win or lose?

### Takeaway
The 2025–2026 controlled studies agree. Plain RAG matches or beats GraphRAG on single-hop and detail lookups. Graph methods win modestly on multi-hop, comparison, temporal and summary questions. Earlier large "wins" (MS GraphRAG, LightRAG) came mostly from position- and length-biased LLM-judge win rates. Costs differ by orders of magnitude: per-query tokens run from about 1k (HippoRAG2) to about 330k (MS GraphRAG global).

### Cited Findings
**Han et al., "RAG vs. GraphRAG: A Systematic Evaluation and Key Insights" (arXiv 2502.11371, Feb 2025, rev. to 2026).** Measured with Llama 3.1-8B/70B, extraction by GPT-4o-mini. Datasets: HotpotQA (1,000 dev questions), MultiHop-RAG (2,556 queries), NQ, NovelQA. — [arXiv](https://arxiv.org/html/2502.11371v2)
- F1 on NQ, 8B/70B: RAG 64.78/68.18; KG-GraphRAG triplets-only 34.28/28.50; triplets+text 50.27/53.88; Community-GraphRAG Local 63.01/65.44; Global 54.48/55.05; HippoRAG2 61.03/64.03. — [arXiv](https://arxiv.org/html/2502.11371v2)
- F1 on HotpotQA, 8B/70B: RAG 60.04/63.88; HippoRAG2 63.01/64.93; Community Local 61.66/64.60; triplets-only 25.02/30.73. — [arXiv](https://arxiv.org/html/2502.11371v2)
- MultiHop-RAG accuracy, 70B: RAG 65.77; Community Local 71.17; HippoRAG2 69.87. — [arXiv](https://arxiv.org/html/2502.11371v2)
  - The graph gains concentrate in Temporal (49.06 vs 25.73) and Comparison (60.16 vs 56.31) questions.
  - On Null (unanswerable) queries, Community Global collapsed to 13.95 vs RAG 91.36, which points to hallucination.
- NovelQA, 8B: RAG 57.12 > HippoRAG2 56.54 > Community Local 53.03. — [arXiv](https://arxiv.org/html/2502.11371v2)
- Token-matched RAG (more chunks, same context size) scored 71.01 on MultiHop-RAG, matching GraphRAG's 71.17. Part of the graph "win" is just more context. — [arXiv](https://arxiv.org/html/2502.11371v2)
- Complementarity on MultiHop-RAG (8B): 13.6% of queries were correct only with GraphRAG and 11.6% only with RAG. — [arXiv](https://arxiv.org/html/2502.11371v2)
- Cost on MultiHop-RAG (the paper's units are unclear):
  - Construction: RAG 135, KG-GraphRAG 7,702, Community-GraphRAG 5,560.
  - Retrieved tokens: RAG 3,631, Community-GraphRAG 9,770.
  - Generation time, 70B: RAG 3,640 vs GraphRAG 6,272.
  - Source: [arXiv](https://arxiv.org/html/2502.11371v2)

**Xiang et al., "When to use Graphs in RAG" / GraphRAG-Bench (arXiv 2506.05690, ICLR 2026).** Two corpora (Gutenberg novels; NCCN medical guidelines) and four task levels, with GPT-4o-mini as the generator. — [arXiv](https://arxiv.org/html/2506.05690v3)
- L1 fact retrieval accuracy:
  - Novel: RAG+rerank 60.92, HippoRAG2 60.14, LightRAG 58.62, MS-GraphRAG 49.29, RAPTOR 49.25.
  - Medical: HippoRAG2 66.28, RAG+rerank 64.73, LightRAG 63.32, MS-GraphRAG 38.63.
  - Source: [arXiv](https://arxiv.org/html/2506.05690v3)
- L2 complex reasoning (ROUGE-L): graph methods win clearly. Novel: HippoRAG2 33.42 vs RAG 15.39. Medical: 36.97 vs 15.57. — [arXiv](https://arxiv.org/html/2506.05690v3)
- Average tokens per query (novel set): — [arXiv](https://arxiv.org/html/2506.05690v3)

  | Method | Tokens per query |
  |---|---|
  | Vanilla RAG | 879 |
  | HippoRAG2 | 1,008 |
  | RAPTOR | 3,441 |
  | HippoRAG | 7,208 |
  | MS-GraphRAG local | 38,707 |
  | LightRAG | 100,832 |
  | MS-GraphRAG global | 331,375 |

- Authors' guideline (a claim): use basic RAG for single-passage lookups; use GraphRAG for multi-hop reasoning and synthesis across distant passages; prefer compact graphs (HippoRAG2) when token cost matters. — [arXiv](https://arxiv.org/html/2506.05690v3)

**Edge et al., Microsoft "From Local to Global" GraphRAG (arXiv 2404.16130, Apr 2024, rev. Feb 2025).** — [arXiv](https://arxiv.org/html/2404.16130v2)
- Corpora: podcast transcripts (about 1M tokens, 1,669 chunks) and news (about 1.7M tokens, 3,197 chunks). 125 *global sensemaking* questions per dataset.
- Win rates vs vector RAG, judged by an LLM:
  - Comprehensiveness: 72–83%.
  - Diversity: 62–82%.
  - Directness: vector RAG produced the most direct answers in all comparisons.
- Root-level community summaries used about 2.3–2.6% of the source-text tokens.
- Indexing: 281 minutes for the podcast corpus with gpt-4-turbo.
- Note: this targets "themes of the corpus" questions, not factual lookups.

**Microsoft LazyGraphRAG (MSR blog, Nov 2024).** Claims indexing cost identical to vector RAG and 0.1% of full GraphRAG's, with global-query quality comparable to GraphRAG Global at more than 700x lower query cost. These are vendor claims and were not independently verified. — [Microsoft Research](https://www.microsoft.com/en-us/research/blog/lazygraphrag/)

**Zeng et al., "How Significant Are the Real Performance Gains? An Unbiased Evaluation Framework for GraphRAG" (arXiv 2506.06331, Jun 2025).** — [arXiv](https://arxiv.org/abs/2506.06331)
- Comparing LightRAG against itself, LLM-judge win rates differed by more than 30% depending on answer order.
- A length gap of about 25 tokens could swing win rates by more than 50%.
- After controlling for these biases, gains for three GraphRAG methods were "much more moderate" than previously reported.

**HippoRAG 2 (arXiv 2502.14802, Feb 2025).**
- Design: open-IE triples plus Personalized PageRank from seed nodes, with LLM "recognition memory" filtering of triples. — [arXiv](https://arxiv.org/pdf/2502.14802)
- A secondary citation reports MuSiQue Recall@5 of 74.7 vs a 69.7 dense baseline (NV-Embed-v2). A separate reproduction found a vector-only baseline at 69.8, so the margin is about 5 points. I did not verify these against the primary table. — [arXiv 2603.28886](https://arxiv.org/pdf/2603.28886)

### Inferences
- Yggdras's eval is dominated by entity-anchored factual and 1–2-hop questions. The literature predicts no graph-RAG gain on this question type, and often a loss.
  - Losses come from added noise (GraphRAG-Bench L1) and from facts the extracted KG lacks (Han et al.).
  - This matches the Graphify result (7/35 label-only).
- The only robust graph wins are multi-hop, temporal and comparison questions, plus corpus-wide "themes" questions.
  - Yggdras already gets multi-hop via its hand-made wikilink neighbour expansion.
  - The remaining possible value is global or summary queries ("what themes recur in my notes about X?").
- Cost per correct answer at Yggdras's current $0.0006 is roughly 1–3 orders of magnitude below any LLM-built graph's query-time token load (LightRAG about 100k tokens per query), before counting build cost.

### Gaps
- No benchmark found uses a corpus of tens to thousands of short, curated notes. All cited corpora are at least about 1M tokens or Wikipedia-scale.
- HippoRAG 2's own 2Wiki and MuSiQue QA tables were not verified from the primary PDF.
- Han et al. do not state units for construction and retrieval time.

## Q2. Existing human links (wikis, Obsidian) vs LLM-extracted edges; hybrid designs

### Takeaway
No study compares authored wikilinks against LLM-extracted edges on a personal vault. The closest evidence is old but strong: retrievers that walk Wikipedia's human hyperlink graph beat the prior state of the art on multi-hop QA. Separately, LLM-extracted KGs miss about a third of answer entities. Together these favour authored links as the backbone, with LLM edges as an optional, reviewed supplement.

### Cited Findings
- Asai et al., "Learning to Retrieve Reasoning Paths over Wikipedia Graph" (ICLR 2020): a recurrent retriever that walks Wikipedia's human-authored hyperlink graph reported more than 14 points over the previous best model on HotpotQA full-wiki (authors' claim from the abstract). — [arXiv](https://arxiv.org/abs/1911.10470)
- LLM-built KGs are incomplete. Only about 65.8% (HotpotQA) and 65.5% (NQ) of answer entities appeared in the extracted KG. — [Han et al.](https://arxiv.org/html/2502.11371v2)
- Answer-containing retrieval, HotpotQA: RAG 0.886 vs KG triplets-only 0.392. On NQ, Community Local fell to 0.422 vs RAG 0.867. — [Han et al.](https://arxiv.org/html/2502.11371v2)
- Han et al. also report that KG-only retrieval underperforms because the graphs are incomplete, and that adding the source text back helps. — [Han et al.](https://arxiv.org/html/2502.11371v2)
- Obsidian RAG projects (e.g., ObsiRag) treat wikilinks as the graph: hybrid search plus depth-1 link traversal plus citations. Its published materials give no measured numbers. — [GitHub ObsiRag](https://github.com/Simon-Busch/obsiRag)
- A graph-memory paper argues that fixed N-hop neighbour expansion only works when evidence is explicitly linked, and that it adds noise. — [MRAgent, arXiv 2606.06036](https://arxiv.org/html/2606.06036v1)

### Inferences
- In a curated vault, authored typed wikilinks ("replaced by [[jack-swigert]]") are higher precision than open-IE triples, and they are complete by construction for the relations the author cared about. The known LLM-extraction failure (about 34% of answer entities missing) does not apply to them.
- Where LLM extraction could add value is *proposing missing links*. This should go through a review queue, not straight into the retrieval graph. That hybrid pattern is not benchmarked in the literature; it is design reasoning.
- The noise risk of 1-hop expansion grows with node degree. Hub notes (e.g., "NASA") may need neighbour capping or relevance filtering as the vault grows.

### Gaps
- No published head-to-head of authored links vs LLM edges on the same corpus. The ObsiRag evaluation is unreported.
- No evidence on human-in-the-loop "LLM proposes, human accepts" link curation quality or effort.

## Q3. Agentic graph-walk / iterative retrieval vs one-shot subgraph retrieval

### Takeaway
Iterative, agentic retrieval improves hard multi-hop sets (MuSiQue +9 to +16 SubEM over single-pass graph RAG in GraphSearch). It does so at several times the LLM calls, and token use climbs steeply with question complexity. Papers rarely report cost or stop criteria. For easy 1–2-hop questions the gain is unproven, and a bounded loop with early exit is the recommended shape.

### Cited Findings
**GraphSearch (arXiv 2509.22009, Sep 2025).** — [arXiv](https://arxiv.org/html/2509.22009)
- Design: an agentic workflow with decomposition, grounding, drafting, an evidence-verification (accept/reject) step and query expansion. It uses dual-channel retrieval over text chunks and graph triples.
- Datasets: 300 questions each from HotpotQA, MuSiQue and 2Wiki; 512 each from three domain sets.
- Results with Qwen2.5-32B (SubEM):
  - LightRAG on MuSiQue: 35.00 → 51.00.
  - PathRAG on MuSiQue: 46.33 → 55.33.
  - LightRAG on 2Wiki: 81.67 → 85.00, a small gain on the easier set.
- LLM calls, latency, cost and maximum iterations are not reported.

**Think-on-Graph 2.0 (arXiv 2407.10805).** — [arXiv](https://arxiv.org/pdf/2407.10805)
- Design: iterative KG and text exploration.
- Cost: an upper bound of about 2D + (D−1) + 1 API calls per question for D iterations. The authors acknowledge the multi-hop exploration costs a relatively high number of API calls.
- Batching relation pruning into one call cut that stage to about 45% of ToG-1's time. The NaiveRAG baseline used the fewest calls.

**MRAgent graph memory (arXiv 2606.06036, Jun 2026).** — [arXiv](https://arxiv.org/html/2606.06036v1)
- Reports that one-shot retrieval is insufficient for complex multi-hop queries.
- Reasoning-enabled traversal beat structure-only variants across memory structures.
- Multi-hop recall improved by more than 30% across successive steps.

**GRASP (arXiv 2605.16598, May 2026).** Notes that token usage "grows rapidly" with question complexity, driven by repeated LLM calls and expanding context. — [arXiv](https://arxiv.org/pdf/2605.16598)

**GraphWalk (arXiv 2604.01610).** Uses a minimal tool set, including a "return all neighbours of a node" tool. This is close to a get_neighbors design. — [arXiv](https://arxiv.org/pdf/2604.01610)

**Practitioner blog (opinion, not a benchmark).** Recommends a few LLM rounds with early exit when evidence is sufficient, and deeper rounds only for ambiguous or many-hop questions. — [vadim.blog](https://vadim.blog/agentic-graphrag-reasoning-planning/)

**Hybrid routing (Han et al.).** On MultiHop-RAG with 70B: — [Han et al.](https://arxiv.org/html/2502.11371v2)
- *Selection* (route each query to RAG or GraphRAG): +1.1 points.
- *Integration* (concatenate both contexts): +6.4 points, to 77.62, but with the highest generation time (9,674 vs 3,640 for RAG).
- With the 8B model, Integration hurt Null-query accuracy because the longer context led to hallucination.

### Inferences
- Yggdras's current design (pick 1–2 nodes, then a deterministic 1-hop neighbour dump) is effectively one-shot subgraph retrieval with a hop budget of 1. The literature says this is ceiling-limited only for 3+-hop or chain questions.
- A sensible extension is a fallback agent loop, triggered only when the answer call signals insufficient evidence:
  - tools such as get_node, get_neighbors(slug, relation?), and possibly shortest_path;
  - a hop or turn budget of about 2–3, and early exit.
  - This keeps the cost of easy questions at today's level. The design is inferred; no paper benchmarks it on small corpora.
- Any loop should be measured as cost per correct answer, since gains on easy sets (2Wiki +3 SubEM) are small relative to the added calls.

### Gaps
- No found paper reports dollars per correct answer or latency for agentic graph walks against one-shot retrieval.
- No standard stop criterion is reported. GraphSearch's reflection-based stopping is unspecified.

## Q4. Failure modes of LLM-extracted graphs and mitigations

### Takeaway
The documented failures are:
- missing facts (about 34% of answer entities absent);
- ambiguous, context-free triples;
- redundant or synonymous relation phrases and entity duplicates.

The mitigations with evidence behind them are:
- keeping the source text attached to triples;
- LLM-driven entity and relation clustering (KGGen);
- open extraction followed by schema canonicalization (EDC);
- schema-constrained extraction against a fixed relation vocabulary.

### Cited Findings
- Missing facts: about 65.8% and 65.5% answer-entity coverage in the KG (HotpotQA, NQ). Triplets-only retrieval lost about 25–35 F1 vs RAG. Adding the text back recovered much of the gap (NQ 70B: 28.50 → 53.88). — [Han et al.](https://arxiv.org/html/2502.11371v2)
- Ambiguity: HOLMES (arXiv 2406.06027) argues that query-agnostic triple extraction yields "ambiguous" facts that "lack context". It proposes query-relevant distilled KGs, reportedly using up to 67% fewer tokens than the prior state of the art on HotpotQA and MuSiQue. — [arXiv](https://arxiv.org/abs/2406.06027v1)
- Entity and relation duplication — KGGen (NeurIPS 2025, arXiv 2502.09956): — [arXiv](https://arxiv.org/html/2502.09956v2)
  - Mitigation: LLM extraction, then cross-source aggregation, then an iterative cluster-and-validate step that merges synonyms ("NYC"/"New York City", tense and plural variants).
  - A secondary source reports MINE information-retention scores of 66.07% (KGGen) vs 47.80% (GraphRAG) vs 29.84% (OpenIE). I did not verify these against the paper.
- Relation sprawl: EDC (Extract–Define–Canonicalize) runs open extraction first, then induces and canonicalizes a schema. It reports more concise, less redundant schemas than open extraction or clustering baselines. — cited in the [LLM-empowered KG construction survey, arXiv 2510.20345](https://arxiv.org/pdf/2510.20345)
- Closed-schema extraction (LREC 2026 KG-LLM workshop): — [ACL Anthology](https://aclanthology.org/2026.kallm-1.21/)
  - Setup: a fixed ontology of 6 entity types and 96 relation types on DocRED, testing GPT-5.1, Gemini 3 Pro, Claude Opus 4.5 and Mistral 7B.
  - Finding: manual review shows automatic triple-F1 *underestimates* quality, because gold labels are incomplete.
- Hallucinated entities: RAKG checks extracted entities against the source text to remove hallucinations. — [arXiv 2504.09823](https://arxiv.org/pdf/2504.09823)
- Extractor quality matters: switching extraction from GPT-4o-mini to GPT-4o raised MultiHop-RAG accuracy from 71.17 to 75.08. — [Han et al.](https://arxiv.org/html/2502.11371v2)

### Inferences
- Graphify's generic labels (the 7/35 label-only result) fit the open-extraction failure profile. The documented fixes map directly onto Yggdras's frozen node format:
  - a fixed verb vocabulary for typed wikilinks (schema-guided);
  - alias-based entity resolution against the existing slug/alias roster (as in the "Graphify with roster" follow-up);
  - always returning source facts, not just edge labels.
- Generic edges from any LLM proposer should be typed post hoc against the vocabulary, or rejected.

### Gaps
- No head-to-head study of schema-guided vs open extraction *for downstream QA accuracy* was found; the evidence covers extraction quality only.
- No found study quantifies "generic relation" rates (e.g., share of edges labelled "related to").

## Q5. What scale or question type makes an LLM-built graph worth its build cost? And evaluation methodology

### Takeaway
LLM-built graphs pay off for corpus-wide sensemaking at about 1M+ tokens (the MS GraphRAG setting) and for many-hop questions over unlinked text. Below about 200k tokens, Anthropic's guidance is to skip retrieval and put the whole knowledge base in a cached prompt. On method: GraphRAG claims need reference-based or bias-controlled judging, paired comparisons, standard errors and multiple runs.

### Cited Findings
- Anthropic (Sep 2024): "If your knowledge base is smaller than 200,000 tokens (about 500 pages)", include it all in the prompt. Prompt caching cuts latency by more than 2x and cost by up to 90%. — [Anthropic, Contextual Retrieval](https://www.anthropic.com/news/contextual-retrieval)
- Same post, for larger knowledge bases: — [Anthropic](https://www.anthropic.com/news/contextual-retrieval)
  - Contextual embeddings cut top-20 retrieval failure by 35% (5.7% → 3.7%).
  - Adding contextual BM25 cut it by 49% (to 2.9%).
  - Adding reranking cut it by 67% (to 1.9%).
  - The one-time cost is about $1.02 per million document tokens.
- MS GraphRAG's demonstrated regime is 1–1.7M-token corpora and global questions. Indexing took 281 minutes with gpt-4-turbo for 1M tokens. — [arXiv 2404.16130](https://arxiv.org/html/2404.16130v2)
- LazyGraphRAG claims vector-RAG-level indexing cost (0.1% of GraphRAG) by deferring LLM work to query time. This is a vendor claim. — [Microsoft Research](https://www.microsoft.com/en-us/research/blog/lazygraphrag/)
- Graph construction cost vs RAG on MultiHop-RAG: about 41–57x (5,560–7,702 vs 135, units unstated). — [Han et al.](https://arxiv.org/html/2502.11371v2)
- Evaluation biases: — [Han et al.](https://arxiv.org/html/2502.11371v2); [Zeng et al.](https://arxiv.org/abs/2506.06331)
  - LLM-judge position bias reversed RAG-vs-GraphRAG preferences (Han et al.).
  - Self-vs-self win rates differed by more than 30% (Zeng et al.).
  - A 25-token length gap swung win rates by more than 50% (Zeng et al.).
  - Both papers recommend reference-based metrics or position-swapped, length-controlled judging.
- Statistics (Anthropic, Nov 2024): — [Anthropic](https://www.anthropic.com/research/statistical-approach-to-model-evals)
  - Report SEM and 95% CIs.
  - Cluster standard errors when questions share a source; clustered SEs were more than 3x the naive ones on popular evals.
  - Resample each question several times and average.
  - Use paired-difference tests when comparing systems on the same questions.
  - Do a power analysis for the number of questions needed.

### Inferences
- A few dozen to a few thousand short notes is likely about 20k–1M tokens. At the low end, a full-context cached prompt is a valid baseline that should be in the eval. At the high end, the current node-picker plus link-expansion pipeline sits in the regime where the literature shows vanilla or structured retrieval matching graph methods on factual questions.
- An LLM-built graph is worth considering only if Yggdras adds question types the current eval lacks:
  - global themes;
  - 3+-hop chains across notes that are *not* linked;
  - temporal or comparison aggregation.
  - Even then, a link-proposal role (curated into wikilinks) is cheaper than a parallel retrieval graph.
- On 35 questions, 35/35 vs 34/35 is within noise: the 95% CI at p≈0.97 is roughly ±6 points. Comparisons should therefore:
  - use paired tests on the same questions;
  - include several runs per question;
  - use a held-out question set written before the system is tuned;
  - report cost per correct answer with a CI.

### Gaps
- No published crossover point (in tokens or note count) where LLM graph build cost is recovered by accuracy gains.
- No small-corpus (<100k tokens) GraphRAG benchmark was found.
- The MS GraphRAG paper's dollar indexing cost was not found in the primary source. A widely repeated "$33,000" figure comes from an unverified Medium post.
