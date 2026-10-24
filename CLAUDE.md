# CLAUDE.md

Working instructions for Claude Code in this repo. Read `constitution.md` first. It is binding.

## What this project is

Yggdras is Manoj's personal second brain. It is also a learning project for agentic software engineering, so process matters as much as output.

## Start of every session

1. Read `constitution.md`.
2. Read the relevant spec in `requirements/` and any plan in `planning/` for the task at hand.
3. Check `rationale/decisions/` before changing a design choice that was already decided.

## How to work here

- **Plan first.** Use plan mode. Propose, wait for approval, then build.
- **Do not guess.** If a spec has a gap, an edge case is undefined, or several reasonable designs exist, ask. Do not make silent decisions.
- **Never invent requirements.** Do not write scoping answers or acceptance criteria for Manoj. Draft options, then let him decide.
- **Verifier with every change.** Add or update tests alongside code. Run them before saying something is done.
- **Stay in scope.** Do not build features that are not in a spec.
- **Record the why.** When a non-obvious choice is made, add a decision record to `rationale/decisions/`.
- **Ask before touching stored data**, migrations, deletes, or anything irreversible.

## Layout

- `app/src/yggdras/interface/`: notifications, chat (user-facing)
- `app/src/yggdras/processing/`: agents, orchestrator, workflows
- `app/src/yggdras/data/`: Graphiti, Supabase, storage access
- `app/tests/`: tests mirror the package layout
- `local-data/`: personal inputs, git-ignored, never read into code as constants

## Commands

Run from `app/`:

```bash
uv sync                  # install dependencies
uv run pytest            # tests
uv run ruff check .      # lint
uv run ruff format .     # format
```

## Conventions

- Python 3.12, type hints on public functions, ruff for lint and format.
- Config from environment variables (see `.env.example`), loaded in one place.
- Keep functions small and layers separate. Data access never imports from interface or processing.

## Communication style

Keep answers short and structured. Lead with the result and flag decisions that need Manoj clearly.
