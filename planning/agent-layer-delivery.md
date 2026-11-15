# Agent integration and orchestration delivery

**Delivered locally:** see [final verification and remaining boundaries](agent-layer-verification.md).
The active build is `.next-agents-ready`, with application migration 009 applied.

Authorized 2026-11-15. Continue through specialist integrations, then orchestration,
without requiring another implementation prompt. No paid verification calls: the
owner will test the live connection. Claude first, credentials server-side.

## Sequence and acceptance gates

1. Inventory the existing contracts and research primary implementation sources.
2. Implement bounded Task and Calendar specialist tools over canonical application
   records. Validate proposals, preserve goals and versions, and test independently.
3. Adapt the existing Lia service without replacing its retrieval, memory, maps,
   checks or writing algorithms. Persist note-save observations separately.
4. Add durable execution, private Claude transport, explicit model registration,
   saved Chat destination integration and user review for proposed Chat writes.
5. Add Yggdras routing/planning over the tested specialists. Temporary helpers have
   a separate context, narrow tools, depth/call/output/time limits and a recorded
   parent. No unrestricted shell, arbitrary SQL or recursive agent creation.
6. Exercise failure, cancellation, concurrency, stale approvals and restart paths
   in isolated databases with synthetic model responses; build and verify the UI.
7. Activate only a verified local candidate using the existing backed-up upgrade
   process. Do not replay held Chat messages or infer work from historical notes.

## Boundaries

Brain schema and Lia's existing engine remain untouched. Application execution
history is not Brain memory. No deployment, native mobile, voice, notification
delivery, energy thresholds, automatic focus switching or invented scheduling.
Clear note-derived updates retain existing workflow review rules. Direct Chat
mutations require an exact version-bound review; answering and reading do not.

An absent credential, unavailable Lia capability or unsupported operation must be
reported honestly, not replaced with a simulated successful action. Live model
quality and paid provider compatibility remain owner-verified until real use.

## Research decisions

- Anthropic [effective agents](https://www.anthropic.com/engineering/building-effective-agents):
  start with explicit, composable workflows and add autonomy where needed.
- Anthropic [tool design](https://www.anthropic.com/engineering/writing-tools-for-agents):
  bounded, purposeful tools and evaluations on realistic tasks.
- Anthropic [tool use](https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview):
  the model proposes client-tool calls; application code controls execution.
- LangGraph [persistence](https://docs.langchain.com/oss/python/langgraph/persistence):
  durable execution state and domain memory are separate concerns. Reuse the
  existing PostgreSQL/receipt foundation rather than adding a second state store.

Progress and remaining external dependencies are recorded below as verified.

## Current implementation

The application specialist tools, bounded helpers, on-demand skill allowlist,
private Claude transport, existing-Lia subprocess adapter, durable worker,
pre-save write intents/recovery, source-handoff processing, owner review API and
Chat integration are implemented. The first specialist gate passed before
orchestration was added. Lia's actual skills and row-backed library were loaded
read-only, with no inference call or engine edits.

The first 16 agent/API cases and all 119 frontend tests passed. The full API run
had 158 passing cases, two optional live-Brain cases skipped, and two failures:
an exact schema allowlist needed the new application tables, and a synthetic note
fixture had a duplicate Facts heading. Both were corrected. Final focused and
browser verification subsequently passed, as recorded in the final report. The
fresh `.next-agents-release` build passed after Windows denied a directory in
`.next-agents`; the final verified and activated candidate is `.next-agents-ready`.

See [the executable integration contract](../requirements/contracts/application-agents-v1.md)
for exact boundaries, including read-only Lia integration and unverified live
model quality. Backend connection setup is active; paid inference remains
owner-verified by explicit choice.
