# Scoping: Phase 1b — Graphiti layer

Answer in your own words. Go deep where a wrong guess is expensive (stored data, several reasonable designs, edge cases). Stay shallow on anything cheap to change later.

**This file is public.** Keep answers generic; anything personal goes in `yggdras-brain/private/`.

Source: `planning/locked-plan-v1.md`, "Phase 1b" and register rows D5–D9, D27, D28, D31.

## Already decided by the plan

| Choice | Decision | Where |
|---|---|---|
| Graph database | FalkorDB in Docker, locally (Kuzu and Neo4j are the alternatives) | D5 |
| Direction | One-way ingest from files to graph; the graph can always be dropped and rebuilt | D6 |
| Extraction | Graphiti with a paid API model | D7 |
| Trigger | Nightly, with catch-up on wake | D8 |
| Language | Python | D9 |
| Model access | Behind an interface from day one | D27 |
| Node format | Frozen 2026-10-24 | D31 |

## Decisions (Manoj, 2026-10-24)

| # | Decision | Options | Your choice |
|---|---|---|---|
| 1 | Corpus for 1b | Apollo demo brain moved to `demo-brain/` first / leave it in `brain/` / the fixture only | **Apollo demo brain, moved to `demo-brain/` first** |
| 2 | Graph database | FalkorDB in Docker (D5) / Kuzu embedded / Neo4j | **FalkorDB in Docker, as D5** |
| 3 | Extraction model | Claude via the Anthropic API / OpenAI / other | **Claude via the Anthropic API** |
| 4 | Embeddings | OpenAI or Voyage (second key) / local model | **Local embeddings (sentence-transformers), no second paid key** |
| 5 | Episode unit | One node file per episode, timed by `updated` / one fact line per episode | **One node per episode, but verify Graphiti reads fact-level dates from the body, not just `updated`** |
| 6 | Code location (D28 open) | `app/src/yggdras/data/graph/` / settle D28 now | **`app/src/yggdras/data/graph/`; D28 waits for phase 2** |
| 7 | "Reproduces the graph" | Same entities, and edges at or above a threshold, across two rebuilds / exact match | **Same entities plus edge agreement above a threshold, but the threshold is measured, not picked** |
| 8 | "Often enough to trust" | e.g. at least 80% of hand links recovered, at most 20% invented edges | **No number yet: define the matching rule, run it, then set the gate from what is seen** |
| 9 | Trigger in 1b | Manual rebuild only, nightly (D8) deferred / nightly now | **Manual rebuild only; nightly deferred** |
| 10 | Cost cap | Hard limit per rebuild (e.g. $5) / none | **Hard cap of $5 per rebuild; abort on the estimate** |

**Gate sequencing for 7 and 8 (Manoj).** No threshold exists until these three steps are done, in order:

1. **Define a match.** Hand links are a slug plus free-form reason; Graphiti emits typed relations between entities it extracted, which may not map to nodes at all. Decide whether same pair with any relation counts, and whether an extracted entity that is not a node counts as invented or out of scope.
2. **Measure the noise floor.** Rebuild twice on the same corpus and measure how far extraction differs from itself. No gate can sit below it.
3. **Set the gate.** Run the comparison against links, look at the actual numbers, then set the thresholds.

A threshold written before step 3 either passes trivially or gets quietly adjusted afterwards. This is the same discipline as never rewriting eval questions after seeing failures.

## Research findings for the spec (2026-10-24, from Graphiti docs and mirrors; to confirm against the installed version)

1. **Dates (decision 5).** Graphiti's LLM fills an edge's `valid_at` and `invalid_at` from dates written in the episode text, and falls back to the episode's `reference_time`. So body dates *are* read, but every fact line also carries its recording date in `(src: …, 2026-10-24)`. That date may be mistaken for when the fact became true. The episode text probably needs the source dates stripped or relabelled. The files stay unchanged, since the graph is derived.
2. **Superseded facts.** Invalidation happens when a *later* episode contradicts an earlier edge. With one node per episode, a fact and its history `(was X, changed <date>)` arrive in the *same* episode. Whether Graphiti records the old value as an invalidated edge is unknown, so a small spike should test it.
3. **Bulk ingest skips invalidation.** `add_episode_bulk` does no edge invalidation, so the rebuild must add episodes one at a time.
4. **Hidden OpenAI dependency.** With Claude, Graphiti still defaults to OpenAI for embeddings *and reranking*. Decision 4 covers embeddings with `SentenceTransformerEmbedder`, but the reranker (cross-encoder) also needs a local replacement, or decision 4 is only half met.
5. **Wiring.** `AnthropicClient` as `llm_client`, `SentenceTransformerEmbedder` as `embedder`, `FalkorDriver` as `graph_driver`. No documented example combines all three, so exact names need confirming once `graphiti-core` is installed.

## Spike results (2026-10-24, graphiti-core 0.31.2, FalkorDB, claude-haiku-5-5; code deleted afterwards)

Three demo-brain nodes (`apollo-13`, the Section 5.3 chunk, `michael-collins`) were ingested one at a time into four graphs: recording dates intact or stripped, each with the episode `reference_time` set to 2026-10-24 and then to 2000-01-01. The second pair was needed because the first was confounded: there, the reference time equalled the recording date.

**Q1: Is the recording date mistaken for when a fact became true? Yes.** With `reference_time` at 2000-01-01, the intact graph dated 8 undated facts (such as "Collins flew Apollo 11") `2026-10-24`, the recording date. The stripped graph dated them 2000-01-01, the fallback. Facts with dates in their text (the 1970 launch, the swap, the abort) got their real dates either way. **Consequence:** the ingest text must strip the `(src: …, <date>)` dates. Then undated facts fall back to `reference_time`, which carries no real meaning, so the spec must choose what an undated fact's `valid_at` should be.

**Q2: Does a fact and its history in one episode keep the old value as a superseded edge? Only sometimes, and not through Graphiti's invalidation.** `expired_at` was never set in any run, so Graphiti's contradiction-invalidation did not fire within a single episode. Instead the model sometimes extracts the old value as its own edge with `invalid_at`. For example, `Apollo 13 → PLANNED_LANDING_AT → Fra Mauro` (1970-04-11 to 1970-04-13) appeared in 3 of 4 runs, but `Apollo 13 → WAS_COMMAND_MODULE_PILOT → Ken Mattingly` appeared in only 1. Otherwise the old value is folded into the new fact's text. The swap also produced a zero-length `REPLACED` edge (valid and invalid both 1970-04-10). **Consequence:** superseded history in the graph is unreliable as built. The spec must either emit the old value as a separate line or episode, or accept that history lives in the files and the graph holds current values plus whatever the model extracts.

**Q3: Do page citations survive? No.** No per-fact page label (`p.5-4`, `p.5-6`) reached any edge in any run. The range "pages 5-4 to 5-6" appeared once, in one of four runs. **Consequence:** page-precise retrieval stays file-based, through chunks. The graph can't serve it.

**Side findings for the spec**
- **The Anthropic SDK must be pinned.** Graphiti declares `anthropic>=0.49` with no upper bound. SDK 2.3.0 rejects the `temperature` argument Graphiti sends; `anthropic<1.0` (0.125.0) works.
- **Graphiti imports OpenAI even when it's unused.** It loads its OpenAI re-ranker module, so `openai` is a hard dependency. D27 needs three slots: model, embedder and re-ranker.
- **There's no built-in local embedder** in 0.31.2, so a small custom `EmbedderClient` is needed. The only built-in local re-ranker (`bge-reranker-v2-m3`) is a multi-gigabyte download.
- **FalkorDB's default query timeout is 1 second.** One run failed intermittently on it, so the spec must raise it.
- **The default model is out of date** (`claude-haiku-4-5-latest`), so the spec must name one.
- **Noise is visible already.** Identical input gave 17–20 edges across runs, plus extraction errors: a self-loop (`Apollo 13 → LAUNCHED_ON → Apollo 13`), and the chunk merged into an entity named after the whole report. This feeds decision 7's noise-floor measurement.

## Rulings for the spec from the spike (Manoj, 2026-10-24)

## 1. What kind of software is this?

The first real system code: a one-way ingest pipeline that reads the frozen
markdown node format, transforms it at the boundary, and sends episodes to
Graphiti, plus a comparison harness that measures what came out against the
hand-written links.

Everything it produces is disposable. The graph is a derived index (D6) that can
be dropped and rebuilt from the files at any moment, so nothing in this phase is
a store of record and no failure here can lose data.

## 2. Which tasks does it take on?

**In (breadth):**

- Parse the frozen node format: frontmatter, fact lines, tags, history, page
  labels, links.
- Transform node text for ingest, stripping recording dates (ruling 1).
- Ingest episodes one at a time, since bulk ingest skips invalidation.
- Provide a rebuild command that drops the graph and re-ingests from files.
- Measure the noise floor by rebuilding twice on identical input.
- Compare extracted edges against hand-written links and write a dated report.
- Check what the graph does with superseded facts.
- Enforce the cost cap, abort before exceeding it.
- Model, embedder and re-ranker behind one interface with three slots (D27).

**Out (for now):**

- The connector and its tools (phase 2), agents (3–4).
- Any write from the graph back to files — forbidden by D6.
- Nightly scheduling (decision 9, deferred).
- Page-precise retrieval from the graph: the spike showed it does not survive,
  so this stays file-based through chunks.
- Using the graph for retrieval at all. This phase builds and measures it; it
  does not put it in the answering path.

## 3. What is the expected result? (acceptance criteria)

**What the spike changed.** Two of the three things the graph was expected to add
did not survive contact: page citations never reached an edge, and supersession
fired inconsistently through model extraction rather than through Graphiti's
invalidation. So the exit test is narrowed to what the graph can actually do —
discover entities and relations — and the other two stay file-based.

**No threshold exists until these run in order:**

1. **Define a match.** Written down before any number: whether same-pair-any-
   relation counts and whether relation direction matters. Already fixed: an
   extracted entity whose name appears in the episode text (case-insensitive,
   after D02 normalization) but matches no node is out of scope; one whose name
   does not appear is invented. Merges and splits use the same string rule.
2. **Measure the noise floor.** Three rebuilds on identical input, measuring how
   far extraction differs from itself. The spike already saw 17–20 edges on
   identical input, so this floor is not negligible.
3. **Set the gate.** Run the comparison, look at the numbers, then choose
   thresholds. A threshold chosen earlier either passes trivially or gets tuned
   afterwards.

Phase 1b is done when all of the following hold:

- The matching rule is written down and was not changed after seeing results.
- The noise floor is measured over three rebuilds and recorded.
- Link recovery and invented-edge rates are measured and sit at thresholds set
  after the fact, both clear of the noise floor.
- A rebuild from files reproduces the same entity set and edge agreement above
  the measured floor.
- A rebuild aborts cleanly when the cost estimate exceeds the cap, leaving no
  partial graph.
- No recording date appears as a `valid_at` anywhere in the graph: no edge carries a `valid_at` equal to any node's `created` or `updated` date. Undated facts carry the sentinel `1900-01-01`, meaning unknown.
- Model, embedder and re-ranker all run through the interface, and no call
  reaches a provider that was not configured.

**Kill criterion.** If link recovery cannot be distinguished from the noise
floor, the honest conclusion is that extraction adds nothing over the links
already written by hand, and the graph layer is dropped rather than tuned until
it looks useful. That outcome is a valid result of this phase, not a failure of
it.

**Value case (Manoj, 2026-10-24).** Phase 1b's value case is **link discovery**. Temporal handling is measured and reported, but gets no kill criterion: the spike showed it already fails as the plan assumed, so a second gate on it would be theatre. With temporal and page precision both out, the kill criterion on link recovery carries the whole case for D5–D8. If it fires, the graph layer is dropped through register amendments to D5–D8 and to phase 2's plan, which relied on Graphiti's MCP server.

**Settled for the spec:** three rebuilds for the noise floor; the re-ranker slot is a do-nothing stub in 1b, since the graph is outside the answering path.

## 4. Which processes run inside it?

1. Parse a node into structured form.
2. Transform it into episode text for ingest.
3. Ingest one episode.
4. Rebuild: drop and re-ingest everything.
5. Measure the noise floor.
6. Compare extracted edges against hand links.
7. Check temporal handling.
8. Estimate and enforce cost.

## 5. How is each carried out, step by step?

**Parse.** Read the file, validate against the frozen format, extract
frontmatter, fact lines with tag and source, history clauses, and links. Parsing
is pure code with no model call, so it is unit-tested in CI without an API key.

**Transform.** Strip the recording date from every `(src: …, <date>)` while
keeping the source label. Dates written inside the fact itself are left alone.
Every episode's `reference_time` is the sentinel `1900-01-01`, meaning "unknown",
so an undated fact can never be mistaken for one with a real date. Dropping
undated facts is ruled out (most facts carry no intrinsic date), and an empty
`valid_at` is not assumed, since the spike didn't test it.

**Ingest.** One episode per node, sent individually. Record the episode's input
text alongside the run so a surprising edge can be traced to what was sent.

**Rebuild.** Estimate cost first and abort if over cap. Drop the graph, re-ingest
every node, write a dated run record with counts and timings.

**Noise floor.** Three rebuilds on identical input. Report edge-count spread and
the share of edges appearing in all three, in two, and in one.

**Compare.** Apply the matching rule from Q3 step 1. Report recovered links,
missed links, and extracted edges matching no link, with examples of each.

**Temporal check.** For the known superseded facts, record what the graph holds:
both values, only the new one, or a malformed edge. Report, do not fix.

**Cost.** Count episodes and estimate tokens before a run. Abort over cap. Record
actual spend per run.

## 6. When do exceptions apply, and what happens then?

| Case | Rule |
|---|---|
| Model invents an edge | Counted and reported, never silently dropped. The invented rate is part of the gate. |
| A hand link is missed | Counted. Since links are in the files, a miss costs nothing operationally — it only lowers the trust score. |
| Two entities merged, or one split | Reported as a distinct failure kind, not folded into the invented count. Merges are worse than inventions because they are invisible at query time. Detection, by the gap-3 string rule: one extracted entity matching two different nodes is a merge; two entities both matching one node is a split. |
| Superseded fact | Reported, not fixed. The spike showed this is unreliable; the files remain the source of truth for history. |
| Node with only `[derived]` facts | Ingested normally, but flagged in the report. Derived facts feeding extraction risks compounding inference. |
| Database down | Fail loudly and stop. Never partially ingest and report success. |
| API error or rate limit mid-rebuild | Abort the rebuild and leave the graph dropped rather than half-built. A partial graph that looks complete is the dangerous state. |
| Cost cap would be exceeded | Abort before the first call, not during. Report the estimate and what it would have cost. |
| Extracted entity matching no node | String check, fixed before any numbers: if its name appears in the episode text (case-insensitive, after D02 normalization) it is out of scope; if not, it is invented. Out-of-scope entities are reported separately as a third category, since they may be worth creating as nodes. Imprecise at the edges by design: a consistently imperfect rule beats one that can be tuned. |
| Node with contradictory facts | Ingested as written and flagged. The contradiction is a problem in the brain, not in the pipeline, and fixing it is a file edit. |
Ready to build? Only if 3 and 6 are answered, and every open decision has a choice.
