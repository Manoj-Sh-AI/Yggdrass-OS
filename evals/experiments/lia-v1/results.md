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
