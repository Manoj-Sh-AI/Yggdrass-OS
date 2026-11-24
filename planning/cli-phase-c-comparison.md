# Phase C: the same CLI built twice (orchestrated vs one session)

Date: 2026-11-24. Both runs had the same spec (`planning/cli-build-spec.md`), the same base
(#61), the same 12 checks, the same model (Opus 5.5) and the same orchestrator verification.
The orchestrator also re-ran every check on each result by hand.

| | Run 1: orchestrated (#62) | Run 2: one session (#63) |
|---|---|---|
| workers | 3 (brain-read, brain-write, app-commands) | 1 |
| SDK cost (estimate) | **$3.48** ($0.59 + $0.94 + $1.95) | **$2.74** |
| wall time, approve → finished | **14 min 55 s** | **30 min 3 s** |
| session time (sum) | 1312 s (222 + 414 + 676) | 1444 s |
| turns | 100 (16 + 30 + 54) | 75 |
| tokens in / out | 6,210 / 60,794 | 3,245 / 46,392 |
| cache read / cache write | 3,565,033 / 194,076 | 4,533,487 / 113,678 |
| parts passing every check first time | 3 of 3 | 1 of 1 |
| send-backs | 0 | 0 |
| tests written (brain-read / brain-write / app) | 19 / 29 / 20 | 20 / 45 / 101 |
| rule violations found in review, missed by the checks | none | 2 (below) |

**What the review found that the checks missed in Run 2**
1. `link-note <slug>` reads the brain over HTTP and decides sensitivity in Python. The spec
   forbids both.
2. `brain search` changed the query syntax from `websearch_to_tsquery` to `plainto_tsquery`.

**Run 1, for review:** `link-note` checks the note against `api.note_refs`, the app's
last-observed copy, as the spec requires. A note archived in the brain since it was last
observed could still be linked.

**Cost accounting:** no session was stopped or crashed in Phase C, so these SDK estimates
miss nothing the SDK counts. They are still client-side estimates. The Console figure for
2026-11-24 00:10:46–01:06:02 UTC is the real one. This comparison session's own work (N1, the
base, verification, merging) ran outside the orchestration key and is not counted for either
run.

## Verdict

- **Orchestration:** on this job it finished in half the wall time and met every rule. It
  cost $0.74 (27%) more and wrote fewer tests.
- **One session:** cheaper, with more thorough tests. It broke one safety rule and changed
  one behaviour, and the checks caught neither.
- **Why orchestration suited this job:** the job was shaped for it (disjoint files, a proving
  command per part, a shared base prepared in advance). That is Stage 6's own condition.
- **The evidence is thin:** one run each. The two review findings may be chance rather than
  something the approach causes; one run cannot tell them apart.
- **The lesson that holds either way:** the checks were not enough. The app modules need the
  same raw-access test that the brain modules got.
