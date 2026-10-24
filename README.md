# Yggdras

Second Brain.

A personal "second brain" that organizes thesis, work, German and job-prep through focused phone notifications. Built as a training ground for agentic software engineering: spec first, then agent-built, verified, versioned.

## Status

Project setup only. Nothing is built yet. The first piece to build is the **memory system** (ingest a note, promote finalized facts to central memory).

## Repository map

| Folder | Purpose |
|---|---|
| `intent/` | Why this exists, who it is for, what is in and out of scope |
| `requirements/` | Scoping answers and specs (the source of truth the agent builds from) |
| `planning/` | Layer design, task breakdowns, sequencing |
| `rationale/` | Decision records: why things are the way they are |
| `app/` | All code. Nothing else lives here |
| `local-data/` | Your personal inputs (notes, calendar, profile). Git-ignored, never hard-coded |
| `constitution.md` | Binding rules for humans and agents |
| `CLAUDE.md` | Working instructions for Claude Code |

## Architecture in one line

Interface layer (notifications, chat) → Processing layer (agents, orchestrator) → Data layer (Graphiti, Supabase). Details live in `planning/`.

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
