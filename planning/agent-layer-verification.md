# Local agent layer — delivery and verification

This records the original agent-layer release. The subsequent owner-authorized
Temporal execution integration is tracked in
[Temporal execution](temporal-agent-execution.md); it preserves these agent and
Brain boundaries.

2026-11-15. Active local frontend: **`.next-agents-ready`**. Application schema:
**001–009**. Web and the existing Windows host share the same backend and records.
No deployment, new installer, mobile app or memory-engine rewrite was performed.

## Delivered

| Component | Implemented behavior |
|---|---|
| Task Manager | Bounded reads; create/update/progress/complete/reopen proposals; reviewed cancellation of unstarted work; immutable original objective/goal; retained metadata, dependencies and history. |
| Calendar | Bounded interval reads; timed event, date-only range and availability proposals; explicit named timezone for exact new times; cancellation preserves history. |
| Existing Lia integration | Her original skills, row-backed library, retrieval, checks and effort policy are reused through a separate read-only process. Explicit model selection can override the model; default selection preserves her existing policy. No engine source changes. |
| Yggdras | Direct answer or sequential specialist delegation; bounded planning/tool loop; isolated-context, read-only consultation helpers with no recursive delegation or additional permissions. |
| Skills/tools | Three shipped application skills load on demand. Lia retains her own nine playbooks. Tool permissions are enforced by code; no shell, arbitrary SQL, arbitrary paths or unregistered remote connectors. |
| Durable execution | PostgreSQL jobs, claims/leases, call-start/completion metadata, saved answers, proposal decisions and stable receipts. Chat and note review have separate execution lanes, independent of human focus time. |
| Chat | Four destinations and registered Claude model choices; selected destinations survive reload and remain attached to messages/requests. Held messages never replay. Old unapplied proposals are superseded on resend or source-message changes. |
| Review | Exact proposed fields and current values, clear cancellation confirmation, protected versions, accept/dismiss and repeat-safe decisions. Generated proposals do not silently mutate application work. |
| Notes handoff | Prepare body-free save intent → existing Brain API save → revision observation → Lia context → handoff inbox → Task/Calendar interpretations → existing canonical work receiver. Clear supported source updates stay silent; conflicts use existing review. |
| Recovery | Interrupted save intents reconcile through Brain reads; Undo returning to an old content revision remains a new operation. Lost paid-call execution does not silently rerun. Saved response delivery can retry without another model call. |

Application execution history and recent conversation decisions supply operational
context; they are not automatically written into Lia's Brain memory. Today,
Calendar, Tasks and Work connections keep reading the existing canonical tables.

## Verification

- Final production build and TypeScript checks passed in `.next-agents-ready`.
- All **119 frontend tests** passed; Ruff checks and formatting passed for 66 files.
- **46 focused backend cases** passed for agents, source receivers, save/Undo
  recovery, schema separation and upgrade safeguards. Two additional direct-role
  cases passed for Lia and Calendar, alongside a repeated transport check.
- The earlier broad API run passed 158 cases and skipped two optional real-Brain
  mutation cases. Its two failures were corrected: the explicit schema allowlist
  needed the new tables, and a synthetic note fixture had a duplicate heading.
  Focused reruns cover those corrections and the final receiving implementation.
- **20 final browser cases** passed: two new synthetic-agent scenarios, including
  phone layout and held-message protection, plus 18 Notes/Chat/Calendar/Graph/source
  regressions. This includes capture, previews, Undo, stale edits, failures,
  attachments, model selection, focus handoff and private proxy rejection.
- Live upgrade restored and verified an application-only backup, migrated an
  isolated restore, compared every original column value, applied migration 009
  and grants to the exact owned cluster, and started the verified build.
- Authenticated live reads confirmed **82 real notes**, **82 Brain graph nodes**,
  four configured agent destinations, four model choices including the default,
  preserved personal password, blocked private browser routes and no automatic
  replay. There were zero managed agent runs at verification time.
- The actual Windows executable opened **Today** successfully after the update.
  An initial Notes read returned a transient 503 after restart; the subsequent
  full authenticated check passed. No Brain mutations were used for verification.

Evidence is kept privately under `app/api/runtime/agents-*` and the existing
LocalAppData/Yggdras backup directory. Synthetic screenshots contain fictional
data. No remote GitHub CI or hosted deployment is claimed.

## Owner-chosen and engine-owned remaining work

**No paid provider inference was tested.** The owner chose to test the live Claude
connection personally. Synthetic tests establish application behavior, not live
model semantic accuracy, account access, quotas or response quality.

**Lia in Chat is read-only.** Existing Notes editor writes still use the existing
Brain API. The Brain writer continues to use its existing scratch-workspace
implementation; this release does not remove it or invoke it from the new agent
adapter. Brain editing/ingestion through Chat and whole-note archive/restore need
a compatible Claude-owned writer/API interface. That boundary must not be hidden
by a replacement memory engine or a simulated successful write.

Direct application Chat mutations use Review. Note-derived updates retain the
previously agreed clear-versus-uncertain workflow behavior. Source identity remains
the documented application reference/producer assertion with HTTP revision checks;
a native immutable-ID/changefeed contract remains an upstream integration point.

Other model providers, remote MCP accounts/connectors, arbitrary new agent roles,
voice, native mobile, hosting and a standalone signed desktop updater are not
silently enabled. Large or unsupported binary attachments stay saved and report
their processing limit rather than being executed or discarded.

## Main files

- `app/api/migrations/009_application_agents.sql`.
- `app/api/src/yggdress_app/agent_*.py` and three `agent_skills/*/SKILL.md` files.
- `app/api/scripts/lia_application_bridge.py`; existing runtime, application,
  Notes, Chat, receiving cursor and role-grant integration.
- Shared `workflow-review.tsx`, Chat refresh events, Notes dispatch warnings and
  the owner-only frontend proxy allowlist. The notebook/editor design is preserved.
- Agent/direct-role tests, synthetic browser model fixture, `e2e/agents.spec.ts`,
  disposable database grants/reset fixtures and the additional CI browser check.
- [Application contract](../requirements/contracts/application-agents-v1.md),
  [implementation sequence](agent-layer-delivery.md), and
  [tradeoffs](../rationale/decisions/bounded-application-agents.md).

Research used primary [Anthropic workflow guidance](https://www.anthropic.com/engineering/building-effective-agents),
[tool design guidance](https://www.anthropic.com/engineering/writing-tools-for-agents),
[skill disclosure guidance](https://www.anthropic.com/research/equipping-agents-for-the-real-world-with-agent-skills),
and [LangGraph persistence documentation](https://docs.langchain.com/oss/python/langgraph/persistence).
Their patterns informed the design; no agent framework or copied third-party
implementation was added.
