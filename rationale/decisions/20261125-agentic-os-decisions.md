# The agentic OS: eight decisions, and foundations first

Date: 2026-11-25
Status: accepted (Manoj, 2026-11-25)

## Context

`planning/agentic-os-plan.md` left eight choices open. Manoj ruled on each, checked against
four talks: Anthropic on how sessions run today, Graphbot on trust through checks, MCP 2.0, and
Cloudflare's Code Mode.

## Decision

1. **The gate is for agents only, enforced by a database role (N4).** Lia answering Manoj
   keeps full access.
2. **Terminal CLI brain writes:** an interactive-terminal confirmation as a convenience. N4
   (no write grant for the agent role) is the protection.
3. **No Claude GitHub App for now**; revisit when Tier 1 or 2 changes merge unread.
4. **WSL2, split:** workers in WSL2 with a sandbox, app work on native Windows. Cloud sessions
   are the destination.
5. **Batch runs independent commands only** until workers run in WSL2.
6. **CLI or MCP:** measured in Phase D, testability included.
7. **Journals after answering passes; subfolders deferred.**
8. **Merge #58** (Manoj merges).

**Order:** the import-boundary lint and the property tests on the sensitivity rule join the
answering fix as Phase 2, ahead of everything that decisions 5–8 touch.

## Alternatives considered

- **Gate for every reader.** This would hide Manoj's own sensitive notes from Lia answering him.
- **The terminal check as the guard.** Refused: an agent can open a pseudo-terminal.
- **Install the App now (talk 1's advice).** Deferred while Manoj still reads every diff;
  cross-testing found more than a reviewer would have.
- **Dependent batch steps now.** They need model-written logic to run somewhere safe, and
  there is no sandbox yet.
- **Choosing CLI or MCP up front.** The talks disagree: talk 2 uses CLIs for tokens and
  testability, while talk 4 favours MCP for context.

## Tradeoffs

- Safety over convenience: N4 adds a role and a connection to manage.
- Talk 1's automated review is given up for now, and Manoj's review time stays the bottleneck.
- Batch saves less until dependent steps arrive.
- The WSL2 split keeps two toolchains.

## Consequences

- The agent role becomes the one protection every later piece relies on: Code Mode runs
  "under the agent's existing permissions", and the sandbox does not cover MCP servers or
  hooks.
- Checks come before automation. The orchestrator is merged but not leaned on until Phase 2
  holds.
