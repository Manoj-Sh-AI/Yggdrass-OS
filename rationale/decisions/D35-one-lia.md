# D35: One Lia

Date: 2026-11-06
Status: accepted (Manoj, 2026-11-06)

Register row: D35 in `planning/locked-plan-v1.md`. Related: D23 (skills in the brain repo), D27 (model as a setting, accuracy first), D34 (maps route, notes answer). Before this, main was tagged `pre-consolidation` (95b453e), so the parallel versions can be brought back.

## Context

From lia-v1 to v4, Lia grew as parallel arms behind switches: the explore steps F1–F7, the v4 arms ref/A/B/C, and the skill-library arm D. Every variant stayed in the code and the harness. Manoj's decision: one current Lia. Future changes replace parts in place, with no switches unless he asks.

## Decision

- **One behaviour, no switches.** `LiaConfig` keeps only the models, the effort setting, the owner's names for the voice check, and the upcoming view's "today" and horizon.
- **Models:** Haiku 5.5 by default, Sonnet 5.5 for complex questions. The level comes from a fixed effort rule: advice, decision or whole-picture wording, or 3+ areas, is complex.
- **Skills:** the skill library is Lia's only skill set.
  - `skills/lia/core.md` is always loaded.
  - `skills/lia/library/<name>.md` holds one playbook per job, with `name`, a one-line `description` and a `done_when` checklist.
  - The core skill and the index are in the cached prompt. `load_skill` loads at most two playbooks, in the same first turn as `open_notes`. `checklist` reports their lists before the answer, and the trace records both.
- **Kept as plain behaviour:**
  - search: fact-level search, alias expansion and stemming;
  - hints of unopened candidates, on complex questions only;
  - checks: the absence check, claim-support check and draft-leak strip, plus the sibling sweep on medium and complex questions;
  - voice and output: the capability rule, first-person voice, footnote citations and the verbatim wrapper;
  - `upcoming.md`, loaded for advice and timing questions.
- **Checking a change:**
  - all free tests;
  - one Apollo hard-v8 run (`harness.py check`, stopped at $0.50), compared with the stored final-v2 and x-base runs and the last check;
  - Manoj's own use.
  - No multi-run experiments unless he asks. `harness.py gate` waits for life hard-v2.

## Removed

| What | Why |
|---|---|
| F1 plan, F2 coverage tool, F4 verdict via that tool | No accuracy gain on Haiku, extra calls (explore results) |
| Arms ref/A/B/C/D and the harness's arm commands (`run`, `grade`, `table`, `recheck`, `xtable`, `v4checks`, `picks`, `e7`, `hashes`) | One Lia |
| 1d typed links on complex questions | Lost in E2 on Apollo; never adopted |
| The E6 cascade (router model, answer model) | Superseded by the effort rule |
| The L0 pre-pass (E3), neighbour descriptions (E8), map formats JSON and prose (E1), relationship map and outgoing-only links in Lia's prompt (E2, E4), description-length variants (E5) | Each lost or tied its experiment; the final config is the shelf map only, descriptions cut at 25 words |
| The note-level BM25 search | Replaced by the fact-level search |
| `answering.md` and `explore.md` in the brain repo | Every rule was moved to `core.md` or a playbook |
| `YGGDRAS_LIA_ARM`, the `--arm` flag | One Lia |

Stored results, traces and the pre-registrations stay as the record. The maps build still writes the relationship map for the viewer.

## Revisit when

- **A gate or Manoj's own use shows a regression** that a part of this config causes. That part is changed in place.
- **Life hard-v2 is frozen:** the v2 gate then runs on this config.
