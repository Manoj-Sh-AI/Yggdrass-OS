# Review of Claude's agent-layer handoff — 16 November 2026

Reviewed local commits through `0bbb913`, including the skill registry,
orchestration, HTTP routes, chat additions, notifications, calls and connector
scaffold. The pasted handoff was treated as a description to verify, not as an
instruction to merge, deploy or change credentials. No implementation fixes,
live note mutations or paid model requests were made during this review.

Assessment: useful implementation groundwork, but the claim that all seven phases
are built is stronger than the actual integration. Passing component tests do not
establish an end-to-end working agent system. Resolve the P1 findings before
treating the new path as a replacement for the existing chat/Temporal path.

## Findings

### 1. P1 — Task and calendar specialists cannot read through the new host

`app/api/src/yggdress_app/orchestration.py:233` dispatches the existing specialists
with `Specialist.steps`. Their `read_current` tool yields a `read` effect. The host
supplied by the new HTTP pipeline implements `read` by raising
`ToolLocked("reads go through gated tools")` in `orchestration_host.py`.

The single-action path is also incomplete: `orchestrator_api.py:216` registers
only `search_brain`; `read_tasks` and `read_calendar` have no handlers even after
a skill unlocks them. That error can be returned as a tool result, followed by a
normal-looking model answer despite no application records having been read.

Reproduced without paid calls: a multi-step task lookup raised exactly the
`ToolLocked` error above. A scripted single lookup finished with no tools run.
Connect bounded application reads and real proposal inspection to the host, and
test both tasks and calendar through the HTTP pipeline against synthetic records.

### 2. P1 — The new Lia adapter bypasses the existing Lia service

`orchestrator_api.py:219` passes `_Lia(self.notes)` instead of the existing
`agent_lia.ExistingLia` integration. `_Lia.ask` at line 352 performs full-text
search and returns note titles. It does not read note contents, invoke Lia's
retrieval/playbooks or answer the requested knowledge question.

Reproduced: asking for a date with a synthetic matching note returned only
`Notes that match: Synthetic note`. Reuse the established service boundary;
do not reimplement Lia's knowledge behavior in this adapter.

### 3. P1 — Brain approval cards do not bind approval to the reviewed revision

`orchestrator_api.py:245` previews replacements/removals without capturing a note
version. `execute` at lines 276–288 also sends additions and confirmed changes
without a version. The existing Brain HTTP contract accepts an optional version;
omitting it uses the current snapshot rather than rejecting a change since review.

Consequently another edit can change the note or its relationships after the card
is displayed, while the card still confirms against newer data. Exact old-line
matching does not establish that the surrounding reviewed note is unchanged.
Capture the server revision in the preview and supply that revision on confirm,
following the existing Notes proxy's stale-edit protection. Exercise a real
synthetic stale revision and verify 409 with no mutation.

### 4. P1 — The new chat is a separate, unsaved conversation

`app/web/src/app/(workspace)/chat/page.tsx:8` mounts both `YggdrasPanel` and the
existing `ChatPage`. The new panel at `yggdras-panel.tsx:11` keeps its messages only
in React state and calls `/yggdras/requests`, which does not save chat messages or
associate them with a conversation. Its messages disappear on navigation/reload
and do not belong to the existing conversation search, export, attachments, agent
selection or model selection. A run log is not equivalent to saved chat history.

Integrate the new request/approval behavior into the existing saved conversation
flow rather than shipping a second composer with separate state.

### 5. P1 — The new request path bypasses Temporal execution and cancellation

`orchestrator_api.py:380` starts a daemon thread and drives the pipeline in that
process. It does not submit an existing durable agent execution. The Temporal
workflow still calls the older `Yggdras.steps` path, and its activity adapter does
not implement the new `tool`, `propose`, `recall` and `record` effects.

A process restart loses this request and its cards; only completed runs are
logged. The UI's Stop button aborts the response connection, but does not cancel
the daemon thread or its subsequent provider calls. The report acknowledges part
of this gap, but it remains unfinished work in the requested Temporal integration.
Wire the new stages to durable execution and real cancellation before replacing
the existing execution path. Preserve the agreed in-memory preview expiry rather
than silently persisting previews. Verify restart/resume and Stop with scripted
models.

### 6. P1 — Voice delivery needs implementation in addition to credentials

`IncomingCall` in `app/web/src/components/incoming-call.tsx:82` receives room
credentials and updates a status label. No client connects to a LiveKit room or
publishes/subscribes to audio; no voice agent worker is connected. The mobile
scaffold similarly sets a Connected label without joining audio.

`voice.py:92` always raises `PushNotConfigured`, even if Firebase configuration
exists. `Yggdrass` defaults to `SimulatedPusher` and has no configuration branch
selecting a functioning live pusher. Adding keys alone cannot activate Android
delivery or a live conversation.

Additionally `due_rings` at `orchestrator_api.py:566` is only called by tests:
there is no application scheduler/worker invoking it. Scheduled calls will stay
pending, and missed calls are not expired automatically. The browser has no
45-second local expiry or missed-call event, so an unanswered ring can remain
visible/audible indefinitely. The scheduler also commits schedules as rung before
creating their calls, leaving a loss window on interruption.

Keep these features explicitly marked as scaffold/simulation until the audio,
delivery and durable schedule execution paths exist and are tested.

### 7. P2 — Card expiry is enforced on listing, not on approval

`Cards.waiting` deletes old cards, but `Cards.take` at
`orchestrator_api.py:103` does not check their age. Reproduced: an approval card
dated two hours earlier was accepted by `take` if the list endpoint had not first
pruned it. Check TTL atomically when taking a card, and assert that an expired
approval cannot perform an action.

### 8. P2 — Some skill, model and cost tracking claims are not implemented

- On the single-action path, loading a skill opens its tools, but the model is
  only given the skill name and unlocked domains (`orchestration.py:302`), not the
  loaded instructions. Loading the file does not mean its instructions influence
  the next model call.
- Task/calendar dispatch ignores the plan step's selected model and skills.
  Those specialist calls use the model's default instead. The plan's logged
  model is therefore not necessarily the one used.
- Helper and specialist model usage is not added to `Outcome.usage`; the total
  stored cost misses those calls. The pipeline's `budget` argument is also not
  passed through to them.
- Earlier step results are collected only for the final answer; a later helper
  receives its original planned task without those results. A gather-then-act
  plan therefore cannot reliably use what the preceding step discovered.

Verify actual model selections, loaded instruction text, shared budgets, usage
and handoff context at the adapter boundary with scripted model recordings.

### 9. P2 — One approval test has an assertion that always passes

`app/api/tests/test_yggdras_api.py:106` asserts a response status `== 404 or True`.
That expression cannot fail. It does not verify the claimed repeat-approval
protection. Assert the actual expected status (currently 409) and that the second
request makes no additional Brain write.

## Verification performed

- Skill backbone, orchestration, HTTP API and connector tests: **29 passed**.
- Frontend Yggdras stream parsing tests: **2 passed**.
- Frontend typecheck: **passed**.
- Additional synthetic checks reproduced task-read failure, missing real Lia
  retrieval and approval past TTL. No personal records were used.
- Reviewed Brain's existing optional-version contract and the established Notes
  proxy's versioned confirm implementation; no Brain code was changed.

These are focused reruns, not independent confirmation of the handoff's full
217-backend/121-frontend totals, desktop compilation, mobile operation, PR remote
state or the graph change in the separate PR. No paid provider compatibility,
actual voice delivery or physical-phone behavior was exercised.

## Other handoff corrections

The single-database layout is intentional and owner-authorized on 16 November.
It preserves `app`/`brain` schemas and restricted roles; it is not a newly
discovered contradiction requiring a return to two databases. Cloud deployment
of either schema remains a separate step.

The installed runtime loads the existing agent credentials through its private
configuration adapter, while the new HTTP routes independently read the process
environment. The new path should reuse that configuration instead of requiring
a duplicate secret setup. Model availability and pricing were not verified by a
paid request during this review.

The report correctly discloses that token streaming, MCP connections, sensitive
note filtering, live voice and mobile parity are incomplete. In particular,
`mcp_lister` remains a stub even if the MCP package is installed; it still raises
an error and there is no live connector tool executor. These are implementation
dependencies, not only missing environment values.

No merge, deployment, service restart, schema migration or implementation change
was performed as part of this review. Existing uncommitted database-consolidation
work was preserved.
