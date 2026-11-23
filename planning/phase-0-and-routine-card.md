# Phase 0 and first UI slice

Historical first-slice record. The later [revised Phase 1 authorization](phase-1-application-foundation.md) approves the separate backend, application PostgreSQL and authentication. Its ownership/storage contract supersedes the browser-only gate below.

## Phase 0 deliverables

Record the approved application boundaries and locked functional invariants in `requirements/application-architecture-v1.md`. Keep unresolved memory/storage, task-policy, API and provider decisions explicit. Phase 0 finalizes the application ownership contract, not those unapproved implementation details.

## Build sequence

1. Define read-only routine metadata and separate execution types, transitions and validation.
2. Add an application-only versioned browser repository without migrating legacy notes or accessing the Brain.
3. Build a controlled Routine Execution Card and a Today-only storage container.
4. Integrate it between the main agenda and supporting dashboard panels, with existing styling and responsive behavior.
5. Verify pure state transitions/storage, component states and browser start/progress/complete/reload/failure flows. Check existing frontend regression tests, types and production build.

## Gates after delivery

Stop after this slice. Weekly planning, production storage/APIs, agent skills, adaptation rules, scheduling, notifications and Yggdress orchestration require separate approval. Claude's existing memory subsystem is never an implementation target for this task.

## Verification — 2026-11-08

- `npm test`: 61 passing tests, including 22 routine domain/storage tests and 5 controlled component rendering tests. Existing repository/scenery unit tests remain green.
- `npm run typecheck`: passed. `npm run build`: passed.
- Production browser suite: 10 of 11 passed initially, including all 4 new routine interaction tests. The existing missing-scenery test assumed an initial sunrise image; at night the application correctly retained a different loaded scene. The assertion now checks the actual fallback contract and a targeted rerun passed. All 11 browser checks are verified across these runs.
- New browser coverage: start/progress/completion across reloads, unchanged definition and legacy demo bytes, explicit 100%-versus-completion behavior, invalid percentages, quota failure preserving drafts, retry after reload, keyboard/phone layout, explicit demo reset, and preservation of unreadable/newer-format records.
- Inspected `verification/routine-card-desktop.png` and `verification/routine-phone.png`; full Today integration screenshot is `verification/routine-today-desktop.png`. Verification images remain local/ignored.
- `git diff --check` passed. No changes to `app/src`, `app/pyproject.toml`, `planning/locked-plan-v1.md` or `constitution.md`. No dependencies added.

## Files in this slice

Created:
- `requirements/application-architecture-v1.md`: Phase 0 ownership, integration contracts, locked invariants and unresolved decisions.
- `requirements/spec-routine-execution-card.md`: scoped acceptance criteria and explicit prototype conventions.
- `planning/phase-0-and-routine-card.md`: this implementation/verification record.
- `rationale/decisions/D40-routine-application-boundary.md`: separation and implementation tradeoffs.
- `app/web/src/lib/routines.ts`: immutable metadata, execution state, commands and validation.
- `app/web/src/lib/routine-repository.ts`: application-only browser persistence.
- `app/web/src/components/routine-execution-card.tsx`: reusable controlled component.
- `app/web/src/components/today-routine.tsx`: Today persistence/loading/failure container.
- `app/web/tests/routines.test.ts`, `app/web/tests/routine-execution-card.test.tsx`, `app/web/e2e/routine.spec.ts`: domain/storage, component, and browser verifiers.

Modified:
- `app/web/src/components/today.tsx`: card integration.
- `app/web/src/app/globals.css`: responsive card styling using the existing design system.
- `app/web/src/lib/repository.ts`: explicit Reset demo also restores the fictional routine.
- `app/web/vitest.config.ts`: TSX component test discovery and existing path alias resolution.
- `app/web/e2e/resilience.spec.ts`: scope the toast assertion now that the card also announces status; remove the time-dependent scenery-poster assumption.
- `app/web/README.md`: reuse, persistence and scope documentation.
