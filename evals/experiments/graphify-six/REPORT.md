# Seven Graphify experiments: final report

2026-10-26 to 2026-10-27. Every experiment was pre-registered in [README.md](README.md) before it ran, and no prompt, question or scoring rule changed after results. Two pre-result tooling fixes are logged there under Deviations. Everything stayed local: nothing committed, `demo-brain/` and `brain/` untouched, Graphify pinned at 0.9.95, query logging off. The answer and checker model is Haiku 5.5; Graphify builds use Sonnet 5.5. Grading runs a key-term check first, then reads every flagged answer by hand. Paraphrases ("a dozen", "1,100 feet", "13 April 1970") are credited, and each such call is recorded in the result files.

## Summary

| # | Experiment | Pre-registered line | Result | Spend | Time |
|---|---|---|---|---|---|
| 1a | Arm A matcher fix | none: before and after | Recall 11→12 of 20; wrong new pairs 6→1 | $0 | <0.4 s per run |
| 1b | Verb checker | Recall ≥11/20, precision ≥33/34, verbs ≥90% | **FAIL.** Recall 12 and 11 pass. Precision 15/15 and 12/12 pass. Verbs 16/59 and 16/56 (27–29%) fail | $0.017 | 23–29 s per run |
| 2 | Harder held-out questions | An arm beats A when the clustered 95% CI of its paired difference is above 0 | **B beats A** (23/24 vs 19/24 every run). C ties A. D is worse | $0.252 | 79–109 s per run |
| 3 | Graphify picker and the filter bug | b recovers ≥3 of the 10 query misses; c ≥33/35 | **b: FAIL** (2 of 10). **c: met** (33 and 34), which shows Graphify adds nothing over our own pick | $0.183 | 140–300 s per run |
| 4 | `graphify update` as the structural map | ≥79/81 and ≥59/61, no extras, identical runs | **PASS.** 81/81 and 61/61, 0 extra, 0 dangling, identical, but verbs and direction are dropped | $0 | 6.6–15.7 s |
| 5 | Deep mode and a 15k token budget | +3 pairs over default in both runs, or generic share <50% | **Recall: FAIL** (8, 8, 4, 9 of 20). **Generic share: technical pass only**: deep mode turns `conceptually_related_to` into `references`, which is just as generic | $0.81 list ($1.21 Graphify's estimate) | 74–92 s per build |
| 6 | Upstream fixes | Run only if a fix is released | **Not run.** #4576, #3636 and #3614 are all unmerged; v0.9.96 contains none | $0 | — |
| 7a | Code: Graphify vs plain agent | A uses ≤60% of B's tokens, and is within 1 correct | **FAIL.** A used 109% of B's tokens and was 1.8× slower; both 8/8 | $0.10 | 13–26 s median per question |
| 7a | Hook on commit | Rebuild runs, $0, graph changes | **PASS.** Probe node added ~6 s after commit, $0 | $0 | ~6 s |
| 7b | Brain: Graphify vs plain agent vs C | Same ≤60% token test | **FAIL.** A used ~1.3× B's tokens. A, B and C all 10/10; C costs ~5× less per correct and runs 5–12× faster | $0.10 | 2.5–30 s median |

**Total spend: $1.47 at list prices** ($1.87 using Graphify's own build estimates), plus $0.013 for the unscored Experiment 7 pilot. This is within both the $5 and the $3 caps.

---

## Part A: questions on finished work

### Experiment 1, verb checker

**Q1. Classification of every verb miss** (hand-classified):

| Class | Run 1 (43 misses) | Run 2 (40 misses) |
|---|---|---|
| (a) Synonym or same meaning | 13 | 11 |
| (b) Right verb, wrong direction | 7 | 3 |
| (c) More general or more specific | 13 | 15 |
| (d) Genuinely wrong | 10 | 11 |

- **Lenient score** (counting (a) as correct): 29/59 and 27/56, about 48%. Adding (c) gives 42/59 and 42/56, about 71–75%. Even the lenient count is far from 90%.
- **(d) is the real failure rate:** 10 and 11 of the 59 and 56 accepted pairs with a gold verb, about 17–20%.

**Ten examples** (fact lines without their `(src: ...)` tail):

| From → to | Got | Gold | Class | From note's facts | To note's facts |
|---|---|---|---|---|---|
| apollo-13 → jack-swigert | crewed with | crewed by | a | …Command module pilot is Jack Swigert (was Ken Mattingly, changed 1970-04-10…)… | Apollo 13 role is prime command module pilot…; immune to rubella… |
| apollo-13-review-board → oxygen-tank-2 | investigated | examined | a | Traced the explosion to an electrically started fire in oxygen tank No. 2… | Exploded on 1970-04-13…; switches built for 28 V… |
| lunar-module → apollo-13 | saved by | saved | b | Apollo 13's lunar module Aquarius kept the crew alive after the oxygen tank failed… | …Crew used the lunar module Aquarius as a lifeboat… |
| nasa → apollo-program | run by | ran | b | Ran the Apollo program | Made six crewed lunar landings… |
| wernher-von-braun → saturn-v | developed by | led | b | Led the team that developed the Saturn V | Three-stage launch vehicle… |
| apollo-16 → john-young | crewed with | commanded by | c | Crew was John Young, Ken Mattingly and Charlie Duke | Commander of Apollo 16… |
| co2-scrubber-adapter → lunar-module | relevant to | fitted | c | CM canisters square, LM's round; adapter from hoses… | Two-stage lander built by Grumman… |
| apollo-1 → command-service-module | built | redesigned | d | …Led to a command module redesign that included a quick-opening hatch | Built by North American Aviation… |
| ken-mattingly → apollo-13 | crewed with | removed from | d | …was Apollo 13 command module pilot, changed 1970-04-10… | …was Ken Mattingly, changed 1970-04-10… |
| mission-control-houston → apollo-13 | landed at | ran | d | Controlled Apollo flights after launch… | …changed 1970-04-13 by Mission Control abort decision… |

**Q2. The gold list.**
- **Size:** 89 distinct verbs, and 69 of them are used only once.
- **Most used:** flew (9), part of (8), crewed by (7), crewed with (7), built (5), built by (5), includes (5), commanded/commanded by (3 each).
- **Near-duplicates and direction pairs are common:** crewed by / crewed with / flew; examined / investigated; designed by / built by; describes / tells / reports on.
- **Is exact-match grading fair? No.** On a free-form list where most verbs appear once, exact match mostly measures whether the model can guess the author's wording. The pre-registered metric stays as written, so Experiment 1 still fails. But the result means the verb list needs to be smaller and fixed before verb accuracy can be measured fairly (see decision 2).

**Q3. Flips between run 1 and run 2.**
- **Counts:** 21 of 96 items flipped accept/reject, and 36 of the items accepted in both runs changed verb.
- **What drives it:**
  - **Not hubs.** Flips involving a hub (degree ≥7) run at about the overall rate (13/21 vs 67% of all items).
  - **Not note length.** The flipping notes have 2–6 fact lines, like the rest.
  - **Indirect evidence does.** Flips cluster on pairs where the fact line mentions the other note only in passing: "One unit flew in the command module and one in the lunar module" (four guidance-computer pairs), the rubella-immunity lines (Haise, Lovell and Swigert to `rubella-crew-swap`), and generic `apollo-program` mentions.
  - **Why the evidence sits in one note:** by construction, every Arm A candidate's evidence is in one note, so this can't separate cases.
- **Verb flips:** they are mostly between synonyms (crewed with ↔ crewed by, piloted ↔ flew).

**Q4. Accepted new pairs: real missing links or noise?** This is my judgement; you decide what gets added.
- **Run 1, 15 pairs:** 12 real, 3 noise.
  - **Real:** apollo-11–apollo-guidance-computer, apollo-11–command-service-module (Columbia), apollo-13–command-service-module (Odyssey), apollo-guidance-computer–command-service-module, apollo-guidance-computer–lunar-module, beech-aircraft–command-service-module (the tanks), buzz-aldrin–lunar-module, charlie-duke–lunar-module, command-service-module–jack-swigert, fred-haise–rubella-crew-swap, jim-lovell–rubella-crew-swap, john-young–rubella-crew-swap.
  - **Noise:** apollo-program–grumman, apollo-program–jim-lovell ("Gemini before Apollo"), command-service-module–rubella-crew-swap.
- **Run 2, 12 pairs:** 7 real, 5 noise.
  - **Real:** apollo-11–command-service-module, apollo-13–apollo-13-measles-article, apollo-13–command-service-module, beech-aircraft–command-service-module, command-service-module–jack-swigert, john-young–rubella-crew-swap, lunar-orbit-rendezvous–nasa.
  - **Noise:** apollo-11–margaret-hamilton, apollo-program–grumman, apollo-program–margaret-hamilton, apollo-program–mission-control-houston, command-service-module–rubella-crew-swap.
- **The pattern:** "Apollo" mentions on a generic hub produce most of the noise.

**Q5. Same settings in both runs?** Yes.
- Same code and prompt: thinking off, effort low, the same JSON schema, batches of 20, 5 calls per run.
- Temperature was not set; Haiku 5.5 rejects non-default sampling values.

| Run | Tokens in / out | Cost | Time |
|---|---|---|---|
| 1 | 56,119 / 6,221 | $0.0087 | 29.4 s |
| 2 | 56,119 / 5,860 | $0.0085 | 23.3 s |

### Experiment 4, `graphify update`

**Q6.** Confirmed.
- **Agreement:** 0 extra pairs, 0 missing, 0 dangling, and identical pairs and edge counts across both runs on each corpus.
- **Build times:** 15.7 s and 8.0 s (intact), 6.6 s and 6.6 s (stripped).
- **Frontmatter:** it read the frontmatter and stored the whole block, aliases included, on each page node. But it labels nodes by file name (`apollo-13.md`), not by `name`.
- **Aliases:** whether it uses them to resolve links is untested here, because every link in the demo brain is written as a slug.
- **Verbs:** every link becomes a plain `references` edge, so verb text and direction are lost. It also adds 85 `contains` edges (page → heading).

### Experiment 6, upstream fixes

**Q7. v0.9.96 release notes (2026-10-26): nothing touches `query`, seeding or the context filter.** The changes that touch markdown and docs:
- watch quick-scan now includes paper-like markdown (#4750)
- the Obsidian export lists parallel relations (#4731)
- cross-document reference stubs are namespaced instead of dropped (#4738)
- `update` skips work when nothing changed (#4740)
- `extract` writes `cost.json`
- hook reminders are worded as facts (#4764)

The three PRs that matter to us (#4576 rationale, #3636 frontmatter body, #3614 markdown routing) are still open.

---

## Part B: Experiments 2, 3 and 5

### Experiment 2, harder held-out questions (24 questions, 3 runs)

**Q8. Scores.** Wilson 95% intervals are over 72 question-runs. Paired differences are against A, clustered by first gold note (23 clusters).

| Arm | Runs | Mean [95% CI] | Paired vs A [95% CI] | $ per correct | Billed tokens in, median / highest | End to end, median / slowest |
|---|---|---|---|---|---|---|
| A, variant C pipeline | 19, 19, 19 | 0.79 [0.68, 0.87] | — | $0.00088 | 3,912 / 8,629 | 3.82 s / 8.03 s |
| **B, whole brain cached** | **23, 23, 23** | **0.96 [0.89, 0.99]** | **+0.17 [+0.01, +0.32], beats A** | **$0.00059** | **2,794 / 2,818** | **3.16 s / 5.70 s** |
| C, A + fallback | 19, 19, 19 | 0.79 [0.68, 0.87] | 0.00, ties | $0.00098 | 4,180 / 10,443 | 4.27 s / 8.22 s |
| D, Graphify picks notes | 14, 13, 14 | 0.57 [0.45, 0.68] | −0.22 [−0.41, −0.04], worse | $0.00134 | 5,823 / 11,255 | 3.47 s / 8.64 s |

**By question type** (correct of question-runs):

| Arm | Multi-hop (18) | Unlinked (15) | Temporal (15) | Comparison (12) | Themes (12) |
|---|---|---|---|---|---|
| A | 18 | 6 | 15 | 12 | 6 |
| B | 18 | **15** | 15 | 12 | **9** |
| C | 18 | 6 | 15 | 12 | 6 |
| D | 6 | 6 | 15 | 12 | 2 |

**Who wins what:** B wins unlinked facts and themes, the two types where the answer sits in notes that no link joins. All arms tie on temporal and comparison. A, B and C tie on multi-hop; D loses multi-hop and themes.

**Q9. Arm B, whole brain cached.**
- **Prompt size:** 27,189 tokens per question in total.
- **Cache hits:** all 72 scored calls were warm. The cache write (~27k tokens, about $0.0034) was paid once, in the smoke test just before run 1, and the prefix stayed warm because B and the old-35 run share it.
- **Billed tokens:** about 2,794 per question, which is 99.7% cache reads.
- **Latency and cost:** median 3.16 s, $0.00059 per correct.
- **General knowledge:** none detected. Every B answer carried at least one citation, and none was flagged for an unsourced claim during grading.
- **Citation coverage:** sentence-level coverage was not captured in this run (only cited sources were logged). 100% of answers cited at least one note.

**Q10. Arm C, fallback.**
- **How often it fired:** 3 of 24 questions per run (x07, x08 and x22, the same three each time).
- **Did it help?** It fixed 0 of 9.
- **Cost:** about $0.0034 per run on top of A.
- **Why it can't help:**
  - *x07 and x08:* the fallback could only expand the nodes already picked, and the right notes (Lovell, Collins, Armstrong) are not linked to them.
  - *x22:* the inference lines sit in three unlinked notes.

**Q11. Arm B on the old 35.**
- **B:** 34, 35 and 35. The one miss is t03 in run 1, which opened "NOT IN BRAIN? No." and then answered correctly.
- **Variant C:** 35, 35, 35.
- **Paired difference:** −0.01 [−0.03, +0.01], so no difference.
- **Cost:** B $0.00049 per correct vs C $0.00062.
- **Speed:** median 2.79 s vs 3.18 s.

**Q12. Every miss, with the step that failed and the note that held the answer.**

| Question | Arm (runs) | Step | Note(s) not sent / what went wrong |
|---|---|---|---|
| x07 Gemini 12 pair | A, C (3/3) | pick | `jim-lovell`: it picked buzz-aldrin + michael-collins, and Lovell isn't a neighbour of either |
| x08 1966 Gemini flyers | A, C (3/3) | pick | `neil-armstrong`, `michael-collins`, `buzz-aldrin`: it picked jim-lovell/john-young, or apollo-program |
| x09 rubella-immune | A, C (3/3) | pick | `fred-haise`, `jim-lovell`, `john-young`: it picked ken-mattingly + rubella-crew-swap, so only Swigert reached the answer |
| x22 agent inferences | A, C (3/3) | pick | `ken-mattingly`, `margaret-hamilton`, `apollo-13`: it picked the two report notes |
| x23 Mission Control roles | A, B, C (3/3 each) | answer | `apollo-13` (abort decision) was sent; the answer left the abort out |
| x01, x02, x03, x05, x07, x21, x22, x24 | D | query | Graphify returned none of the gold notes; x02, x21 and x22 returned no notes at all |
| x08, x09 | D | query | Partial: `michael-collins` and `buzz-aldrin`, or `john-young`, never returned |
| x23 | D | answer | Abort omitted, as in A, B and C |

**Q13. Were the questions written before any run?**
- **Yes.** `held-out-v7-hard.yaml` was saved at 2026-10-26 21:24:25 (sha256 `b83c54ebce5ac074…`), the pre-registration README at the same time, and the first Experiment 2 result at 21:32.
- **No commit hash:** nothing is committed, as instructed, so the file times and hash are the evidence.

**Questions I now think are ambiguous** (flagged, not dropped):
- **x23:** "What roles did Mission Control Houston and its people play" is broad. Requiring the abort decision asks for more than the question clearly does, and all four arms missed it.
- **x08:** Lovell flew Gemini 12 in 1966 in reality. His note gives no year, but Aldrin's note dates Gemini 12 to 1966, so a careful reader could include Lovell. The key doesn't punish that.
- **x22:** it assumes the reader knows `[derived]` means an agent inference. The arms that failed did so because the pick missed the notes, not because of the tag.

### Experiment 3, the Graphify picker (35 questions, 2 runs)

**Q14. Results by variant.**

| Variant | Runs | Seed recall@2 | Filter collapses | $ per correct | End to end, median |
|---|---|---|---|---|---|
| a. Raw questions | 23, 25 | 12/28 | 6 per run | $0.00130 | 4.44 s |
| b. Trigger words removed | 28, 26 | 12/28 | 0 | $0.00131 | 4.03 s |
| c. `--seed` from our pick + `explain` | 33, 34 | 24/28 | 0 | $0.00074 | 8.16 s |

**How much of the gap to variant C's 35 each variant closes:**
- **(b), removing the trigger words:** about 3 of the 11 points, or ~27%. It fixed d02 and h07; the pre-registered bar was 3 of the 10 query misses, so the filter is a real but minor cause.
- **(c), seeding with our own picks:** about 9.5 of the 11, or ~86%. That's because the seeds are our picks. Its remaining misses (h06, h08) are notes Graphify's links don't reach. It ends up a slower, slightly worse copy of variant C.

### Experiment 5, deep mode and a smaller budget

**Q15. Results.**

| Build | Recovered of 20 | `conceptually_related_to` | `references` | Rationale nodes | New pairs (plausible) | Time |
|---|---|---|---|---|---|---|
| deep-1 | 8 | 7 of 71 (10%) | 63 | 2 | 1 (yes) | 87 s |
| deep-2 | 8 | 7 of 72 (10%) | 64 | 3 | 1 (yes) | 92 s |
| tb15k-1 | 4 | 3 of 66 | 63 | 0 | 0 | 74 s |
| tb15k-2 | 9 | 8 of 73 | 64 | 0 | 1 (yes) | 78 s |

- **Noise between runs:** deep mode overlap 0.97 (2 recovered flips); the 15k budget overlap 0.89 (5 flips).
- **Spend:** $0.81 at list prices, against Graphify's estimate of $1.21 and my pre-run estimate of $1.20–1.60.
- **Real verb edges:** none. Every edge is `references`, `conceptually_related_to` or `cites`.
- **The single new pair** in three of the builds is plausible: `north-american-aviation`–`oxygen-tank-2`.

---

## Part C: Experiment 7, the video's claims

**Setup:** fresh headless Claude Code sessions (2.1.310) on Haiku 5.5, project settings only, no MCP servers, 2 runs per arm. Hand-graded against the pre-registered keys; every session answered correctly once paraphrases were credited.

### 7a: code repo (8 questions)

| Arm | Correct (run 1 / run 2) | Total tokens, median | Tool calls, median | Seconds, median | $ per run | $ per correct |
|---|---|---|---|---|---|---|
| A, Graphify + graph | 8 / 8 | 91,098 / 90,057 | 3 / 2.5 | 25.7 / 26.0 | $0.025 / $0.026 | $0.0031 / $0.0032 |
| B, plain tools | 8 / 8 | 83,532 / 82,587 | 2.5 / 2.5 | 15.0 / 13.1 | $0.020 / $0.022 | $0.0025 / $0.0027 |

- **Build:** `graphify update` on the repo copy produced 586 nodes, 741 edges and 61 communities in 12.6 s, for $0.
- **Token claim fails here:** A used 109% of B's tokens, not ≤60%, and was about 1.8× slower. Quality was equal.
- **Why:** about 75–80k of every session is Claude Code's own fixed prompt and tools, read from cache. On a repo this small, `grep` plus one or two reads finds the answer directly, and the Graphify step adds calls.
- **Not tested:** the video's ~200-file repo with Explore subagents on a stronger model. Our result doesn't refute the claim there.
- **Hook claim:**
  - **What happened:** with `graphify hook install`, a commit triggered a background rebuild. `hook_probe.py` and `scratch_hook_probe()` appeared in the graph about 6 s later, for $0.
  - **Side effect:** the hook writes `~/.cache/graphify-rebuild.log`.
  - **Clean-up:** the hook was uninstalled and the clone deleted. The real repo's hooks were never touched.

### 7b: brain (10 of the old 35)

| Arm | Correct (run 1 / run 2) | Total tokens, median | Seconds, median | $ per correct |
|---|---|---|---|---|
| A, Claude Code + Graphify | 10 / 10 | 116,458 / 97,438 | 29.9 / 22.1 | $0.0032 / $0.0030 |
| B, Claude Code, plain tools | 10 / 10 | 78,770 / 80,714 | 12.5 / 11.6 | $0.0023 / $0.0023 |
| C, our pipeline (v6, 3 runs) | 10 / 10 / 10 | ~6,600 (≈3,000 billed) | 2.5–2.7 | $0.00057 |

- **Graphify saves nothing against a roaming agent on notes:** it cost about 1.3× B's tokens and about 2× B's time.
- **Both agents are far from our pipeline:** roughly 12–17× its tokens, 4–5× its cost per correct, and 5–12× its latency, for the same 10/10.

---

## Part D: recommendations

These follow the Big Picture. "One tool, one job" means a tool must beat a free baseline at a real job; "obvious is free" means deterministic code first.

1. **Graphify's role under D32: none in the brain path.** Optional at most as a code-repo map.
   - **Brain answers: no.** Label-only output scored 7/35. As a note picker, Graphify loses to our own pick: 25 vs 35, and on the hard set D 14 vs B 23.
   - **Brain links: no.** It produces no typed verbs in any mode, and its recall is beaten by the free scan.
   - **Brain map: no.** `graphify update` matches our structural pass exactly but throws away the verbs and direction we keep for $0.
   - **Code-repo map:** it works, is free, and rebuilds on commit. But at this repo size it saved no tokens and cost time, so keep it only if a larger code base shows the saving. Re-test before relying on it.
2. **Who proposes links: the fixed free scan proposes, a cheap model filters, you approve.**
   - **The scan:** fixed Arm A recovers 12/20 deleted links, with 1 wrong out of 29 new pairs, at $0.
   - **The filter:** a Haiku accept/reject pass kept every accepted new pair plausible (15/15 and 12/12) for under $0.01. Of those, I'd add 12 and 7.
   - **No model verb choice yet:** the free-form list (89 verbs, 69 used once) can't be matched reliably; even leniently it reaches about 48%.
   - **Recommendation:** adopt a small fixed verb vocabulary of roughly 15–20 canonical verbs, each with an inverse ("crewed by" ↔ "flew", "built by" ↔ "built"). Then re-run the verb checker against it as a new, separately named experiment. This touches the frozen node format (D31), so it needs a register amendment, and that decision is yours.
3. **Whole-brain cached prompt: adopt it as the default ("auto") while the brain is under about 100k tokens.**
   - **On the hard set:** it is the only arm that beats the pipeline (23/24 vs 19/24, CI above 0). It wins exactly on unlinked and themes questions.
   - **On the old 35:** it ties (34–35 vs 35).
   - **Cost and speed:** cheaper per correct ($0.00049–0.00059) and faster (2.8–3.2 s).
   - **The demo brain:** 42 notes are about 27k tokens, roughly 650 per note.
   - **Why 100k:** Haiku 5.5's price doubles above 100k-token prompts ($0.50 / $2.50), and accuracy at larger sizes is untested. So the limit is about 150 notes until a larger-brain test shows it holds.
   - **Cold starts:** each one costs about $0.0034 (5-minute cache). For questions spread over a day, a 1-hour cache or a measured cold-start cost is needed.
   - **Above the limit:** the pipeline stays the fallback.
4. **Version policy: stay on 0.9.95.**
   - v0.9.96 changes nothing we use (no query, seeding or filter changes).
   - Move only when #4576, #3636 or #3614 ships, and then re-run Experiment 6 as pre-registered.
   - Keep the pin when comparing runs, because `query` ranking is still moving upstream.

**Against the gate in the Big Picture.** Answering is not yet "rock-solid" on a hard eval:
- the pipeline scores 19/24 here;
- the whole-brain prompt scores 23/24;
- x23 is missed by every arm.

This 24-question set is a start. The gate needs a bigger, harder held-out set before discovery begins.

## Files

- **Pre-registration and deviations:** [README.md](README.md)
- **Experiment 1:** `exp1/` (Arm A before/after, checker runs, scores)
- **Experiments 2–3:** `exp2/`, `exp3/` (runs, overrides, `stats*.json`)
- **Experiment 4:** `exp4/scores.json`
- **Experiment 5:** `exp5/` (builds, `scores.json`)
- **Experiment 7:** `exp7/` (questions, session results, event logs)
- **Scripts:** `arm_a_fixed.py`, `verb_check.py`, `exp1_score.py`, `exp2_run.py`, `exp4_score.py`, `exp5_score.py`, `exp7_run.py`, `grade_stats.py`
- **Hard questions:** `demo-evals/held-out-v7-hard.yaml` (brain repo, uncommitted)
