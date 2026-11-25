# Yggdras as an agentic operating system: the plan

Status: **decided 2026-11-25** (Manoj's eight rulings, §4; why:
`rationale/decisions/20261125-agentic-os-decisions.md`). Nothing here is built by writing it
down.

**Sources.** The chart (whiteboard "Yggdras — the operating engine", rewritten on
2026-11-25), the validation report from the same day, and the repo. Each fact below was
checked against the code, CI, the `main` ruleset or a committed result. Where a fact could not
be checked from here, it says so.

## 1. What the OS is for, and the order of work

The one line (`intent/big-picture.md`) does not change: **turn what Manoj knows into
possibilities he can act on, reliably, cheaply and privately.** The OS connects components
(chat conductor, Lia, CLI, MCP, orchestrator, Temporal) behind **one door** (the commands) and
**one gate** (the `api.*` views, made a wall by a database role).

**Order.** Both talks close on the same instruction: make the checks catch what you care
about and configure the environment *before* automating. So:

1. land what exists;
2. **foundations**: fix answering, and add the checks that are missing;
3. make the brain's source real;
4. make the gate a wall;
5. measure;
6. add capability that the measurements earn;
7. reach outward;
8. discovery.

Phase 2 comes before everything that decisions 5–8 touch. Nothing in a later phase starts
until the phase it depends on meets its **done-check**, which is a deterministic check (a
command, a test, a committed result), never an opinion.

## 2. How we will know the OS works

"Productivity in magnitudes" is the goal, not a fact: nothing has measured it yet. These are
the numbers that will:

| Number | Today | Where it comes from |
|---|---|---|
| Tokens, wall time and right answers per agent task | not measured | Phase 5, three tasks per arm |
| Testability of each surface (deterministic tests, no model needed) | CLI: 231 command tests on #64 | Phase 5 |
| First-time pass rate of agent work | 4 of 4 parts in Phase C | the orchestrator's verdicts |
| Send-backs per task | 0 in Phase C | the orchestrator's report |
| Review findings the checks missed | 2 in run 2 of Phase C, 0 in run 1 | cross-testing |
| Revert rate on `main` | 0 of 101 commits since 2026-10-23 (explicit reverts) | `git log` |
| Share of tokens spent on verification | not measured | to be added to the orchestrator's report |
| Answering: the five lia-v1 bars | 3 of 5 pass (FAIL: traps, citations) | `evals/experiments/lia-v1/results.md` |

## 3. Phases

Owner: **M** = Manoj only (data, money, gates, `.claude/`, `.github/`, merges); **A** = agent,
reviewed by Manoj; **A→M** = agent drafts, Manoj runs or approves.

### Phase 1 — Land what exists (no new features)
| Step | Owner | Done when |
|---|---|---|
| Close #43, #44 and #45: their work is already on `main` (#43, #44) or far behind it (#45) | M | closed |
| Apply app migrations 042–045 to the hosted database: `migrate_hosted plan`, then `apply` | M | `plan` reports nothing pending |
| Review the Tier 3 PRs and label them `tier3-reviewed`. Merge in order: #52, #53–#56, #60, #61, #64; then #58 (decision 8). Docs #57, #59 and #65 any time | M | `ci-gate` green on `main` after each merge |
| Set the repo variable `PRODUCTION_HEALTH_URL`, so the deploy watchdog stops skipping | M | the `deploy-watchdog` step passes on the next `main` run |

The brain never runs on the hosted database (D13). Brain migration 0005 is applied in Phase 3,
locally.

### Phase 2 — Foundations: answering, and the checks that are missing
These are the prerequisite the talks name, not polish. Each step has its own done-check.

| Step | Owner | Done when |
|---|---|---|
| Fix the citation check on "Not in your brain" answers (18 failures, `cites = []` on abstain) | A | a test: an abstain answer with a quote is checked |
| Fix trap Q11 (partly right in all 3 runs); fix or replace the ambiguous y10 | A→M | the questions are frozen before the rerun |
| Rerun the lia-v1 pre-registration (paid) | M | all 5 bars pass, and the result is committed |
| Property tests: no restricted slug, title or wikilink leaks, for any generated note graph | A | the tests pass on random graphs, in CI |
| Import boundaries enforced (interface / processing / data; `app` vs `app/api`) | A | a CI check fails on a forbidden import |
| Commit the deny rules; wire a hook that runs the full suite | M | the rules are in the repo; the Stop hook reads a fresh verdict |
| Then resume the librarian checklist (`planning/librarian-plan.md`, 2026-10-31) | A→M | its own pass bars, written first |

### Phase 3 — Make the brain's source real
| Step | Owner | Done when |
|---|---|---|
| A full database dump held off this PC (`planning/brain-backup.md`) | M | the dump exists off the PC; its date is recorded |
| Rehearse a restore into a scratch database | A→M | the restored row counts match the source |
| Apply brain migration 0005 to the local brain (`python -m yggdras.data.brain_db.migrate up`) | M | `status` shows version 5 |
| Run the pre-registered parity gate (`evals/experiments/rows-parity/prereg.md`; paid, up to $15) | M | every bar holds, and the results are committed |
| Switch `YGGDRAS_BRAIN_SOURCE` to `rows` | M | only after the two rows above; Lia answers from rows |

### Phase 4 — Turn the gate into a wall (decision 1, amended 2026-11-25, and decision 2)
| Step | Owner | Done when |
|---|---|---|
| **Only Lia reads the brain.** Every other agent (conductor workers, task and calendar agents, orchestration workers) has **no brain grant at all** and asks Lia, who decides what is relevant to hand over | A→M | a test: the agent role cannot `SELECT` from `brain.*`; Lia's role can |
| N4: the agents' database role reads only `api.*` app views and has **no write grant** on the brain | A→M | a test: the role cannot write to `brain.*` |
| Move the conductor's notes tools behind Lia (they read the brain over HTTP and mask in Python today) | A | the conductor's catalog has no brain reader of its own |
| No agent edits or deletes a note without Manoj's approval (`tell_lia` plus confirm). Terminal CLI brain writes ask for confirmation in an interactive terminal (TTY); **the TTY check is a convenience, not the protection.** An agent can open a pseudo-terminal, and the role's missing write grant is the protection | A | tests: no TTY means refused; under the agent role, a write is refused by the database |
| No agent sends private information to an outside service (email, connectors, web). **How this is enforced is not designed yet** | A→M | an approved spec, then its tests |

### Phase 5 — Measure (Phase D)
| Step | Owner | Done when |
|---|---|---|
| The feature map: one page, with a slice per area; detail lives in `--help` | A | under one page; each worker gets only its slice |
| A pre-registration written before any run: three tasks (a lookup, a write, a multi-step task), the arms, bars and a cost cap | A→M | committed before the first run |
| The arms: today's tools · the CLI · the CLI plus `find` and `run_batch`, with independent steps only (decision 5) | M runs | results are committed; no saving is claimed that wasn't measured |
| Compare **testability** as well as tokens and wall time (decision 6): how much of each surface deterministic tests can exercise without a model | A | a column in the results |
| Add the verification share of tokens to the orchestrator's report | A | the report shows it |

### Phase 6 — Capability, only where Phase 5 earns it
| Step | Owner | Done when |
|---|---|---|
| `find` and `run_batch` over MCP (read-only there, D33/D36). **Independent commands only** until workers run in WSL2 (decisions 4 and 5 are one decision) | A | they beat the CLI alone in Phase 5 |
| MCP tasks for long work (orchestration, Lia); Claude Code 2.1.304+ | A | a long call returns a handle; Temporal tracks it |
| Skills over MCP: the feature-map slices (needs Claude Code 2.1.331+; this machine has 2.1.329) | A→M | Claude Code upgraded; the skills load on demand |
| Elicitation on destructive verbs (`remove`, `undo`) | A | a test: the verb waits for a confirm |
| The conductor reads past judgements (today it only writes them) | A | a test: a rejected pattern changes the next plan |
| One run log: phone and older panel onto the conductor (connected-data step 6, G7) | A→M | its expand and contract steps, each proven |
| Run Fable's job-splitting once on a real job. Merging #58 is not permission to lean on it: automating a loop that produces slop produces more slop | M runs | the plan is approved and the result is reported |
| Journals: written as a spec only after answering passes Phase 2's rerun (decision 7) | A→M | an approved spec in `requirements/` |

### Phase 7 — Reach outward (decision 4)
| Step | Owner | Done when |
|---|---|---|
| Split: orchestration workers run in WSL2 with an OS sandbox. Windows-side app work (Expo, WebView2) stays native. This is a staging post; cloud sessions are the destination | A→M | a probe: a sandboxed worker command cannot read `.env` |
| Remember what the sandbox does not cover: Claude's own files, MCP servers and hooks. All three reach the brain, so N4 still carries the protection | — | — |
| Once workers run in WSL2: `run_batch` may run dependent steps (a script runner), which collects the rest of Code Mode | A | the measured gain over independent-only batch |
| Research Temporal workflow versioning (`agentic-engineering.md` flags it) | A | a decision record with a replay test |
| Write specs for the laptop gateway and for Claude Code / Codex as workers (no design exists in the repo); then build them | A→M | approved specs, then their acceptance tests |

### Phase 8 — Discovery
Starts only when Phase 2's answering done-check holds (the ladder rule). Then connected-data
step 7 (`candidate_links`), with significance scored cheap-first.

## 4. Manoj's decisions (2026-11-25)

1. **Only Lia has direct access to the brain** (amended 2026-11-25; first ruling: "gate for
   agents only"). Other agents ask Lia. Agents may use what Lia gives them, but they cannot edit
   or delete notes without approval, and they cannot send private information to outside
   services. N4 enforces the access part.
2. **Terminal CLI brain writes:** confirmation in an interactive terminal, as a convenience.
   N4 is the protection: the agent role has no write grant. Build both, and never treat the
   terminal check as the guard.
3. **No Claude GitHub App for now.** This is against talk 1, which recommends a Claude review
   on every PR. The reason: that reviewer earns its place once you stop reading diffs, and you
   still read them. Revisit it the moment Tier 1 or 2 changes merge unread.
4. **WSL2, split:** workers in WSL2, app work on native Windows. A staging post, with cloud
   sessions as the destination.
5. **Batch runs independent commands only** until workers run in WSL2. Decisions 4 and 5 are
   one decision.
6. **CLI or MCP:** measured, with testability compared alongside tokens and wall time.
7. **Journals later**, after answering passes. **Subfolders no** (deferred: areas already
   group notes, and nesting adds no enforcement; a judgement call).
8. **Merge #58** (Manoj merges), without leaning on it before the foundations hold.

## 5. Not in this plan, and why

- **Dozens of parallel sessions:** one person and one usage limit. Phase C showed parallel
  work pays only on disjoint parts.
- **Team-scale PR metrics** (11,000 a month, 227 contributors): not a solo goal.
- **Claude Code Projects cloud threads:** no local Postgres, Temporal or emulator there.
- **CI auto-fix:** off; the web auto-fix needs the Claude GitHub App (decision 3).
- **Auto-merge:** off. Your research recommends agents never auto-merge.
- **Formal methods and release fuzzing:** not ruled out, but no decision is recorded. They
  come up after Phase 4.
