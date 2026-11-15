# Local foundations implementation sequence

Subsequent approved work: [the local agent layer is delivered and verified](agent-layer-verification.md).
This sequence records the earlier receiving-side scope; its original boundaries
do not negate the owner's later agent/orchestration authorization.

2026-11-15. The owner approved all six receiving-side areas plus a Chat page. This is application engineering; specialist agents, Yggdras orchestration, chat model responses, deployment and Lia's memory engine remain outside scope.

## Delivery order

1. Record requirements and boundaries; retain current working Notes bridge and Calendar design.
2. Implement explicit atomic focus handoff and independently authenticated background-state intake. Preserve goals, one human timer, timestamps, versions, and retries.
3. Establish persistent local application runtime/backup behavior. Stage additive migrations and test restarts independently of the process-managed preview.
4. Build authenticated interpretation intake, source/target bindings, durable processing receipts and quiet conflict review against synthetic producer fixtures. No semantic extraction or automatic remote callback claims.
5. Extend time representations/validation and Notes lifecycle adapter capabilities; preserve unsupported interpretations and unavailable upstream operations truthfully.
6. Expose bounded operational graph neighborhoods and integrate an optional application graph layer.
7. Build persistent Chat conversations/messages/attachments and responsive UI below Graph; add future response intake, with no connected provider and no automatic message replay.
8. Exercise cross-feature, restart, retry, security and responsive workflows; inspect screenshots; preserve local records and activate only verified builds.
9. After those foundations pass, build and verify the Windows desktop application for the owner's laptop. Reuse the shared backend and persistent local data; manage startup/shutdown and connection recovery. No separate task/Brain store, cloud deployment or native mobile implementation.

## Decisions already settled

Chat sends save to history while disconnected and require explicit resend later. Text and file/image attachments are included; voice is deferred. Desktop/tablet/phone compatibility means responsive web and shared APIs; network/device setup is deferred. No additional approval is required for routine implementation choices within these boundaries.

## Existing baseline

Application migrations 001–008 are now active locally. The current frontend serves `.next-connected-polish`; never rebuild that directory in place. Package verification into another dedicated `.next-*` directory. Notes and the existing Brain graph remain behind backend-only authenticated proxies. Private service configuration, PostgreSQL and desktop profile live under the current user's LocalAppData/Yggdras. Test/rollout evidence remains ignored under `app/api/runtime`.

## Implementation checkpoint

- Focus handoff: backend command and explicit Today/task controls implemented. Four PostgreSQL tests passed, including no-clock selection, same-instant transfer, preserved objectives/deadlines, stale/dependency refusal and competing switches. The browser handoff/inspection scenario passed.
- Chat: migration 005, conversation/message/file APIs, authenticated private response receiver and responsive page/navigation are active. Seven backend tests passed, including idempotent upload recovery. No provider is connected; held messages require explicit resend. Markdown uses react-markdown/remark-gfm with raw HTML skipped and external Markdown images not automatically fetched. The archive/filter race was corrected and browser-tested.
- Time precision: migration 006 adds all-day/date ranges, review dates and availability, source links and reverse context. Calendar can create/edit/remove these; Notes can create and open linked date/availability items; Today shows actual all-day commitments. No invented midnight appointment, focus minutes or scheduling algorithm. Five API tests and the calendar browser flow passed.
- Desktop: the owner's later request brought the laptop host into this checkpoint. The Windows/WebView2 app is compiled, verified, open and available through desktop and Start menu shortcuts. Native rendering, single instance, service reuse, full record equality across stop/start and sign-in persistence passed. This is a workspace-linked personal build, not a standalone installer. See `planning/windows-desktop-verification.md`.
- Persistent runtime: full app-only backup restored and verified before import; source business records and final retry/auth records preserved. Explicit migrations only; private SCRAM PostgreSQL outside OneDrive; least-privilege runtime role; no normal-startup migrations or seeding. Real Notes and Brain graph read checks both returned 82 nodes; no Brain mutations.
- Verification: production build and 119 frontend tests passed; 20 affected browser scenarios passed. API regression covered 120 passing tests across runs, with two optional Brain integration tests skipped. One old schema-allowlist expectation was updated for the approved app tables and passed its rerun.
- The initial desktop checkpoint left four receiving areas unfinished. These have now been implemented and activated: separated Lia handoff and agent-update contracts, source lifecycle/target binding and quiet conflict review, bounded Work connections graph, background-run receipts/cancellation UI, and typed uncertain-time handling. All six local receiving areas are ready for future producers; the handoff alone does not change work. Details/evidence are in `planning/connected-foundations-delivery.md` and `requirements/contracts/connected-receivers-v1.md`.
- The owner additionally requested Chat agent/model selectors. Migration 008 stores the conversation's selected destination and snapshots it on messages/requests/replies. Catalog metadata is backend-owned; unknown/incompatible choices are rejected. Yggdras/Lia are disconnected choices locally, with Provider default as the model placeholder until models are registered. No live model calls or automatic replay were added.
- Future work remains the actual Lia triggering/producer integration, Yggdras routing, specialist agents, model provider execution and unavailable upstream whole-note Brain archive/restore writes. These are not quietly implemented as part of application plumbing. Voice, home-Wi-Fi setup, native mobile, hosting, standalone installer/signing/automatic native updates remain deferred.
- Dependency audit after Markdown installation reports existing advisories in Vitest/tinypool/mocker and sharp (test/image tooling), with major-version fixes offered. No new Markdown advisory reported. A controlled tooling upgrade remains tracked separately; the desktop host adds no Node web-test server or native bridge.
