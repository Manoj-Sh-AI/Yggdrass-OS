# lia-v1 results

Run 2026-11-02 under `prereg.md` (committed before the first run; deviations after start are listed there). Aggregate numbers only. Real-brain answers, traces and grades stay in `local-data/`.

## Verdict: FAIL

Bars 2 (traps) and 3 (citations) failed; bars 1 (accuracy), 4 (latency) and 5 (cost) passed.

| Bar | Result | Pass? |
|---|---|---|
| 1. Accuracy, Lia ≥ variant C on the mean of 3 runs | Life: Lia 15.0 vs C 13.67 (of 20). Apollo hard-v8: 22.0 vs 19.67 (of 24). Held-out-v8: 8.0 vs 8.0 (of 10) | **Pass** |
| 2. Traps (life): Q4, Q6, Q9 correct_abstain and Q10, Q11 correct, all 3 runs | Q4, Q6, Q9, Q10: 3 of 3 each. **Q11: partly correct in all 3 runs** | **Fail** |
| 3. Citations: 100% verified or marked `[unverified]`; 0 invented quotes | Fresh re-check: 473 shown citations, 455 verified, 0 marked, **18 fail the word-for-word re-check without a mark** | **Fail** |
| 4. Latency p50 ≤ 8 s, no-search questions | 5.6 s over 130 questions | **Pass** |
| 5. Cost ≤ 2× the PR #28 estimate (Haiku: ≤ $0.004/q) | $0.0011–$0.0016 per question | **Pass** |

## The three most likely causes, with trace evidence

1. **The citation check skips abstain answers, and Lia quotes Apollo fact lines without their `[stated]` tag.**
   - **Where it fails:** all 18 failing citations are in answers that begin "Not in your brain." `lia.py` sets `cites = []` for an abstain, so neither the check nor the retry runs on them.
   - **What the quotes are:** the quoted text is real. For example, apollo-held y04, run 2, quotes "Launched 1969-07-16 from Kennedy Space Center Launch Complex 39A (src: …)", while the note's line is "- [stated] Launched 1969-07-16 …". The quotes are not word for word, though, so they count as invented under the bar's definition.
   - **Other cases:** traces `final__apollo-hard__…__r1–3.jsonl` (v13, v14, v15, v16).
   - **Two life citations** fail differently: a fact line with its own double quotes inside breaks the citation pattern.
2. **Q11: Lia answers only the literal part and hedges on "last meeting".**
   - **What she did:** in all 3 runs she opened the one right note and gave the supervisor's advice, but said the note doesn't tie it to a meeting. She left out the second keyed fact, which is in the same note.
   - **Why:** the strictness skill ("a match only if the fact lines state what was asked") plus wording the notes don't use ("last meeting").
3. **Lia reads "goals" as a note type.**
   - **Q17** ("which goals made no progress"): she opened only notes of type `goal` and abstained in all 3 runs. The two "no progress" facts sit in a project note and a topic note.
   - **Q8:** she abstained twice, after missing the one note that holds the answer.

   Both are routing misses, not reading misses. Variant C got partial credit on Q17 by gathering neighbours. Not a bar, but it is most of Lia's life-set loss.

## Model choice

- **Step 1** (default config, 1 run each on Apollo hard-v8): Haiku 5.5 22, Sonnet 5.5 23, Opus 5.5 23. Re-graded under the consistent review rules: 22, 24, 23. The pre-registered tie rule picked Haiku for the experiments.
- **Deviation 1** (final config on Apollo hard-v8 only, 3 runs each):

| Model | Runs | Mean | Range | $ / question |
|---|---|---|---|---|
| Haiku 5.5 | 22, 23, 21 | 22.0 | 2 | 0.0011 |
| Sonnet 5.5 | 23, 22, 23 | 22.67 | 1 | 0.0148 |

- **The decision:** the difference of 0.67 is within the larger spread (2), so it's a tie, and the cheaper model wins: **Haiku 5.5**. Life and held-out decided nothing.

## Step 2: experiments (Apollo hard-v8, Haiku 5.5, 3 runs each)

Run-to-run noise is the default's range of 1, around a mean of 22.33.

| Arm | Runs | Mean | Partly | Citations verified | Routing recall | $ / q | p50 / p90 s |
|---|---|---|---|---|---|---|---|
| default | 22, 23, 22 | 22.33 | 2, 1, 2 | 192/197 | 0.97 | 0.0013 | 5.5 / 8.7 |
| E1 JSON | 22, 22, 22 | 22.0 | 2, 2, 2 | 184/193 | 0.99 | 0.0013 | 5.3 / 8.8 |
| E1 prose | 22, 22, 22 | 22.0 | 2, 2, 2 | 194/196 | 0.98 | 0.0013 | 5.4 / 8.6 |
| E2 shelf map only | 23, 23, 22 | 22.67 | 1, 1, 2 | 187/190 | 0.98 | 0.0012 | 5.4 / 10.3 |
| E3 L0 on | 23, 22, 23 | 22.67 | 1, 2, 1 | 181/186 | 0.98 | 0.0012 | 5.2 / 9.7 |
| E4 outgoing only | 22, 22, 23 | 22.33 | 2, 2, 1 | 178/186 | 0.98 | 0.0012 | 5.3 / 8.8 |
| E5 ≤ 10 words | 22, 22, 22 | 22.0 | 2, 2, 2 | 196/201 | 0.99 | 0.0013 | 5.4 / 9.6 |
| E5 ≤ 15 words | 22, 22, 22 | 22.0 | 2, 2, 2 | 188/192 | 0.98 | 0.0013 | 5.8 / 8.8 |
| E5 ≤ 25 words | 22, 22, 23 | 22.33 | 2, 2, 1 | 173/177 | 0.98 | 0.0013 | 5.5 / 9.1 |
| E6 cascade (Haiku routes, Sonnet answers) | 23, 23, 23 | 23.0 | 1, 1, 1 | 203/207 | 0.98 | 0.0159 | 8.8 / 12.8 |
| E8 neighbours on | 22, 23, 22 | 22.33 | 2, 1, 2 | 186/189 | 0.97 | 0.0015 | 5.3 / 8.8 |

**Decisions (keep the simpler arm unless the other wins by more than 1):**
- E1: pipe rows.
- **E2: shelf map only.** It's the simpler arm, and the relationship map did not beat it.
- E3: L0 off.
- E4: outgoing only (moot once E2 drops the relationship map).
- E5: ≤ 25 words.
- E6: one model; the cascade's +0.67 was at 12× the cost.
- E8: off.

**Final config** (`final-config.json`): the shelf map without the relationship map, descriptions cut at 25 words, everything else default.

**On "within noise":** with one noise point of 1 and 24 questions, Step 2 can't separate arms that differ by less than about 1 question. None did. E2's choice rests on the simplicity rule, not on a measured gain.

## E7: routing recall at scale (synthetic library brains, Haiku 5.5, route only)

| Notes | Maps, estimated tokens | Recall per run |
|---|---|---|
| 100 | ~5,100 | 1.00, 1.00, 0.98 |
| 300 | ~13,900 | 0.98, 1.00, 0.95 |
| 1,000 | ~42,200 | 0.68, 0.63, 0.65 |

Routing holds up to about 300 notes and falls sharply by 1,000. That fits the 25k-token split trigger in `maps-design.md` §7.

## Gate detail (Haiku 5.5, 3 runs each)

| Set | Lia runs | Lia mean | Variant C runs | C mean | Lia recall | C recall | Lia $ / q | C $ / q | Lia p50 / p90 s |
|---|---|---|---|---|---|---|---|---|---|
| Life hard-v1 (20) | 16, 15, 14 | 15.0 | 14, 14, 13 | 13.67 | 0.87 | 0.75 | 0.0016 | 0.0011 | 5.6 / 10.1 |
| Apollo hard-v8 (24) | 22, 23, 21 | 22.0 | 20, 19, 20 | 19.67 | 0.97 | 0.93 | 0.0011 | 0.0008 | 5.3 / 9.9 |
| Held-out-v8 (10) | 8, 8, 8 | 8.0 | 8, 8, 8 | 8.0 | 0.99 | 0.99 | 0.0012 | 0.0008 | 5.2 / 10.0 |

Lia's Apollo hard-v8 runs are the model-choice runs: same config and model, reused, so the gate ran once.

## Grading

- **Volume:** 1,236 graded answers.
- **The two graders** (Haiku judge and key terms) disagreed on 104. Claude hand-reviewed 550 answers in all: every disagreement, the pre-registered 20% sample, and every row of the questions where a written element rule was needed, so all arms were graded the same way (`prereg.md`, deviations 2–3).
- **The judge agreed with the final grade on 94.9%** (1,173 of 1,236).
- **The judge's two systematic errors:**
  - crediting a decline as correct_abstain on answerable questions;
  - crediting long lists that miss one keyed item (Apollo v24, y08).
- **Known question flaw:** y10 (held-out) has two valid events. It was graded strictly against the key, as in hard-v8's earlier run.

## Spend

$5.06 of the $15 cap, judge included: 252 calls in the last session, and the ledger covers all sessions.

## What would fix the failed bars (not built; for the next round, with new bars)

1. Run the citation check on abstain answers too, and either accept a fact line's text without its leading tag or tell Lia to copy the tag.
2. Make the citation pattern accept quotes that contain double quotes.
3. **Skills:**
   - read "goals", "projects" and other type words in a question as plain words, not as a filter on note type;
   - on "what did X say" questions, give every fact about X's advice and the user's own position from the same note, plus what's missing.

A rerun must be pre-registered again, with fresh held-out questions, because these fixes are tuned on the gate's failures.

## v2 validation (Apollo hard-v8 only, Haiku 5.5, 3 runs; a check, not a gate)

The fixes are in `prereg.md` under "v2 changes": the citation check runs on every answer; one quote unit (text before " (src:", tags included) inside «»; search before abstaining; the completeness and type-word rules; the shelf map only.

| | v1 final | v2 final |
|---|---|---|
| Score per run (of 24) | 22, 23, 21 (mean 22.0) | 23, 23, 22 (mean 22.67) |
| Partly correct | 2, 1, 3 | 1, 1, 2 |
| Apollo traps (v13–v16) abstained or declined correctly | all | all (12 of 12) |
| Shown citations, fresh re-check | 473 across three sets; 18 invented, all in unchecked abstains | 213 shown: 211 verified, 2 marked `[unverified]`, **0 invented** |
| Citations in abstain answers | not checked | 13 checked; 0 failed after the retry |
| Abstains sent back to search first | — | 2 of 11; both still abstained after the search (both traps) |
| Routing recall | 0.97 | 0.97 |
| $ / question | 0.0011 | 0.0013 |
| p50 / p90 latency | 5.3 / 9.9 s | 5.9 / 8.3 s (no-search p50 6.0 s) |

**Reading it:**
- **The score:** +0.67 per run is within run-to-run noise (v1's range was 2). The fixes did not cost accuracy.
- **Citations:** the citation failure mode is gone on this set. Both failing quotes were caught and marked: one dropped a `[stated]` tag, and one quoted a link line, not a fact.
- **Not shown yet:** the life-specific failures (type-word routing, completeness on Q11-like questions) can only be shown on life hard-v2, which isn't written yet.

**Tooling fix found during validation:** the `recheck` command still looked for the old `"` delimiter before `[unverified]`. Fixed. v1's count is unaffected, because v1's marks used `"`.

## v3 voice check (Apollo hard-v8 only, Haiku 5.5, 1 run; a check, not a gate)

The change is in `prereg.md` under "v3 voice check": first person, numbered footnotes, the abstain line "I don't have that in your notes yet.". The evidence rules and the final config are unchanged.

| | v2 final (3 runs) | v3 final (1 run) |
|---|---|---|
| Score (of 24) | 23, 23, 22 | **23** |
| Partly correct | 1, 1, 2 | 1 (v24, missing 1970-04-03, as in every v2 run) |
| Apollo traps (v13–v16) | 12 of 12 | 4 of 4, in the new abstain wording |
| Shown citations, fresh re-check | 213: 211 verified, 2 marked, 0 invented | 67: 65 verified, 2 marked, **0 invented** |
| Answers that needed the citation retry | 23, 22, 21 | 24 |
| Routing recall | 0.97 | 0.97 |
| $ / question | 0.0013 | 0.0014 |
| p50 / p90 latency | 5.9 / 8.5 s | 5.3 / 9.3 s |
| Third person in Lia's own sentences | not checked | 0 of 24 |
| Answers with a follow-up question | — | 3 of 24 |

Grading: the judge and the key-term grader agree on all 24, and the element rules from Step 2 change nothing (v24 still misses a date).

**Reading it:** accuracy and citations didn't drop. The bars set in the prereg are met: the score is within v2's range, and 0 citations were invented.

**Seen, not fixed** (changing anything now would be tuning after seeing the run):
1. **The retry runs on almost every answer, in v2 and v3 alike.** Haiku's first draft usually drops the `[stated]` tag, and the retry restores it. Each retry costs one extra call.
2. **v24: the retry's own words leaked into the reply.** "Here is the answer again with corrected citations:" opened the answer. This happened once in v2 as well.
3. **v24: one footnote held three quotes,** `[4] [[apollo-13]] «a»; «b»; «c»`. The second and third have no slug in front, so they were marked `[unverified]`, although both are true fact lines of that note. The error is on the safe side.

## Explore (F1–F7) on the dev sets, Haiku 5.5 (pre-registered under "Explore")

**Budget stop and grading:**
- The runs reached the $8 stop at $8.13. The last F7 run (`x-esc`, life-explore, run 3) was not run.
- **Not graded by the judge yet.** That would mean spending past the stop. Every score below comes from the free key-term grader, with the Step 2 rule that a decline without the exact abstain line counts as a correct abstain. Recalls, citations, latency and cost don't depend on the grader.

**Two ablation runs are invalid:**
- `x-no-plan` on life-explore: 10 of 10 rows are API timeouts.
- `x-no-coverage` on apollo-hard: 18 of 24 rows are timeouts.

**Main results** (score = correct + correct abstain, key-term grader):

| arm | set | score per run | facet recall | fact recall | citations verified / shown | invented | traps | p50 / p90 s | $ / q |
|---|---|---|---|---|---|---|---|---|---|
| x-base | apollo-hard | 23, 23, 23 of 24 | 0.99 | — | 203/205 | 0 | 12/12 | 6.7 / 11.2 | 0.0014 |
| x-all | apollo-hard | 23, 23, 23 of 24 | 1.00 | — | 227/228 | 0 | 12/12 | 11.5 / 16.2 | 0.0035 |
| x-esc | apollo-hard | 23, 23, 23 of 24 | 1.00 | — | 251/258 | 0 | 12/12 | 11.7 / 18.3 | 0.0036 |
| x-base | life (hard-v1, dev) | 17, 16, 14 of 20 | 0.94 | — | 230/230 | 0 | 9/9 | 6.2 / 10.4 | 0.0020 |
| x-all | life | 17, 15, 14 of 20 | 0.98 | — | 295/296 | 0 | 9/9 | 14.1 / 25.0 | 0.0066 |
| x-esc | life | 17, 15, 15 of 20 | 0.98 | — | 321/321 | 0 | 9/9 | 15.1 / 32.0 | 0.0380 |
| x-base | life-explore | 6, 5, 4 of 10 | 1.00 | 0.60 | 212/213 | 0 | — | 9.0 / 14.1 | 0.0024 |
| x-all | life-explore | 5, 6, 4 of 10 | 1.00 | 0.57 | 262/262 | 0 | — | 25.1 / 34.8 | 0.0104 |
| x-esc | life-explore | 9, 6 of 10 (run 3 not run) | 1.00 | 0.77 | 242/242 | 0 | — | 33.4 / 52.5 | 0.1278 |

**Ablations** (1 run each; `x-all` means in brackets):

| arm | apollo-hard | life | life-explore (fact recall) |
|---|---|---|---|
| x-no-plan | 22 (23) | 19 (15.3) | invalid (timeouts) |
| x-no-coverage | invalid (timeouts) | 14 (15.3) | 6 (5.0), 0.55 (0.57) |
| x-no-siblings | 22 (23) | 15 (15.3) | **3** (5.0), **0.46** (0.57) |
| x-no-upcoming | 22 (23) | 16 (15.3) | 5 (5.0), 0.54 (0.57) |

**Cost and latency by effort level** (levels from `x-all` run 1):

| arm | simple p50 s | simple $ | medium p50 s | medium $ | complex p50 s | complex $ |
|---|---|---|---|---|---|---|
| x-base | 5.5 | 0.0013 | 7.9 | 0.0020 | 8.1 | 0.0024 |
| x-all | **10.4** | 0.0032 | 15.9 | 0.0066 | 22.1 | 0.0098 |
| x-esc | 10.8 | 0.0032 | 16.8 | 0.0154 | 29.5 | **0.1603** |

**Guardrails for `x-all`:**
- Apollo accuracy didn't drop: met.
- Traps 100%: met (9/9 and 12/12).
- 0 invented citations: met.
- p50 ≤ 10 s on simple questions: **failed** (10.4 s).
- Mean cost ≤ $0.01 per question: **failed** on life-explore ($0.0104).

**`x-all` is not adopted.** F7 fails the cost guardrail by more than ten times ($0.16 per complex question) and is not adopted either.

**What the switches did** (behaviour, from the traces):
- **Write offers (P4):** 3 of 90 life answers in `x-base`, 0 of 90 in `x-all`.
- **"Want me to check/look" offers (P3):** 60 in `x-base`, 22 in `x-all`.
- **Parallel facts (P2):** the sibling sweep brought in German's "no progress" next to the thesis's on life-explore.
- **The cost of siblings:** the sweep ran a sibling round on 48 of 72 Apollo answers, which is most of the extra latency on simple questions.
- **Abstain wording drift:** with F4, some declines on traps come out as "partly" answers padded with nearby facts. They still decline, but not in the abstain line.

**Reading it:**
- **No measurable accuracy gain from F1–F6 on Haiku** with this grader; facet recall rose slightly (0.94 to 0.98 on life).
- **The one strong ablation signal is siblings** on life-explore: 3 vs 5 correct, and fact recall 0.46 vs 0.57.
- **Plan's ablation went the other way on life** (19 without it vs 15.3 with it). That is one run, so it is weak evidence.
- **The biggest gain came from a bigger model on complex questions** (F7 life-explore: 7.5 vs 5.0, fact recall 0.77 vs 0.57), at a cost the guardrail rules out.

## Known cost issue (2026-11-07, for later)

**Cold cache, round 2.** On the first question after the cache has gone cold, round 2 sometimes reads nothing from the cache (0 tokens) and re-writes the whole prefix. It was seen on Sonnet in two real complex questions; one cost about $0.11 extra. Warm questions read the conversation as intended. The cause isn't found yet. Not a blocker.
