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

## Results

Not yet run.
