# Yggdras

Second Brain.

A personal "second brain" that organizes projects, work, learning and job search through focused phone notifications. Built as a training ground for agentic software engineering: spec first, then agent-built, verified, versioned.

The build plan is [`planning/locked-plan-v1.md`](planning/locked-plan-v1.md). It sets the phases, their exit tests and the decision register.

## Status

Project setup only. Nothing is built yet. Next up is **phase 1a**: brain nodes written by hand, an index and a gateway skill. The brain itself lives in a separate private repo, never in this one (D3).

## Repository map

| Folder | Purpose |
|---|---|
| `intent/` | Why this exists, who it is for, what is in and out of scope |
| `requirements/` | Scoping answers and specs (the source of truth the agent builds from) |
| `planning/` | Layer design, task breakdowns, sequencing |
| `rationale/` | Decision records: why things are the way they are |
| `app/` | All code. Nothing else lives here |
| `skills/` | Operating instructions for agents (gateway, per-agent skills). No personal data |
| `evals/` | The eval set: questions with known answers, run as a gate on every change |
| `local-data/` | Your personal inputs (notes, calendar, profile). Git-ignored, never hard-coded |
| `constitution.md` | Binding rules for humans and agents |
| `CLAUDE.md` | Working instructions for Claude Code |

## Architecture in one line

Interface layer (notifications, chat) → Processing layer (agents, orchestrator) → Data layer (markdown brain as the source of truth, with a derived Graphify map built from its links; SQLite and a Supabase outbox come later). Details live in `planning/`.

## Quick start

```bash
cd app
uv sync
uv run pytest
uv run ruff check .
```

Copy `.env.example` to `.env` and fill in values when a feature needs them.

## Workflow

1. Answer the six scoping questions in `requirements/` (you, not the agent).
2. Write a spec with testable acceptance criteria.
3. Plan in `planning/`, then build with the agent in plan mode.
4. Verify with tests, review anything that touches stored memory.
5. Record the why in `rationale/`.
