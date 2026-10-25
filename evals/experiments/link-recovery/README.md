# Experiment: link recovery with Graphify discovery

Phase 1b's core measurement: can Graphify's discovery pass find links that were written by hand and then deleted, clearly above its own run-to-run noise? If not, discovery is dropped and 1b ends with the structural map alone. That is an acceptable outcome.

## Pre-registration (written and committed before any discovery run)

**Corpus.** A copy of the Apollo demo brain (`yggdras-brain/demo-brain`, 42 nodes, 81 linked pairs) in `brain-stripped/`. The original is never touched and stays the ground truth.

**Deletion.** `sample.py` deletes 20 of the 81 pairs with a fixed seed (20261025), stratified so they don't all come from hubs. A hub has 7 or more neighbours.

| Stratum | In the brain | Deleted |
|---|---|---|
| leaf (an endpoint has 1 neighbour) | 2 | 2 (both; the leaves `grumman` and `john-f-kennedy` end up isolated) |
| hub–hub | 4 | 1 |
| hub–mid | 31 | 5 |
| mid–mid | 44 | 12 |

Every link line between a chosen pair is removed, in both directions: 36 lines. The stripped copy's structural map has 107 edges, 0 dangling and 0 errors. The answer key is in `answer-key.json`.

**Graphify settings.**
- Version `graphifyy==0.9.95`, installed whole (`[all]`) as a uv tool.
- `--backend claude` passed explicitly, which skips auto-detection (confirmed in `graphify/cli.py`).
- `GRAPHIFY_QUERY_LOG_DISABLE=1`. Logging is already opt-in in 0.9.95 (confirmed in `graphify/querylog.py`); this forces it off.
- Default extraction mode, not `--mode deep`. The model is pinned explicitly with `--model claude-sonnet-5-5`, because Graphify's built-in Claude default (`claude-sonnet-4-6`) is an older generation.

**Two runs on identical input.** Each run writes to its own output folder with `--force`, so the second run does not replay the first run's content-hash cache. The difference between them is the noise floor.

**Matching rule (fixed now).**
1. A Graphify node maps to a brain node when its label, normalized by the D02 rule, equals the normalized slug, name or any alias of exactly one brain node. Otherwise it is unmapped, which means out of scope, not junk.
2. A **proposal** is a Graphify edge whose two endpoints map to two different brain nodes and that is not tagged `_origin: ast`. AST edges are Graphify re-reading the links still written in the copy, not discovery.
3. Proposals are compared as unordered node pairs. A proposal on a pair still linked in the stripped copy counts as **re-found**, not discovery.
4. **Recovered:** the proposal's pair is one of the 20 deleted pairs.
5. Every other proposal is judged by hand into **plausible** (never in the brain, but might be real) or **wrong** (contradicts the corpus, or links unrelated nodes). Plausible proposals are listed in full for Manoj to judge; wrong ones get a count and examples.
6. **Noise:** compare run 1 and run 2 proposal pairs. Report the counts, the overlap (shared pairs over all pairs), and which deleted pairs were recovered in one run but not the other.
7. Also recorded: whether each proposal carries a reason or only a bare connection, the cost of a run, and how long it took.

**No threshold is set here.** Manoj rules on whether recovery clearly beats the noise once the numbers are in, the same discipline as the phase 1a gate.

## Results (2026-10-25)

Two runs, identical input, `graphifyy 0.9.95`, `--backend claude --model claude-sonnet-5-5 --force`, separate output folders. Raw outputs: `run-1-graph.json`, `run-2-graph.json`, plus logs and timings. Scores: `scores.json`, written by `score.py` and reproduced identically on a re-run.

| | Run 1 | Run 2 |
|---|---|---|
| Time | 182 s | 265 s |
| Tokens (in / out) | 23,953 / 15,279 | 25,402 / 18,335 |
| Cost (Graphify's estimate) | ~$0.30 | ~$0.35 |
| Raw Graphify output | 43 nodes, 71 edges | 72 nodes, 91 edges |
| Edges by origin | 71 model, 0 AST | 91 model, 0 AST |
| Node pairs proposed | 68 | 69 |
| Re-found (pair still written in the copy, of 61) | 59 | 61 |
| **Recovered (of 20 deleted)** | **9** | **7** |
| New pairs, never in the brain | 0 | 1 |

**Noise between the two runs**
- **Proposed pairs:** 65 in both runs, 3 only in run 1, 4 only in run 2, so overlap is 65/72 = **0.90**. The raw output varied far more (43 vs 72 nodes, 71 vs 91 edges), but most of that variation collapses once nodes are mapped onto the brain.
- **Recovered pairs:** 6 in both runs. **4 flip** between runs (recovered once only): `apollo-11`–`neil-armstrong`, `apollo-13`–`rubella-crew-swap`, `apollo-program`–`john-f-kennedy` and `neil-armstrong`–`tranquility-base`. **10 of the 20 were never recovered.**

**Recovered, by stratum.** Run 1: both leaves, 2 of 5 hub–mid, 5 of 12 mid, 0 of 1 hub–hub. Run 2: 1 leaf, 0 hub–mid, 6 mid, 0 hub–hub.

**The three buckets**
- **Recovered:** 9 in run 1, 7 in run 2, 10 across both. Every recovered pair is one whose connection is also stated in a fact line. For example, "Built the service module oxygen tanks under North American Aviation" recovers beech–NAA, and "Led the team that developed the Saturn V" recovers von Braun–Saturn V.
- **Plausible:** 1, in run 2 only. `john-young` → `apollo-13-measles-article` (*cites*). It's real: John Young's facts cite that article as their source, so the model turned a source label into a link. Listed for Manoj to judge.
- **Wrong:** 0. No proposal connected unrelated nodes or contradicted the corpus.

**Reasons.** No proposal carries a reason. Each edge has only a generic relation label and a confidence tag. Across both runs' raw output (162 edges), the labels were `references` (145), `conceptually_related_to` (15) and `cites` (2). There is no per-link explanation of the kind the plan's review step relies on.

**Other observations**
- **No deterministic pass ran.** All 43 files were classed as documents and sent to the model (confirms open question 1). The model emitted mostly `references` edges, essentially re-reading the written `[[links]]`.
- **`index.md` was included in the input**, since Graphify doesn't know it's an index. It became a node and stayed unmapped.
- **The strict label rule left one source unmapped** in run 1: "NASA history: Apollo 13 and German Measles" doesn't exactly match the node's name. That was pre-registered, so it was not adjusted.
- **Misses include connections stated plainly in the text.** `apollo-13`–`ken-mattingly` was missed although apollo-13's facts say the pilot "was Ken Mattingly". Also missed: `apollo-11`–`lunar-module` (hub–hub), and `buzz-aldrin`–`neil-armstrong`.

**No ruling is made here.** Whether recovery (9 and 7 of 20; 6 consistent, 4 flipping) clearly beats the run-to-run noise is Manoj's call under the kill criterion.

## Follow-up: three arms (pre-registered 2026-10-25, before any arm ran)

Same copy (`brain-stripped/`), same answer key, same 20 deleted pairs, same matching rule and buckets as above. Each arm runs twice on identical input; the difference is its noise floor.

**Graphify issues, checked against the pinned 0.9.95 source and changelog.**
- **#65 (no global linking pass across batches):** closed, but the fix (v0.3.17) only added skill-file guidance to group files by folder. 0.9.95 still has no cross-batch pass: `_pack_chunks_by_tokens` groups by directory and packs to a token budget, and an over-long answer splits the chunk in halves (`_extract_with_adaptive_retry`). **Still applies.**
- **#3947:** open. **Still applies.**
- **#4547:** open, reported on 0.9.92, fix only on a branch. **Still applies.**
- **#3094:** closed 2026-10-04. The installed `dedup.py` has the `source_file` guards (line 239, lines 298–327). **Fixed at 0.9.95.**

**What batching did in the original runs.** Run 1 was one batch of all 43 files. Run 2's answer was truncated and split into halves of 21 and 22; the halves were reconstructed by calling Graphify's own `detect` and `_pack_chunks_by_tokens`, read-only. 11 of the 20 deleted pairs straddled run 2's halves. Also, `index.md` lists every node's slug and aliases, so whenever it shared a batch with a note, that batch already had a roster in it. Run 1 had that throughout.

**Arm A, free baseline (control).** `arm_a.py`, no model. Roster = every node's slug, name and aliases from the stripped copy's structural map. For each fact line, the fact text only (the trailing `(src: …)` group is provenance, not a link claim), normalized by the D02 rule. Roster names match at hyphen-token boundaries, longest first, without overlap. A match to another node gives a candidate link, with the fact line as its reason. Cost zero.

**Arm B, Graphify with a roster in every batch.** No prompt or instruction option exists in 0.9.95: the system prompt is a fixed constant and `--prompt-file` only exists on the cache-check subcommand. Reachable from outside without editing Graphify:
- a roster file (`_roster.md`: every node's name, slug and aliases) added to a second copy of the stripped corpus;
- `GRAPHIFY_MAX_OUTPUT_TOKENS=21000`, Graphify's public output-cap variable (default 16,384), so that the answer is not truncated and the batch is not split, and every note shares the batch with the roster. 21,000 is the most the SDK allows without streaming.

Everything else is as in the original runs. If a run still splits, that is recorded, not retried.

**Arm C, cross-batch pass.** `arm_c.py`, one model call per run (`claude-sonnet-5-5`, Anthropic API, same key), over run 2, the only run with more than one batch.
- **Input:** the roster tagged with run 2's batch for each note, run 2's proposal pairs (so it doesn't repeat them), and each note's fact lines. Fact lines are included because Graphify's output carries only labels and bare edges, and a pass given only those would be guessing.
- **Asked for:** links only between notes in different batches, not already proposed, each with a reason that quotes the supporting fact.
- **Kept:** only output pairs whose slugs both exist and that do cross batches; anything dropped is counted.
- **Scored:** C's own additions alone, and run 2 plus C's additions combined.

Run 1 had a single batch, so C has nothing to add there; that is reported as such.

**Judging new pairs.** A new pair is plausible if its reason sentence states a relation between the two nodes, and wrong if the name match is spurious or the sentence doesn't relate them.

**Reported per arm:** recovered of 20, the noise between its two runs, the three buckets, whether each proposal carries a usable reason, cost and time. No threshold is set here; Manoj rules.
