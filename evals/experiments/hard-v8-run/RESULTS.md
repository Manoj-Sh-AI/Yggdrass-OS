# Hard set v8: results (2026-10-30)

Pre-registered in [README.md](README.md), with no deviations. Questions: `demo-evals/hard-v8.yaml` (24) and `demo-evals/held-out-v8.yaml` (10), in the brain repo.
- **Model:** Haiku 5.5, thinking off.
- **Runs:** 3 per arm per file, interleaved whole-1, pipeline-1, whole-2 and so on, one question at a time.
- **Grading:** key-term check, then hand review. Nine paraphrases were credited; they are recorded in `overrides.json`.
- **Total spend:** $0.134.

Columns as in `evals/baseline.md`. Tokens are billed-equivalent input per question, median (highest); seconds are the end-to-end median.

## Hard v8 (24)

| Option | Score (per run) | $ per correct | Tokens, median (highest) | Median s | Warm vs cold |
|---|---|---|---|---|---|
| Whole-brain cached prompt | 23, 24, 24 | $0.000617 | 2,793 (33,964, the cold call) | 3.32 | 71 warm: $0.000543, 3.32 s median. 1 cold (v01, run 1): $0.003559, 2.44 s |
| Current pipeline (variant C) | 21, 20, 21 | $0.000798 | 3,948 (7,818) | 4.22 | 71 warm: $0.000668, 4.21 s median. 1 cold (v01, run 1): $0.001012, 4.38 s |

## Held-out v8 (10)

| Option | Score (per run) | $ per correct | Tokens, median (highest) | Median s | Warm vs cold |
|---|---|---|---|---|---|
| Whole-brain cached prompt | 9, 9, 10 | $0.000575 | 2,794 (2,808) | 2.53 | 30 warm: $0.000519, 2.53 s median. 0 cold (prefix still warm from the hard runs) |
| Current pipeline (variant C) | 9, 9, 8 | $0.000935 | 5,945 (8,189) | 3.74 | 30 warm: $0.000799, 3.74 s median. 0 cold |

**Cold vs warm.** Only the first question of each arm's first run met a cold cache, because the runs were interleaved within the 5-minute TTL.
- **Whole-brain:** a cold question costs about 6.6× a warm one ($0.0036 vs $0.00054). It was not slower.
- **Pipeline:** its cached block is the small signpost list, so a cold question costs only about 1.5× a warm one.

## Partials (v24, y08)

| Option | v24 | y08 |
|---|---|---|
| Whole-brain cached prompt | correct 3/3 | correct 3/3 |
| Current pipeline (variant C) | correct 3/3 (run 1 after hand review) | correct 2, **partial 1** (run 3: Duke, Mattingly and Swigert given, Charles Berry missing) |

## Every miss, with the step that failed

| Question | Option (runs) | Step | What happened |
|---|---|---|---|
| v05 chain | whole (run 1) | answer | Opened "NOT IN BRAIN." and then gave the right answer |
| y06 reworded | whole (runs 1, 2) | answer, input gap | Declined "AS-204". The alias is in `apollo-1`'s frontmatter, but the whole-brain blocks carry fact and link lines only, no aliases |
| v21 whole picture | pipeline (3/3) | pick | Picked apollo-1 and apollo-8; apollo-11, apollo-13 and apollo-16 never sent |
| v22 whole picture | pipeline (3/3) | pick | Picked armstrong and aldrin; charlie-duke never sent |
| v23 whole picture | pipeline (3/3) | pick | Picked north-american-aviation and grumman; mit-instrumentation-lab never sent |
| v17 reworded | pipeline (run 2) | answer | Declined because "mailbox" isn't a word in the fact lines, though the right note was sent |
| y10 unlinked | pipeline (3/3) | answer (question flagged) | Answered "Apollo 13" instead of the Apollo 11 landing |
| y08 whole picture | pipeline (run 3) | answer | Partial, as above |

**Missed by every option: none.** No question was missed by both options; the two sets of misses don't overlap.

## Flags (not changed, because the questions are frozen)

1. **y10 has two valid answers.** Duke and Kranz both had a role in Apollo 13 too: Duke as backup lunar module pilot whose measles started the swap, and Kranz, whose team was on console when the tank failed. The pipeline's "Apollo 13" is supported by the notes; only the key's Apollo 11 answer was graded correct.
2. **The whole-brain prompt has no aliases.** Its blocks don't include frontmatter, so alias questions (y06 "AS-204"; v17 "mailbox", which it got right anyway) depend on luck. Fixing it is a new, separately named experiment, not a retune of this one.
3. **The pipeline loses whole-picture questions at the pick.** Picking 1–2 nodes can't cover questions whose answer is spread over 3–5 unlinked notes: all 9 of its whole-picture misses, across v21, v22 and v23.
