# Yggdras as an agentic operating system: the plan

Status: **DRAFT for Manoj.** Planning decisions are his (constitution rule 2). Every choice
the agent cannot make is marked **[decide]** and collected in §4. Nothing here is built by
writing it down.

**Sources.** The chart (whiteboard "Yggdras — the operating engine", rewritten on
2026-11-25), the validation report from the same day, and the repo. Each fact below was
checked against the code, CI, the `main` ruleset or a committed result. Where a fact could not
be checked from here, it says so.

## 1. What the OS is for, and the order of work

The one line (`intent/big-picture.md`) does not change: **turn what Manoj knows into
possibilities he can act on, reliably, cheaply and privately.** The OS connects components
(chat conductor, Lia, CLI, MCP, orchestrator, Temporal) behind **one door** (the commands) and
**one gate** (the `api.*` views).

**Order** (the ladder, plus both talks: foundations before reach, automation last):

1. land what exists;
2. make the brain's source real;
3. make the gate a wall;
4. pass the answering eval;
5. measure;
6. add capability that the measurements earn;
7. reach outward;
8. discovery.

Tracks 4 and 5 can run beside 2 and 3, because they touch different code. Nothing in a later
phase starts until the phase it depends on meets its **done-check**, which is a deterministic
check (a command, a test, a committed result), never an opinion.

## 2. How we will know the OS works (pre-registered before Phase 5 runs)

"Productivity in magnitudes" is the goal, not a fact: nothing has measured it yet. These are
the numbers that will:

| Number | Today | Where it comes from |
|---|---|---|
| Tokens, wall time and right answers per agent task | not measured | Phase 5 (Phase D), three tasks per arm |
| First-time pass rate of agent work | 4 of 4 parts in Phase C | the orchestrator's verdicts |
| Send-backs per task | 0 in Phase C | the orchestrator's report |
| Review findings the checks missed | 2 in run 2 of Phase C, 0 in run 1 | cross-testing |
| Revert rate on `main` | 0 of 101 commits since 2026-10-23 (explicit reverts) | `git log` |
| Share of tokens spent on verification | not measured | to be added to the orchestrator's report |
| Answering: the five lia-v1 bars | 3 of 5 pass (FAIL: traps, citations) | `evals/experiments/lia-v1/results.md` |

## 3. Phases

Owner: **M** = Manoj only (data, money, gates, `.claude/`, `.github/`); **A** = agent, reviewed
by Manoj; **A→M** = agent drafts, Manoj runs or approves.

### Phase 1 — Land what exists (no new features)
| Step | Owner | Done when |
|---|---|---|
| Close #43, #44 and #45: their work is already on `main` (#43, #44) or far behind it (#45) | M | closed |
| Apply app migrations 042–045 to the hosted database: `migrate_hosted plan`, then `apply` | M | `plan` reports nothing pending |
| Review the Tier 3 PRs and label them `tier3-reviewed`. Merge in order: #52, #53–#56, #60, #61, #64. Docs #57 and #59 any time. Decide #58 **[decide]** | M | `ci-gate` green on `main` after each merge |
| Set the repo variable `PRODUCTION_HEALTH_URL`, so the deploy watchdog stops skipping | M | the `deploy-watchdog` step passes on the next `main` run |

The brain never runs on the hosted database (D13). Brain migration 0005 is applied in Phase 2,
locally.

### Phase 2 — Make the brain's source real
| Step | Owner | Done when |
|---|---|---|
| A full database dump held off this PC (`planning/brain-backup.md`) | M | the dump exists off the PC; its date is recorded |
| Rehearse a restore into a scratch database | A→M | the restored row counts match the source |
| Apply brain migration 0005 to the local brain (`python -m yggdras.data.brain_db.migrate up`) | M | `status` shows version 5 |
| Run the pre-registered parity gate (`evals/experiments/rows-parity/prereg.md`; paid, up to $15) | M | every bar holds, and the results are committed |
| Switch `YGGDRAS_BRAIN_SOURCE` to `rows` | M | only after the two rows above; Lia answers from rows |

### Phase 3 — Turn the gate from a code test into a wall
| Step | Owner | Done when |
|---|---|---|
| N4: an agents-only database role, granted only `api.*`; the CLI and MCP connect as it | A→M | a test shows the role cannot `SELECT` from `brain.*` or `app.*` |
| Move the conductor's notes tools onto the views (they read the brain over HTTP and mask in Python today) | A | the raw-access test covers `conductor/catalog.py` |
| Decide who the gate is for: agents only, or Lia answering Manoj too **[decide]** | M | a decision record; `brain ask` and `brain open` follow it |
| Decide how terminal CLI brain writes are approved **[decide]** | M | a decision record; tests pin it |
| Property tests: no restricted slug, title or wikilink leaks, for any generated note graph | A | the tests pass on random graphs |
| Import boundaries enforced (interface / processing / data; `app` vs `app/api`) | A | a CI check fails on a forbidden import |
| Commit the deny rules (`.claude/`); wire a hook that runs the full suite | M | the rules are in the repo; the Stop hook reads a fresh verdict |

### Phase 4 — Answering passes its hard eval (the foundation; can run beside 2 and 3)
| Step | Owner | Done when |
|---|---|---|
| Fix the citation check on "Not in your brain" answers (18 failures, `cites = []` on abstain) | A | a test: an abstain answer with a quote is checked |
| Fix trap Q11 (partly right in all 3 runs); fix or replace the ambiguous y10 | A→M | the questions are frozen before the rerun |
| Rerun the lia-v1 pre-registration (paid) | M | all 5 bars pass, and the result is committed |
| Then resume the librarian checklist (`planning/librarian-plan.md`, 2026-10-31) | A→M | its own pass bars, written first |

### Phase 5 — Measure (Phase D)
| Step | Owner | Done when |
|---|---|---|
| The feature map: one page, with a slice per area; detail lives in `--help` | A | under one page; each worker gets only its slice |
| A pre-registration written before any run: three tasks (a lookup, a write, a multi-step task), arms, bars and a cost cap | A→M | committed before the first run |
| The arms: today's tools · the CLI · the CLI plus `find` and `run_batch` (only if decision 5 is yes) | M runs | results are committed; no saving is claimed that wasn't measured |
| Add the verification share of tokens to the orchestrator's report | A | the report shows it |

### Phase 6 — Capability, only where Phase 5 earns it
| Step | Owner | Done when |
|---|---|---|
| `find` and `run_batch` over MCP (read-only there, D33/D36) | A | they beat the CLI alone in Phase 5 |
| MCP tasks for long work (orchestration, Lia); Claude Code 2.1.304+ | A | a long call returns a handle; Temporal tracks it |
| Skills over MCP: the feature-map slices (needs Claude Code 2.1.331+; this machine has 2.1.329) | A→M | Claude Code upgraded; the skills load on demand |
| Elicitation on destructive verbs (`remove`, `undo`) | A | a test: the verb waits for a confirm |
| The conductor reads past judgements (today it only writes them) | A | a test: a rejected pattern changes the next plan |
| One run log: phone and older panel onto the conductor (connected-data step 6, G7) | A→M | its expand and contract steps, each proven |
| Run Fable's job-splitting once on a real job | M runs | the plan is approved and the result is reported |

### Phase 7 — Reach outward (after a sandbox exists)
| Step | Owner | Done when |
|---|---|---|
| WSL2 and an OS sandbox, or another boundary **[decide]** | M | a probe: a sandboxed command cannot read `.env` |
| Research Temporal workflow versioning (`agentic-engineering.md` flags it) | A | a decision record with a replay test |
| Write specs for the laptop gateway and for Claude Code / Codex as workers (no design exists in the repo) | A→M | approved specs in `requirements/` |
| Build them | A | each spec's acceptance tests |

### Phase 8 — Discovery
Starts only when Phase 4's done-check holds (the ladder rule). Then connected-data step 7
(`candidate_links`), with significance scored cheap-first.

## 4. Decisions for Manoj

1. **Who the gate is for:** agents only (Lia keeps seeing your sensitive notes when answering
   you), or every reader.
2. **Terminal CLI brain writes:** keep them card-free (version check only), require
   `tell_lia`-style approval, or allow them only from your own terminal.
3. **The Claude GitHub App:** install it (it adds AI review; your research notes it asks for
   write access to workflows) or not.
4. **WSL2:** move development there for a sandbox (costs a duplicated toolchain and Windows-side
   friction) or keep native Windows.
5. **The batch language:** may a step use an earlier step's output? Without that, multi-step
   tasks cannot batch.
6. **CLI-first or MCP-first:** decided with Phase 5's numbers, not before.
7. **Journals and subfolders:** in scope or not. Neither has a spec, and subfolders touch the
   frozen node format (D31).
8. **#58 (the orchestrator):** merge it as dev tooling, or keep it as a draft.

## 5. Not in this plan, and why

- **Dozens of parallel sessions:** one person and one usage limit. Phase C showed parallel
  work pays only on disjoint parts.
- **Team-scale PR metrics** (11,000 a month, 227 contributors): not a solo goal.
- **Claude Code Projects cloud threads:** no local Postgres, Temporal or emulator there.
- **CI auto-fix and auto-merge:** off. Your research recommends agents never auto-merge, and
  auto-fix waits on the Claude GitHub App decision.
- **Formal methods and release fuzzing:** not ruled out, but no decision is recorded. They
  come up after Phase 3.
