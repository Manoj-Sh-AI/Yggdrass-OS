# Constitution

Binding rules for everyone working in this repo, human or agent. If a rule here conflicts with a request, stop and ask. Changes to this file are made by Manoj only.

## Process

1. **Spec before code.** No feature is built without a spec in `requirements/` that has testable acceptance criteria. If code and spec disagree, fix the code. Update the spec first if the spec is wrong, then regenerate.
2. **The first two lifecycle steps are not delegated.** Requirements and planning decisions are made by Manoj. The agent may draft and challenge; Manoj decides.
3. **Everything lives in the repo.** Decisions, plans and rationale are written to files, not left in chat. If it is not in the repo, it does not exist next session.
4. **Narrow scope.** One vertical slice at a time. Anything out of scope goes in `intent/` as "later", not into the code.

## Architecture

5. **Process and data are separate.** No personal data (notes, calendar, profile, names, keys) is hard-coded in `app/`. Personal inputs live in `local-data/` or external stores and flow in at runtime. The test: delete my data and someone else's can plug in.
6. **Three layers, one responsibility each.** Interface (`app/src/yggdrass/interface`), processing (`.../processing`), data (`.../data`). A layer talks only to the one directly below it.
7. **Model-agnostic core.** The reasoning model, orchestration, memory and tools are separate parts. Swapping the model must not require rewriting the orchestrator.
8. **Name the tradeoff.** Every design choice states what it trades among latency, cost, reliability, consistency, maintainability and simplicity. Record it in `rationale/`.

## Quality

9. **Every build ships with a verifier.** Acceptance criteria become automated tests. Edge cases are tested: empty note, missing field, duplicate fact.
10. **Human review on stored data.** Any change that writes to, migrates or deletes stored memory needs Manoj's review before it runs against real data.
11. **Irreversible actions need approval.** Deleting data, force-pushing, dropping tables, rotating secrets: ask first.

## Security

12. **No secrets in git.** Keys live in `.env` (git-ignored). `.env.example` lists names only, never values.
13. **Least privilege.** Sub-agents and tools get only the access their job needs.

## Hygiene

14. **Small commits, clear messages.** One logical change per commit. CI must be green before merging to `main`.
