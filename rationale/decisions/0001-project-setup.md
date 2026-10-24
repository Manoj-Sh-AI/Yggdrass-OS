# 0001: Project setup

Date: 2026-10-23
Status: accepted

## Context

Setting up the repo before building. The skills plan recommends a "wrapper architecture": code in `app/`, with folders for intent, requirements, planning and rationale, plus `constitution.md` and `CLAUDE.md`, all versioned together.

## Decision

- Wrapper structure as described in the plan, adapted from its description (the original template was not available at setup time).
- Python 3.12 for `app/`, managed with uv and `pyproject.toml`. Graphiti is a Python library, agent orchestration is strongest in Python, and one language keeps the first slice simple.
- Interface layer starts inside the same Python package. A separate TypeScript front end can be added later if the notification layer needs one.
- ruff for lint and format, pytest for tests, GitHub Actions CI from day one.
- Personal data lives in `local-data/` (git-ignored), never in `app/`.

## Alternatives considered

- TypeScript throughout: friendlier for web UI, weaker fit for Graphiti and the agent tooling.
- Python plus TypeScript monorepo now: more setup, no feature needs it yet.
- conda: matches existing Anaconda install, but a uv lockfile is easier to reproduce in CI and deployment.

## Tradeoffs

Simplicity and fast iteration over a polished UI stack from the start.

## Consequences

If the interface needs a rich front end, add a separate package then and record a new decision.
