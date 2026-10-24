# Layers

Starting point from the skills plan, synced to `locked-plan-v1.md`. Confirm or change each line; this is a design rep for Manoj. D-numbers refer to that plan's decision register.

| Layer | Responsibility | Candidates | Code location |
|---|---|---|---|
| Interface | What the user sees and does | MCP connector (phase 2), Telegram notifications (5), Tauri app (6) | `app/src/yggdras/interface/` |
| Processing | Rules and workflows | Filter agent (3), ingest agent and orchestrator (4) | `app/src/yggdras/processing/` |
| Data | Stored information | Markdown brain (source of truth, D1); Graphiti on FalkorDB, derived (D5, D6); SQLite (D12); Supabase outbox (D14) | `app/src/yggdras/data/` |

Layered vs service-oriented layout is open until phase 2 (D28).

## Agentic components (kept separate, so the model can be swapped)

- Reasoning core (model), behind an interface from day one (D27)
- Orchestration, extracted after two agents exist (D24)
- Memory: the brain files
- Tools (MCP): the connector, the only validated write path (D22)

## Memory types

| Type | Meaning | Maps to |
|---|---|---|
| Episodic | What happened | Session transcripts in the brain's `inbox/`, filtered and deleted after 48h (phase 3) |
| Semantic | Facts | Fact lines in brain nodes, tagged `stated`, `observed` or `derived`, with source and date |
| Procedural | How to do things | Skills in `skills/`, outside the brain (D23) |

## Decisions still open

- Code layout: layered vs service-oriented (D28, at the start of phase 2)
- Seed domains for the first nodes (open before phase 1a, build order step 2). The `type` enum is settled by D29

Settled by the plan: the promotion rule (explicit save plus nightly suggestions, phase 3; the orchestrator confirms worker results, phase 4); consistency vs latency (files lead and the graph catches up nightly, D6 and D8); where each memory type is stored (table above).
