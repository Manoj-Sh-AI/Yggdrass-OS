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
