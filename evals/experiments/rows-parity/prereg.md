# Parity gate: markdown path vs row path (D44 §7)

Pre-registered 2026-11-12, before any run. Nothing here is changed after a run.

## What is compared

Lia answering from the files (`Library`) against Lia answering from the database (`RowLibrary`, a throwaway local PostgreSQL loaded by the loader). Both read one frozen copy of the brain's `library/`, taken once before the first run. Same skills, same model settings, same pinned "today" (2026-11-02, as the lia-v1 harness).

Before any paid run, a free check on that copy: Lia's view is identical on both paths (every note's text and citable lines, a search per note name, the manual, and the maps apart from `map_version`).

## Sets

- **life hard-v1:** 20 questions. Key at brain commit `723329b`, SHA-256 `252bc081…`; key terms in `local-data/lia-v1/life-terms.json`, SHA-256 `5c3f3b42…`. Q4, Q6 and Q9 are traps (ABSTAIN).
- **life-dev-explore x04 and x09** (Manoj, 2026-11-12: the RK Constructions cases). Rubric in `local-data/lia-v1/explore-rubric.json`, SHA-256 `b5c31bf2…`.
- **Apollo:** dropped from the gate (Manoj, 2026-11-12).

The runner stops if any of these hashes differs.

## Runs

- Two runs per path, interleaved: markdown 1, rows 1, markdown 2, rows 2.
- Questions run as the lia-v1 harness runs them: 6 workers; the first question of each run warms the cache.
- Graded by the harness's judge (Haiku 5.5, the RUBRIC in harness.py) and by key terms.
- Network errors are retried with backoff, at most 3 tries per call.
- Budget: stop at $12 of a $15 cap.

## Bars (all must hold to switch the default to rows)

- **Accuracy:** the row path's mean judge score is not below the markdown path's mean by more than the markdown path's own run-to-run difference.
- **Traps:** 3/3 in every run on both paths.
- **Invented citations:** 0 in every run on both paths.
- **Unverified absences:** 0 on hard-v1 Q2 (robotics), x04 and x09, in every run on both paths.
- **Cost per question and p50/p90 latency:** the row path's mean is within the larger of two bounds of the markdown path's mean: the markdown run-to-run difference, or 20%. The 20% floor is my operational reading of "within run-to-run noise", since two runs give a rough spread.

## Even if every bar holds

D44 also needs a full database dump held outside this PC before the switch. The default stays `markdown` until that dump exists, whatever the gate says.
