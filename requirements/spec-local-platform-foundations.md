# Local platform foundations and Chat

Owner authorization, 2026-11-15. Build and iterate on all receiving-side foundations locally before specialist agents or orchestration. No deployment, memory-engine redesign, or automatic Brain writes.

## Confirmed product choices

- Before a provider exists, sending a chat message saves it in conversation history. Never replay it automatically when a provider connects; a later explicit resend is required.
- Chat includes text, file/image attachments, conversation history, search, rename, delete and export. Voice is deferred. Do not display simulated AI answers or imply Yggdras is connected.
- Add Chat immediately below Graph in shared navigation. Preserve the quiet nature/glass design and accessible keyboard/touch behavior.
- Cross-device scope is responsive web interfaces and shared backend APIs. Home-Wi-Fi access, device certificates, native clients and deployment are deferred.

Later owner instruction in this session: after the local foundations and Chat have been built and tested, build a desktop application for the owner's Windows laptop. It must reuse the shared application data/API and manage its required local services rather than depend on a manually started browser preview. Native mobile work remains deferred until a later collaboration. This supersedes the desktop-client deferral above; cloud deployment and mobile implementation remain outside this delivery.

## Six receiving-side areas

1. **Interpreted note changes:** authenticated, versioned application intake for structured outputs from a future Lia adapter. Stable source/change/commitment identity, original context reference, clear/uncertain disposition, deduplication, durable status and conflict recovery. Use synthetic producer fixtures; do not implement a replacement date/meaning extractor.
2. **Notes lifecycle and synchronization:** approved Brain API adapters and explicit capability reporting; source-reference lifecycle updates, archive/restore handling, safe link reconciliation, preserved work/history. Unsupported upstream operations stay visibly unavailable rather than pretending to archive Brain data.
3. **Connected work graph:** bounded read-only operational neighborhoods and an opt-in application layer with typed source/task/event/goal edges and status. Preserve Lia's semantic graph and curated relationships.
4. **Focus/background execution:** explicit Focus atomically transfers the single running human timer; inspecting a task does not. Selecting with no timer running starts none. Background-run receipt/status/elapsed clocks remain independent of human focus; no agent runner.
5. **Time meaning and constraints:** preserve dates versus instants, all-day intervals, precision, timezones, uncertainty, historical context, availability and relative references. Validate supported application actions; unsupported/coarse meanings remain reviewable rather than being coerced into fabricated times.
6. **Reliable local use and responsive clients:** persistent application-owned storage, private configuration, verified backup/restart behavior, common APIs, bounded queries, accessible desktop/tablet/phone layouts. No cloud provisioning or publication.

## Chat receiving boundary

Conversation and message identity, ordering, versions, attachment integrity, retry receipts, draft preservation and bounded pagination belong to application storage. Future response intake must be authenticated independently of browser message submission, preserve parent-message/request identity, validate sequence/state, and support partial/final/error/cancel outcomes without forged or duplicated answers. No provider, model key, agent, orchestration, or automatic replay is introduced now.

Attachments are application data, never executable tools or automatically ingested Brain memories. Use authenticated access, explicit size/type limits, safe download behavior and backup coverage. Context references must not copy authoritative Brain note bodies into relationship tables.

## Verification

Use disposable PostgreSQL and synthetic Brain/provider outputs for mutations. Verify retries, restart persistence, stale source/target conflicts, archive/restore/removal, cancellation, no-loop behavior, timer handoff invariants, graph bounds, temporal precision/DST, attachment access/limits, chat edit/delete/export/history, keyboard focus and responsive layouts. Preserve and verify real local application records before activation. Real Brain checks remain read-only.
