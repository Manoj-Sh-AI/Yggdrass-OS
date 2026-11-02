# lia-v1: Lia's read side, the map experiments and the gate (pre-registration)

Written 2026-11-02, **before any run.** Committed before the first API call of this experiment. No question, key, pass bar or rule below changes after a run starts; any change is logged under "Deviations after start" with its reason.

## Pinned inputs

| Input | Pin | Check |
|---|---|---|
| Brain notes | brain commit `f6fe26a`, a clean read-only worktree | `harness.py verify` before every run |
| Answer key | `evals/hard-v1.md` at brain commit `723329b` | SHA-256 `252bc0813f630f4a4810c52e946850b3caa8ac45ecb113e4b96795265e985640`; stop if it differs |
| Apollo questions and keys | `archive/demo-evals/hard-v8.yaml` (24) and `held-out-v8.yaml` (10), read from the `f6fe26a` worktree | — |
| Lia's skills | `skills/lia/answering.md`, brain commit `24f2e72` | SHA-256 `11bce556fe5b37c2c9141cea8f9d3dce0bf14a395f09eb9e6ac7dff8ea3dab3b` |
| Code | main `6301c55` plus this branch (`lia-read`) | — |

- **Keys stay out of Lia's reach (D30).** Lia's tools read only the brain root under test: `library/` for the life set, `archive/demo-brain/` for Apollo.
- **The keys are read only by the grader.** Lia sees question text only.
- **The brain tree's hash** is compared before and after every run, and the run stops if it changed.

## Datasets and roles

| Set | Size | Role |
|---|---|---|
| `apollo-hard`: Apollo hard-v8 | 24 (4 traps) | **The only tuning set.** Every experiment decision is made on it |
| `apollo-held`: Apollo held-out-v8 | 10 (2 traps) | Scoring only, in the gate |
| `life`: life hard-v1 | 20 (Q4, Q6, Q9 keyed ABSTAIN) | Scoring only, in the gate |

## Lia's default configuration

- **Template:** the maps as built (pipe rows), with the relationship map on (inverses written, mentions on) and descriptions as committed.
- **Switches:** L0 off, neighbour descriptions off.
- **Model settings:** effort `low`, thinking at the model's default.
- **Prompt:** two 1-hour cache breakpoints, in this order: tools → [skills + taxonomy + node template] → [atlas → shelf map → relationship map] → question.
- **Model:** chosen as below.

## Step 1: the model for the default arm

- **The pick run:** the default config, run once each with `claude-haiku-5-5`, `claude-sonnet-5-5` and `claude-opus-5-5` on `apollo-hard`.
- **The rule:** the most accurate wins. A difference of 1 question or less out of 24 is a tie, and the cheaper model wins a tie.
- **Reuse:** each pick run counts as run 1 of that model's default arm.

## Step 2: experiments (on `apollo-hard` only, 3 runs per arm)

Each experiment changes one thing against the default.

| # | Arms | The simpler arm (kept unless the other wins) |
|---|---|---|
| E1 | pipe rows (default) vs JSON vs prose | pipe rows |
| E2 | shelf + relationship map (default) vs shelf map only | shelf map only |
| E3 | L0 off (default) vs on | off |
| E4 | inverses written out (default) vs outgoing only | outgoing only |
| E5 | descriptions cut to ≤ 10 vs ≤ 15 vs ≤ 25 words, from the same notes | ≤ 25 words, the least cut, so closest to committed |
| E6 | one model (default) vs cascade: Haiku 5.5 routes (opens and searches), the default model answers (Sonnet 5.5 if the default is Haiku) | one model |
| E7 | synthetic library brains of 100 / 300 / 1,000 notes, 30 questions each, routing only (stop at the first `open_notes`) | — (measured, not decided) |
| E8 | neighbour descriptions off (default) vs on | off |

**Run-to-run noise** is the range (highest minus lowest score) of the default arm's 3 runs on `apollo-hard`.

**The decision rule:**
- The other arm replaces the simpler one only if its mean score is higher by more than the noise.
- With three arms (E1, E5), each arm is compared with the simpler one.

**The final config** is the default with every experiment's winner applied. It is written to `final-config.json` before the gate runs.

## Step 3: the gate (all three sets, 3 runs each)

The final config against variant C (the current pipeline), both on the chosen model.

**Pass bars, all required:**

1. **Accuracy:**
   - **Life:** Lia's mean score on `life` is at least variant C's mean.
   - **Apollo:** Lia's mean is at least variant C's mean on `apollo-hard` and on `apollo-held`, separately.
2. **Traps** (life): Q4, Q6 and Q9, keyed ABSTAIN, are graded correct_abstain in all 3 runs. Q10 and Q11 are graded correct, as keyed, in all 3 runs.
3. **Citations:** 100% of shown claims are verified or marked `[unverified]`, and there are 0 invented quotes. An invented quote is a shown citation without the `[unverified]` mark that fails a fresh re-check against the pinned notes.
4. **Latency:** p50 ≤ 8 s over Lia's gate questions that used no search.
5. **Cost:** Lia's mean cost per question in the gate is within 2× of the PR #28 estimate for the chosen model:
   - Haiku 5.5: ≤ $0.004;
   - Sonnet 5.5: ≤ $0.08;
   - Opus 5.5: ≤ $0.14.

**Verdict:** PASS only if all five pass. Otherwise FAIL, listing each failed bar and the three most likely causes, with evidence from the traces.

## Scoring

- **Score per run:** the number of questions graded correct or correct_abstain. Partly correct counts 0 and is reported separately.
- **Grades:** correct, partly_correct, wrong, correct_abstain, wrong_abstain.
- **Grader 1** is an LLM judge (`claude-haiku-5-5`, fixed rubric in `harness.py`, structured output). It sees the question, the key's answer and the answer being graded.
- **Grader 2** is a deterministic key-term check: the Apollo keys, and for the life set a list of key terms derived from the frozen key and written before any run. The terms are personal, so they stay in `local-data/lia-v1/life-terms.json` (SHA-256 `5c3f3b4201ba3169071874dd91689b382b1091773555986b221972ad1d4f945d`); the harness stops if the file changes.
- **Hand review:** Claude reads every answer where the two graders disagree, plus a random 20% of agreements (seed 7), and writes the final grade into `overrides.json` (life overrides stay local). The final grade is the review grade where reviewed, otherwise the judge's.
- **Agreement rate:** the judge-versus-final agreement rate is reported.
- **Also reported per arm:**
  - the citation-check pass rate;
  - routing recall (the share of the key's notes that Lia opened);
  - tokens, cost per question, and latency p50 and p90.

## Budget

- **Cap:** $15 in total, tracked live in `local-data/lia-v1/spend.json` and covering every model call, the judge included. The runner stops at **$12** and the report follows.
- **The full schedule** is about 1,100 question-equivalents on the chosen model:
  - default runs 2 and 3: 48;
  - E1: 144; E2, E3, E4, E6 and E8: 72 each; E5: 216;
  - E7: about 90;
  - the gate: 162 for Lia, plus variant C at about half a Lia question each.
- **Projection:** after Step 1, projected cost = (the chosen model's mean $ per question in its pick run) × the remaining question-equivalents.
  - **If the projection fits under the $12 stop:** Steps 2 and 3 in order.
  - **If it doesn't:** the gate runs first with the default config. Then experiments run in this order while budget remains: E3, E8, E2, E4, E6, E1, E5, E7. The final config is then reported but not gated.

## Real-brain privacy

- **Life set:** answers, traces and grades stay in `local-data/` (git-ignored).
- **Committed:** only Apollo results and traces, aggregate numbers, and this file.

## Deviations declared before the start

1. **Experiments run on `apollo-hard` only.** The ground rules allow tuning only on Apollo hard-v8, and choosing a winner is tuning. The life and held-out sets are used only in the gate.
2. **Variant C is ported** (`variant_c.py`):
   - the model is a parameter;
   - thinking is left at the model default, because Opus 5.5 and Sonnet 5.5 refuse `disabled`;
   - fact lines are read in both formats;
   - the graph is built in library mode for the life brain;
   - costs use the 5.5 cache rates.

   Otherwise it is unchanged, including its 5-minute cache and the hub links it gathers.
3. **The skills live at brain commit `24f2e72`,** later than the pinned notes. They sit outside `library/` (D23), and the notes Lia reads are `f6fe26a`'s.
4. **Contamination risk, disclosed.** The skills' author (Claude) wrote the life answer key with Manoj. The skills follow the librarian plan's eleven rules and the time rule, and were not tuned on any life question. They were smoke-tested on one Apollo question that is not in any eval set.
5. **Apollo is a flat brain:**
   - its top folders stand in for areas in the maps;
   - its free-text link verbs are kept, with `←verb` as the other direction;
   - its "manual" is a short generated folder list and note format, since it has no taxonomy.
6. **The trace format is defined here** (one JSON per question with its steps, answer, citations, check, calls and cost), since `planning/lia-and-connector.md` has none.
7. **L0's stoplist** is the fixed list in `library.py`.

## Deviations after start

1. **Lia's model is chosen on Apollo hard-v8, and the gate runs once (Manoj, 2026-11-02, before any gate run is graded or read).**
   - **Why:** Step 1's tie rule picked Haiku 5.5. The reviewed scores were Haiku 22, Sonnet 23 and Opus 23, and a gap of 1 counts as a tie.
   - **Unchanged:** the experiments (Step 2) ran on Haiku.
   - **The model choice:** the final config runs with `claude-haiku-5-5` and `claude-sonnet-5-5`, 3 runs each, on `apollo-hard` only.
     - The higher mean score wins.
     - A tie is a difference of means no larger than the run-to-run spread, the larger of the two models' ranges. The spread is reported.
     - The cheaper model wins a tie.
   - **Then the gate runs once** with the chosen model: Lia's final config against variant C on the same model, on `life`, `apollo-hard` and `apollo-held`, 3 runs each, against the five bars.
   - **Life and held-out decide nothing.** `life` and `apollo-held` are used only for the gate verdict, never for any choice.
   - **The superseded version.** An earlier instruction (choose the model on `life` plus `apollo-held`) was meant to be recorded here in commit ff3cc1e. The edit did not land, and that was not noticed until now. The instruction was replaced before any of its runs was graded or read. Two runs had already finished: the final config on `life` with Haiku, runs 1 and 2. They were moved, ungraded and unread, to `local-data/lia-v1/quarantine/` and are not used.
2. **The reviewer's listing showed answers cut at 900 characters** for the Step 1 review. The judge always saw full answers. Every pick-run answer that needed it (v24) was re-read in full. The listing shows full answers from Step 2 on (commit a4879ed).
3. **Hand review in Step 2:**
   - **Rules:** systematic grader disagreements were resolved with written element rules, applied to every row of those questions in every arm, so all arms were graded alike:
     - v24 needs all seven dates;
     - v12 needs Marshall;
     - v19 needs 7129, 125 and P64;
     - v23 needs the four builders and the guidance computer;
     - v07 needs House, 1982 and died.
   - **Visible text counts,** including quoted fact lines.
   - **Declines without the exact prefix** (v13, v16) are graded correct_abstain.
   - **Re-grading Step 1** under these rules gives Haiku 22, Sonnet 24, Opus 23. The tie rule would then pick Sonnet, not Haiku. Deviation 1 settles the model on `apollo-hard` either way.
4. **Harness additions after the prereg commit:**
   - tooling only: `recheck` (gate bar 3), model-keyed overrides in `table`, the `final` arm taking each run's model, and `grade` skipping the E7 summary;
   - no change to any question, key, bar or decision rule.

## v2 changes (Manoj, 2026-11-02, recorded before any v2 run)

The v1 gate failed bars 2 and 3. These are general fixes, with no question-specific patch.

**The fixes:**
1. **The citation check runs on every answer,** "Not in your brain." answers included, with the same one retry and then `[unverified]`.
2. **The quote unit is defined once,** in `node.md`, D34, Lia's skill and the checker alike:
   - **What a quote is:** the fact line's text after its leading `- ` and before ` (src:`, tags such as `[stated]` included. A quote may carry the source bracket; the checker ignores it.
   - **The delimiter is «…»,** so fact lines that contain double quotes can be cited: `[[slug]] «fact text»`.
   - **Frontmatter citations** are unchanged: `[[slug]] field: value`.
3. **The abstain rule:**
   - **In the skill:** before answering "Not in your brain.", Lia runs `search_notes` with the question's key terms and opens the top hits.
   - **In code:** if a reply abstains and no search ran for this question, Lia is sent back once to do that search before answering.
   - **In the trace:** the search is logged (`abstain_search`).
4. **The completeness rule (skill):** when a note supports the answer, give every fact in it that bears on the question, not only the first.
5. **Type words are topics (skill):** words like "goals", "projects" and "decisions" in a question are topics, not note-type filters. Facts can live in any note type.
6. **The final config is the shelf map only (E2).** The relationship map is still generated (the viewer and discovery use it) but not loaded into Lia's prompt. Descriptions are cut at 25 words, and the rest is default (`final-config.json`, unchanged).

**Validation:** Apollo hard-v8 only, the final config with these fixes, Haiku 5.5, 3 runs. It is reported against v1's final config on the same set (22, 23, 21) and v1's citation re-check. No bar is applied: it is a check, not a gate.

**The v2 gate:**
- **Sets:** life hard-v2 (20 new questions in the same seven categories, written and answered by Manoj, frozen at a pinned brain commit before any v2 run), Apollo held-out-v8 and Apollo hard-v8.
- **Model and runs:** Haiku 5.5, 3 runs each, against the same five bars.
- **Life hard-v1 is now a dev set,** contaminated by the failures seen and by skills written after its key. It is not part of the v2 gate.

**Inputs:** the skills change (new SHA in `harness.py`), the run tag `v2`, and the budget ledger continuing from $5.06.

## v3 voice check (Manoj, 2026-11-02, recorded before the run)

**The change:** Lia's voice, not her evidence rules.
- **Skills v3** (brain commit 96710fd): she speaks to Manoj in the first person ("I", "you"), warm and brief, with at most one short follow-up question.
- **Citations are numbered footnotes:** `[1]` in the text, then `[1] [[slug]] «fact text»` lines at the end. The quote unit and the checker are unchanged. One rule is added: a marker with no footnote fails the check.
- **The abstain line** is now "I don't have that in your notes yet." The code still recognises "Not in your brain.".
- **Unchanged:** the final config, the maps, the retry and the abstain search.

**The check:** Apollo hard-v8 only, the final config (arm `final-v3`), Haiku 5.5, **1 run**. It is graded and hand-reviewed with the same written element rules as Step 2, and reported against v2's three runs (23, 23, 22) and v2's fresh citation re-check (213 shown, 0 invented). It is a check, not a gate. "Didn't drop" means a score within v2's run-to-run range (22 to 23) or above it, and 0 invented citations.

**Inputs:** the new skills SHA in `harness.py`, the run tag `v3`, and the budget ledger continuing.

## Explore: look wider, check coverage, then answer (Manoj, 2026-11-02, recorded before any run)

Manoj calls this "Lia v3". The code names it **explore**, because v3 is already the voice change (skills 96710fd).

**The changes** (each a `LiaConfig` switch; all off is the baseline):
- **F1 `plan`:** the first call is forced to the `plan` tool. It lists facets (named and implied areas), 1–4 sub-questions and an effort level by fixed rules. The reply names each facet's hub, adds free hints (areas whose note names or aliases share a word with the question), and asks for one wide `open_notes` call.
- **F2 `coverage`:** the `coverage` tool grades each sub-question. A gap gets a corrective round: search with rewritten terms, open the top hits, grade again. Rounds are capped by effort (simple 1, medium 2, complex 3), and so are searches (3, 4 and 6). The turn limit rises to 12.
- **F3 `siblings` (free code):** after the draft, two-word key phrases are taken from its cited facts. A phrase counts when both words carry meaning: not a stopword, not a word of the note's own name, not a date. "no", "not" and "never" count. Phrases found in more than 8 fact lines are dropped. Up to 6 matching fact lines from notes the draft didn't cite go back to Lia once; those notes count as opened.
- **F4 `verdict` (on whenever exploring):** the coverage call carries a verdict of sufficient, partly or insufficient. An answer written without one is sent back once.
- **F5 `capability` (on whenever exploring):** a skill rule plus a code check for write offers in Lia's own sentences. An offer joins the one retry.
- **F6 `upcoming`:** `upcoming.md` is built by code: `date | slug | title (kind)` for dated facts, review dates and `valid:` starts within 120 days. It is loaded only for complex questions or time words, and "today" is pinned to 2026-11-02.
- **F7 `escalate`:** after the plan, Sonnet 5.5 takes over complex questions.
- **Skills:** `skills/lia/explore.md` (brain commit fc985e5) is loaded only when a switch is on. `answering.md` is unchanged (v3).

**Sets (all dev; none is used for a gate):**
1. Apollo hard-v8.
2. Life hard-v1 (a dev set since v2).
3. **life-dev-explore:** Manoj's 10 cross-area questions. The rubric gives expected areas, expected facts and required elements. It was written by Claude from the pinned brain f6fe26a, not by Manoj. It lives in `local-data/lia-v1/explore-rubric.json`, SHA in `harness.py`.

**Arms** (Haiku 5.5, final config, today pinned):
- `x-base` (all off) and `x-all` (F1–F6): 3 runs each on all three sets.
- `x-esc` (F7): 3 runs on all three sets.
- Ablations `x-no-plan`, `x-no-coverage`, `x-no-siblings` and `x-no-upcoming`: 1 run each on all three sets.
- F4 and F5 have no ablation (always on).

**Metrics:**
- Accuracy: the judge's grade, as in v2, hand-reviewed where the judge and key-term grader disagree. The written element rules from Step 2 apply on Apollo.
- Facet recall: expected areas touched by an opened note.
- Fact recall: expected facts cited, tags ignored; life sets only.
- Citations: fresh re-check, verified, marked and invented.
- Traps: correct abstains on ABSTAIN questions.
- p50/p90 latency, and cost per question by effort level (the levels from `x-all` run 1).

**Guardrails** (any failure means `x-all` is not adopted):
- accuracy on Apollo hard-v8 doesn't drop (mean of runs, beyond the larger run-to-run range);
- traps stay 100% correct;
- 0 invented citations;
- p50 latency ≤ 10 s on simple questions;
- mean cost ≤ $0.01 per question.

**F7 rule:** adopted only if it beats `x-all` on the dev sets by more than run-to-run noise. Cost decides only ties (D27).

**Switch recommendations:** a switch is recommended ON if its ablation lowers the dev score or a recall. One ablation run is weak evidence, and the report says so.

**Budget:** its own ledger, `local-data/lia-v1/spend-explore.json`, with a stop at $8 of a $10 cap. Runs go in order: `x-base`, `x-all`, the ablations, then `x-esc`. Whatever the stop cuts is reported as not run.
