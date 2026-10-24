# Experiment: does node strength improve answers?

Run 2026-10-24 on invented data only. The question it was meant to answer: should the real brain aim for **fifty thin nodes or twenty rich ones**?

## Method

1. **Score** all ten fixture nodes on a six-dimension rubric (0–2 each, max 12): [`rubric-scores.yaml`](rubric-scores.yaml). Base spread: Project Furrow 12, everything else 6–8.
2. **Strengthen** the three weakest (`campo-verde-agro` 6, the Okafor chunk 6, `orchard-site-visits` 7 on the tie-break) to 12/12 each, in a copy: [`brain-b/`](brain-b/). IDs are kept, and the only index changes are those three rows. The base fixture is untouched.
3. **Seal** `brain-b` *before* writing any question (sha256 of its files: `483d3202533748320300e50f6df0f785fd1ea2a81d8082858aa833531541b90d`). Facts were written without knowing which questions would be asked.
4. **Write** ten stress questions from the *base* fixture's facts only, two each of synthesis, comparison, causal, four-hop and partial-knowledge: [`questions.yaml`](questions.yaml) (sha256 `dfc479e01ac9414662b87065de00bcb2662bc6cc779e56c0cc82b66cc25deec7`). They were not edited between runs.
5. **Run** each question once in a fresh agent against the base fixture (run A) and against `brain-b` (run B). Same skill, same prompt, only the brain path differs.
6. **Score** each answer 2 / 1 / 0 (correct and complete / thin / wrong or an unwarranted refusal) against the marks written into the question set beforehand. Results: [`results/`](results/). The runner records pass = score 2, with the score in the notes.

## Result

| Q | Kind | A | B | What happened |
|---|---|---|---|---|
| s01 | synthesis | 2 | 2 | |
| s02 | synthesis | 2 | 2 | |
| c01 | comparison | 2 | 2 | B gave a richer answer (4% yield loss, erratum, drip assumption), but the scale caps at 2 |
| c02 | comparison | 2 | 2 | |
| k01 | causal | **1** | 2 | A never opened `ines-navarro`, where the reason is. That node is identical in A and B, so this is run-to-run variance |
| k02 | causal | 2 | 2 | Both refused to invent a reason, and A ruled out the later sensor slip |
| f01 | four-hop | 2 | 2 | B opened 6 files, over the ~5 budget, because the richer links invited extra hops |
| f02 | four-hop | 2 | **1** | **A regression caused by strengthening**: see finding 2 |
| q01 | partial | 2 | 2 | Both hedged correctly |
| q02 | partial | 2 | 2 | B gave a richer answer, but capped |
| | | **19/20** | **19/20** | **Delta: 0** |

## What it shows

1. **No measurable gain from strength at this size.** Both runs scored 19/20, and neither loss came from a thin node. A's miss was a retrieval choice on an unchanged node; B's miss came from the strengthening itself. With ten nodes and multi-hop links, the base fixture already holds enough to answer these questions.
2. **Strengthening can hurt provenance.** I made the chunk's 30% saving a superseded fact (preprint 35%, corrected by an erratum). That moved its source from `Okafor 2029 p.15` to `erratum`. A fact has one source slot, so the page citation was lost and f02 dropped a point. **This is a node-format finding, parked rather than fixed** (the format is frozen): a superseded fact can't carry both its origin and the source of the change.
3. **Rich links cost file budget.** f01 in B traversed six files instead of five. More links make a node easier to reach, but they also invite more hops.
4. **The experiment can't yet tell 1 point from noise.** k01 flipped between runs on an identical node. With one trial per question, any delta of 1–2 points could be chance.
5. **The scale has a ceiling.** B's answers were visibly richer on c01 and q02 but couldn't score above 2. Questions written from thin facts can't reward depth.

## What it means for the real brain

Inconclusive. It does not support "twenty rich nodes over fifty thin ones", and it doesn't refute it. What it does support:

- **Coverage first.** Every miss so far (here and in the 20-question set) was about *which node* got opened, never about a node being too thin to answer.
- **Put the reason in the same node as the fact it explains, or link the two explicitly.** k01 failed once because "scope narrowed" and "why" lived in different nodes.
- **Don't strengthen by adding change history** until a superseded fact can keep its original source.

## A better next run, if it's wanted

- Three trials per question per condition, to separate signal from variance.
- Write the ground truth first, then derive thin and rich versions of the *same* nodes from it, and write questions that need the rich facts. That way depth can score.
- Add questions where the answer lives in exactly one strengthened node, so a strength effect can't be masked by multi-hop routes.
