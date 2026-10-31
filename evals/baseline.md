# Baseline: the "before" score

Step 2, part 1 of the roadmap in `planning/librarian-plan.md`. The numbers are copied from existing results, and nothing was rerun or estimated. A cell the results don't hold says **missing**.

**Common to all cells**
- **Model:** Claude Haiku 5.5, thinking off.
- **Tests:**
  - *Original 35:* the 25 questions in `demo-evals/questions.yaml` plus the 10 in `demo-evals/held-out-v6.yaml`.
  - *Hard 24:* `demo-evals/held-out-v7-hard.yaml`, in the brain repo.
- **Score:** correct per run. All results were hand-graded after a key-term check.
- **$ per correct:** total spend across all runs divided by total correct, at list prices.
- **Tokens per question:** billed-equivalent input tokens, median per question, with cache reads counted at 0.1× and cache writes at 1.25×. The highest value is in brackets.
- **Median seconds:** end to end per question.

## Original 35

| Option | Score (per run) | $ per correct | Tokens per question, median (highest) | Median seconds | Warm vs cold cache |
|---|---|---|---|---|---|
| Current pipeline (variant C) | 35, 35, 35 [1] | $0.000624 [1] | 3,893 (8,330) [1] | 3.18 [1] | missing |
| Whole-brain cached prompt | 34, 35, 35 [1] | $0.000493 [1] | 2,794 (2,810) [1] | 2.79 [1] | missing |
| Pipeline + neighbour fallback | missing | missing | missing | missing | missing |
| Graphify picks notes | 23, 25 [2] | $0.001297 [2] | 9,179 (11,714) [2] | 4.44 [2] | not applicable (no cache) |

## Hard 24

| Option | Score (per run) | $ per correct | Tokens per question, median (highest) | Median seconds | Warm vs cold cache |
|---|---|---|---|---|---|
| Current pipeline (variant C) | 19, 19, 19 [3] | $0.000877 [3] | 3,912 (8,629) [3] | 3.82 [3] | missing |
| Whole-brain cached prompt | 23, 23, 23 [3] | $0.000589 [3] | 2,794 (2,818) [3] | 3.16 [3] | 72 of 72 calls warm; 27,189 tokens per question in total [4]. Cold: missing [5] |
| Pipeline + neighbour fallback | 19, 19, 19 [3] | $0.000978 [3] | 4,180 (10,443) [3] | 4.27 [3] | missing |
| Graphify picks notes | 14, 13, 14 [3] | $0.001337 [3] | 5,823 (11,255) [3] | 3.47 [3] | not applicable (no cache) |

## Sources

All paths are relative to `evals/experiments/graphify-six/`.

1. `exp2/stats-old35.json`
   - **Whole-brain prompt:** arm B, from the runs `exp2/B-old-{1,2,3}.json`.
   - **Current pipeline:** arm C, from the v6 runs `speed-test-one-query/results/v6-C-{1,2,3}.json` on branch `retrieval-baseline-citations` (PR #18).
   - **Grading:** the hand grades in `exp2/overrides.json` are applied.
   - **Also in `REPORT.md`,** Part B Q11, where the per-correct figures are rounded to $0.00049 and $0.00062.
2. `exp3/stats.json`, variant D
   - **Runs:** `exp3/D-{1,2}.json`, Experiment 3a: raw questions, Graphify's own query on the links-free build.
   - **Grading:** the hand grades in `exp3/overrides.json` are applied.
   - **Also in `REPORT.md`,** Part B Q14, as 23, 25 and $0.00130.
   - **An earlier run of the same option** (`graphify-vs-baseline/hybrid-{1,2,3}.json`) scored 25, 24, 25. Its own statistics are not in the listed sources, so it is not used here.
3. `exp2/stats.json`, arms A, B, C and D
   - **Runs:** `exp2/{A,B,C,D}-{1,2,3}.json`.
   - **Grading:** the hand grades in `exp2/overrides.json` are applied.
   - **Also in `REPORT.md`,** Part B Q8.
4. `REPORT.md`, Part B Q9.
5. **No cold-cache whole-brain call is in the results.** The one cache write happened in a smoke test whose output was deleted. `REPORT.md` Q9 gives "about $0.0034" for it, but that figure is an estimate, not a measurement, so it is not used here.

## What is missing, to rerun in step 2, part 2

- **The fallback on the original 35:** the option was never run on that test.
- **Warm vs cold for the pipeline, both tests:** the pick call's cache write happens on the first question of a run. The per-call results hold the raw cache counts, but no warm/cold figure was ever reported.
- **Warm vs cold for the whole-brain prompt on the original 35, and a measured cold cost on both tests.**
