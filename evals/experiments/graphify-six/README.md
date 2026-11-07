# Six Graphify experiments (pre-registration)

Written 2026-10-26, before any run. Prompts, questions, matching rules and code are frozen from here on; anything changed after results would be logged below as a deviation. Local only. `demo-brain/` and `brain/` are not touched. Graphify is pinned at 0.9.95 (D32), provider Anthropic, query logging off (`GRAPHIFY_QUERY_LOG_DISABLE=1`). Answer and checker model: `claude-haiku-5-5`, thinking off, effort low. Graphify builds: `claude-sonnet-5-5`, as in link-recovery.

**Shared rules**
- At least 2 runs per arm unless stated. All arms of an experiment are scored on the same items (paired).
- Every run reports $ and seconds. Graded answers also report $ per correct.
- Hand grading: a key-term check runs first, then every flagged answer is read. Paraphrases of a key fact are credited, and each such call is recorded in the result file.
- A reply starting with "NOT IN BRAIN" is a decline.
- **Spend cap:** $5 in total. Before each experiment, its estimate is added to the running spend. If the total would exceed $5, that experiment is not run and the reason is reported.
- Costs use list prices:
  - Haiku 5.5: $0.10 / $0.50 per MTok, cache write 1.25×, cache read 0.1×.
  - Sonnet 5.5: $2 / $10 per MTok. Graphify's own estimate is reported beside it.

## Experiment 1: free link scan + verb checker

**Hypothesis.** Arm A's spurious name matches can be removed by fixing the matcher, and a Haiku checker can attach the right verb from the brain's vocabulary without losing recall.

**Setup**
- Corpus `link-recovery/brain-stripped/`, its 20 deleted pairs (`answer-key.json`), and its matching rule (`score_arms.py`).
- **Step 1a, logged change to Arm A (`arm_a_fixed.py`):**
  - Strip a possessive `'s` / `’s` before normalizing.
  - Block the place names "Cape Kennedy" and "Kennedy Space Center" (not nodes) before roster matching, so "Kennedy" cannot match `john-f-kennedy` inside them.
  - Nothing else changes.
  - A before and after: 2 runs each.
- **Step 1b, checker (`verb_check.py`):**
  - Fixed A's candidates, one per ordered (from, to) pair, go to Haiku in batches of 20.
  - Each item carries both notes' fact lines and the candidate's reason line.
  - The verb list is every distinct link reason in the original `demo-brain/` link lines.
  - Structured output per item: `{"id", "decision": "accept"|"reject", "verb": <from the list> | null, "quote": <a fact line, verbatim>}`.
  - The verb describes from → to. 2 runs.
- **Gold verbs:** the reasons of the original brain's link lines for that ordered pair.

**Metrics**
- Recovered of 20, counting pairs with at least one accepted direction.
- Precision of accepted new pairs (new = not linked in the original brain), judged plausible or wrong by hand under link-recovery's rule.
- Verb accuracy on accepted pairs that have a gold link in the proposed direction (exact verb match).
- Run-to-run flips in decisions, and $ and seconds per run.

**Pass line**
- Recall at least 11/20.
- Precision of new pairs at least 33/34 (≥ 0.97).
- Correct verb on at least 90% of accepted pairs with a gold verb.

## Experiment 2: harder held-out questions

**Questions.** 24 new questions in `demo-evals/held-out-v7-hard.yaml`, written before any run, with answer key, gold notes and key terms. The mix:
- 6 multi-hop (3 or more notes)
- 5 unlinked (facts in notes with no link between them)
- 5 temporal
- 4 comparison
- 4 corpus-wide themes

**Arms (3 runs each, same 24 items)**
- **A:** the current pipeline (variant C, `retrieve.py`): pick, gather, cited answer.
- **B:** the whole demo brain in one cached prompt. Every note's fact lines and link lines go in as `search_result` blocks, with the cache marker on the last block, followed by one cited answer call. No pick.
- **C:** A, plus one fallback.
  - When the first answer declines, one structured call picks up to 2 of the gathered nodes whose neighbours to fetch (`get_neighbours`).
  - Their unsent neighbours' fact lines are added, and a second cited answer call is made.
  - Capped at 2 answer turns.
- **D:** the hybrid.
  - `graphify query --budget 2000` on the links-free build in `graphify-vs-baseline/`.
  - Names are mapped to slugs, and our fact lines are sent as `search_result` blocks.
- **B on the old 35 questions:** 3 runs.

**Metrics**
- Correct out of 24 per run, mean with Wilson 95% CI over all question-runs.
- Paired difference vs A: per question, the mean over runs, with a standard error clustered by first gold note.
- $ per correct, tokens in (billed equivalent), and end-to-end seconds (median and slowest).

**Pass line (B and C vs A):** an arm "beats" A when its paired difference is above 0 with the clustered 95% interval excluding 0. Otherwise, no difference.

## Experiment 3: is the Graphify picker gap the filter bug?

**Hypothesis.** The hybrid's 10 query misses are caused by the inferred context filter (#2529) and by weak seeding, not by Graphify's graph.

**Setup.** The hybrid on the 35 questions, 2 runs per variant:
- **a.** Raw questions (a repeat of the last hybrid run).
- **b.** Before the query, remove every word in 0.9.95's `_CONTEXT_HINTS` from the question; the answer call keeps the original question.
- **c.** Seed the query instead of letting Graphify find seeds.
  - The seeds are our signpost picker's notes: `graphify query "notes" --seed <path>` for each picked note.
  - Then `graphify explain` on each seed label, for its neighbours.
  - All returned names are mapped to slugs, and our fact lines are sent.

The `Context: ... (heuristic)` header is logged for every query.

**Metrics**
- Score out of 35 per run.
- Seed recall@2: is any gold note among the query's first 2 start seeds (a, b), or among the picked notes (c)?
- Number of filter collapses (a heuristic filter header in the output).
- $ and seconds per run.

**Pass line.** If b recovers at least 3 of the hybrid's 10 query misses, the filter is a material cause. If c reaches at least 33/35, Graphify adds nothing over our own pick plus neighbours.

## Experiment 4: `graphify update` as the structural map

**Setup**
- `GRAPHIFY_BACKEND=none graphify update <copy>` on a fresh copy of the intact `demo-brain/` and on a copy of `brain-stripped/`, twice each, in a scratch folder.
- Its `references` edges between page nodes are mapped to slugs by `source_file`, and compared with our structural pass (`build_map`) on the same copy.

**Metrics**
- Agreement of 81 (intact) and of 61 (stripped) pairs.
- Extra pairs, missing pairs, and dangling links.
- Repeatability between the two runs, and time.

**Pass line.** At least 79/81 and 59/61, no extra pairs, and identical output across runs.

## Experiment 5: deep mode and a smaller token budget

**Setup.** `graphify extract brain-stripped-copy --backend claude --model claude-sonnet-5-5 --force`, with:
- `--mode deep`, 2 runs
- `--token-budget 15000`, 2 runs

Separate output folders. Stop if the experiment's spend passes $2.

**Metrics**
- Recovered of 20, scored by `score_arms.py`'s rule.
- Share of `conceptually_related_to` edges, and the count of nodes with a rationale.
- New pairs, plausible or wrong by hand.
- Noise between the two runs, and $ and seconds.

**Pass line.** Beats default Graphify (9 and 7 of 20) by at least 3 pairs in both runs, or cuts the generic share below 50%.

## Experiment 6: upstream fixes (check only)

**Setup.** Check whether PR #4576 (`--rationale`), #3636 (frontmatter description as body) or #3614 (markdown routing) is in any released version.
- **If none is:** don't run; report the status.
- **If one is:** install it in a separate venv, re-run the label-only arm with `--rationale` and with description frontmatter on a test copy, 2 runs.

## Experiment 7: the video's claims (pre-registered 2026-10-26, before any 7a/7b run)

Spend cap for experiment 7: $3. Sessions are `claude -p` (Claude Code 2.1.310, installed for this experiment) on `claude-haiku-5-5`, billed to the API key. Every session uses:
- `--setting-sources project --strict-mcp-config --no-session-persistence --output-format stream-json --verbose`
- a working directory in a scratch copy, so no user settings, memory or MCP servers load.

**Measured per session:** tokens (all models and subagents, from the result event's usage and `modelUsage`), tool calls (`tool_use` blocks, subagents included), seconds, and `total_cost_usd`.

**Abort rule.** After the first 4 sessions of 7a, cost is extrapolated to the whole experiment. If the projection passes $3, the experiment stops and reports what ran.

### 7a: code repo

**Corpus.** A copy of this repo at commit 5c15e0c (branch `retrieval-baseline-citations`), without `.git` and `.venv`.
- **Build:** `GRAPHIFY_BACKEND=none graphify update <copy>`. Record time, nodes, edges, communities and $.
- **Arm A copy:** also gets `graphify claude install` (project CLAUDE.md block plus `.claude/settings.json` hook), run in that copy only.

**Arms (2 runs each, a fresh session per question):**
- **A (Graphify):** tools `Read, Grep, Glob, Task, Bash(graphify:*)`. The prompt says a graph is at `graphify-out/graph.json` and to use `graphify query`, `explain` and `path` before reading files.
- **B (no Graphify):** tools `Read, Grep, Glob, Task`, and no graph in the copy.
- **Same in both:** the question, the reply format, and the model.

**Questions and answer key** (keys are checked first, then hand-graded):

| ID | Type | Question | Key (from reading the code) |
|---|---|---|---|
| c1 | flow | Trace how a question goes from `retrieve.py` to the final answer shown to the user. | `Retriever.__init__` builds the map with `build_map` and the cached signpost block → `ask()` → `pick()` (structured JSON, slug enum, one retry on empty) → `search_results()` (picked nodes' facts + Link lines + neighbours' facts via `edges_of`) → `answer()` (search_result blocks, citations, streamed) → `status_of` and `display_text` (strips `(src: ...)`). Keys: pick, search_results, answer, display_text |
| c2 | flow | How does the structural pass build the map from a brain folder? | `node_files` (all `*.md` except root `index.md`) → `parse_node` (`_split` frontmatter, YAML, required id/slug/name/type, `links_section` under `## Links`, `LINK_LINE` → reason + target) → `build_map` (duplicate-slug errors; targets resolved by exact slug, then `normalize`d slug or alias; ambiguous → error; unresolved → dangling; sorted output). Keys: parse_node, links_section, normalize, dangling |
| c3 | flow | How does the eval runner record a run? | `main` `record` → `load_questions` → verdicts from `--verdicts` (`load_verdicts`) or interactive `prompt_verdicts` → `build_result` (rejects missing or unknown ids, summary, `gate_met` when all pass) → `write_result` (dated YAML, `-run-N` suffix) → exit 0 only if the gate is met. Keys: load_questions, build_result, write_result, gate_met |
| c4 | where | Where is `normalize` defined, and where is it used? | Defined in `app/src/yggdras/data/graph/structural.py`. Used in `build_map` (slug and alias keys, resolving written targets) and in `app/tests/test_structural_map.py`. Keys: structural.py, build_map, test_structural_map |
| c5 | where | Where is `fact_lines` defined, and which files call it? | Defined in `evals/experiments/speed-test-one-query/retrieve.py`. Called in `retrieve.py` (`signposts`, `search_results`), `variant_a.py` and `test_retrieve.py`. Keys: retrieve.py, variant_a, test_retrieve |
| c6 | where | Where is a link line like `- replaced by [[jack-swigert]]` parsed? | The `LINK_LINE` regex in `structural.py`, applied in `parse_node` to lines from `links_section`. Keys: link_line, parse_node |
| c7 | breaks | What breaks if `LINKS_HEADING` is changed to `"## Related"`? | `links_section` reads only lines under that heading. Existing notes with `## Links` produce no edges, so the map has no edges and every link counts as missing. Link-dependent tests in `test_structural_map.py` fail, and `retrieve.py`'s gather finds no neighbours. Keys: links_section, edges, test |
| c8 | breaks | What breaks if `display_text` is deleted from `retrieve.py`? | `test_retrieve.py` imports it (ImportError, so the test module fails), and `Retriever.ask` calls it (NameError at runtime). `variant_a.py` does not import it. Keys: test_retrieve, ask |

**Metrics.** Correct /8 per run; total tokens including subagents; tool calls; seconds; $ per correct.

**Pass line for the claim.** The claim "Graphify cuts tokens with the same quality" holds if A's median total tokens are at most 60% of B's (the video showed about 80k vs 200k) and A's correct count is within 1 of B's in both runs.

**Hook check.**
- Make a local `git clone` of the repo into the scratch folder, on a new branch.
- Run `graphify update`, then `graphify hook install`.
- Make one small code commit: add a function to a scratch module.
- Confirm the post-commit rebuild ran and spent $0 (no backend set, so no model call), and that `graph.json` changed: the new function appears as a node.
- Run `graphify hook uninstall`, then delete the clone. The real repo and its hooks are never touched.

### 7b: the brain

**Questions.** 10 of the old 35, chosen now:
- direct: d01, d07
- two-hop: m01, m03, m04
- reworded: h01, h03
- page: p02
- negative: n02, n04

**Arms**
- **A:** Claude Code session in a copy of `demo-brain/`, with the existing full-brain Graphify build copied in as `graphify-out/graph.json` (from `evals/experiments/retrieval/build/`).
  - Tools: `Read, Grep, Glob, Task, Bash(graphify:*)`.
  - The prompt says to use `graphify query` and `explain`, then read the notes.
- **B:** the same copy without the graph, tools `Read, Grep, Glob, Task`.
- **Prompt (both arms):** answer from the notes only, with "NOT IN BRAIN" if absent, in an `ANSWER:` / `FILES:` reply.
- **Runs:** 2 per arm.
- **C:** variant C, reused from `speed-test-one-query/results/v6-C-{1,2,3}.json` for the same 10 IDs (no new run).

**Metrics.** Correct /10, total tokens, seconds, $ per correct.

**Questions this answers**
- Does Graphify save tokens against a roaming agent on notes? Same test as 7a: at most 60% of the tokens, and within 1 correct.
- How far are both from C?

## Deviations

1. **`grade_stats.py`: YAML keys read as integers.** Keys such as `1970` came in as integers and crashed the substring check, so they are now converted to strings. This is a type fix made before the grader produced any result; no grading rule changed.
2. **`exp7_run.py`, three fixes before any valid session:**
   - **What broke:** the first 4-session pilot failed. The npm `claude.cmd` shim sends arguments through `cmd.exe`, which cut the multi-line prompt at its first newline (arm A could not start at all).
   - **The fix:** the runner now calls the native `claude.exe` and passes the prompt on stdin.
   - **`--ids` filter:** its usage line already promised it, but it hadn't been implemented.
   - **The pilot:** re-run after the fix (4 sessions: c1 and c4 × A and B) and used only for the cost projection (projected $0.23 against the $3 cap). It is not scored; the scored 7a/7b runs start fresh.
