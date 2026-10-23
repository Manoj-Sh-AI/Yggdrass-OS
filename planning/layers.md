# Layers

Starting point from the skills plan. Confirm or change each line; this is a design rep for Manoj.

| Layer | Responsibility | Candidates | Code location |
|---|---|---|---|
| Interface | What the user sees and does | Notification layer, chat | `app/src/yggdrass/interface/` |
| Processing | Rules and workflows | Agents, orchestrator (manager-worker) | `app/src/yggdrass/processing/` |
| Data | Stored information | Graphiti, Supabase | `app/src/yggdrass/data/` |

## Agentic components (kept separate, so the model can be swapped)

- Reasoning core (model)
- Orchestration
- Memory
- Tools (MCP)

## Memory types

| Type | Meaning | Maps to |
|---|---|---|
| Episodic | What happened | Agent transcripts |
| Semantic | Facts | Finalized facts promoted to central memory |
| Procedural | How to do things | TODO |

## Decisions still open

- Promotion rule: when does a note's fact become "finalized"?
- Consistency vs latency for central memory
- Where each memory type is stored
