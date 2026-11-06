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

## Talk to Lia in Claude (read-only MCP connector)

`yggdras mcp` runs Lia as a local stdio MCP server with two read-only tools and one prompt:
- `ask_lia(question, context)`: Lia's reply in her own voice ("I", "you"), with numbered footnotes `[1] [[slug]] «fact»`, or "I don't have that in your notes yet.", then a line of cost, time and verified citations. It starts with a line telling the chat model to show it exactly as written;
- `open_note(slug)`: one note's full text, to check a citation;
- the prompt `talk-to-lia`: every message in the conversation goes to Lia, and her replies are shown verbatim.

Each `ask_lia` result starts with one instruction line for the chat model, then Lia's reply inside `<lia_reply>…</lia_reply>`, which the chat model shows unchanged.

There is one Lia (D35):
- **Models:** Haiku 5.5 answers simple and medium questions; Sonnet 5.5 answers complex ones (advice, decision or whole-picture wording, or 3+ areas).
- **Skills:** `<brain>/skills/lia/core.md` is always loaded, with an index of the job playbooks in `<brain>/skills/lia/library/`. Lia loads one or two playbooks per question with `load_skill`, alongside her first `open_notes`, and reports their "done when" checklist before answering.
- **Search:** fact-level, with word forms and the brain's aliases. Complex questions also get hints of notes not yet opened, and advice and timing questions the upcoming view.
- **Free checks:** a sweep for parallel facts, then citations, claim support, absence claims, write offers and draft talk, in one retry. Whatever still fails is marked.

How it works:
- It reads the brain's current files and rebuilds the maps when a note or skill changes. It never writes to the brain.
- Every answer leaves a trace in `local-data/traces/`.
- A change is checked with the free tests and one Apollo run: `uv run python ../evals/experiments/lia-v1/harness.py check` (about $0.50 at most).

The examples below use these placeholders:
- `<APP>`: this repo's `app` folder, after `uv sync`;
- `<BRAIN>`: the brain repo;
- `<ENV>`: a `.env` file with `ANTHROPIC_API_KEY`. The key stays in that file and is never logged.

**Claude Code:**

```bash
claude mcp add yggdras --scope user -e "YGGDRAS_BRAIN=<BRAIN>" -e "YGGDRAS_ENV_FILE=<ENV>" -e "PYTHONIOENCODING=utf-8" -- "<APP>/.venv/Scripts/python.exe" -m yggdras.interface.cli mcp
```

Check it with `claude mcp list`; it should show `yggdras: … ✔ Connected`.

**Claude Desktop:** add this to `claude_desktop_config.json` (Settings → Developer → Edit Config), then quit and restart Claude Desktop:

```json
"mcpServers": {
  "yggdras": {
    "command": "<APP>\\.venv\\Scripts\\python.exe",
    "args": ["-m", "yggdras.interface.cli", "mcp"],
    "env": {"YGGDRAS_BRAIN": "<BRAIN>", "YGGDRAS_ENV_FILE": "<ENV>", "PYTHONIOENCODING": "utf-8"}
  }
}
```

On macOS or Linux, use `<APP>/.venv/bin/python`.

## Workflow

1. Answer the six scoping questions in `requirements/` (you, not the agent).
2. Write a spec with testable acceptance criteria.
3. Plan in `planning/`, then build with the agent in plan mode.
4. Verify with tests, review anything that touches stored memory.
5. Record the why in `rationale/`.
