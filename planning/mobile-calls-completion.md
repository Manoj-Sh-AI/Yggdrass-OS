# Android calls, push and advanced controls

Authorized 17 November 2026. Owner decisions: LiveKit/Firebase are not configured;
finish production integration code and zero-cost simulations, leave live activation
off. No paid Claude/speech tests. Calendar start/end and routine check-ins enabled
as a preference, quiet hours 22:00–08:00 Europe/Berlin. No iPhone or deployment.

## Delivery sequence

1. Durable application-only call contract: authenticated commands, retry receipts,
   first-answer arbitration, identity-bound room access, disconnect/end/expiry,
   history, app-only summaries, durable event recovery and safe push outbox.
2. LiveKit transport integration: per-call room credentials, explicit worker
   dispatch and heartbeat, actual connection/microphone state, mute/speaker/end,
   errors and reconnection. No connected label before media and agent presence.
3. Android push: permission requested only by an explicit control; device/token
   registration, rotation and revocation; generic notification text, expiring
   deduped calls, action handling and authenticated state reconciliation. Never
   put credentials/note content in push payloads. Respect OS/DND restrictions.
4. Check-ins: application preferences, local timezone/quiet hours, source-version
   keys for calendar starts/ends and routines; cancellation/update reconciliation,
   one-off/snooze, transactional delivery claims, no expired-call replay. Integrate
   the existing Temporal execution path; local loop only supplies durable ticks.
5. Native controls: goal/routine authoring, routine activation, precise task
   deadlines, focus handoff and independent background-job inspection. Use
   existing versioned command APIs; keep goals fixed during task execution.
6. Verify permission denial, missing keys, expired sessions, duplicated/stale
   pushes, simultaneous answers, quiet hours/DST, restart, transport failure,
   token rotation, source changes and UI recovery. Synthetic SQL/Brain fixtures
   only. Build/typecheck/tests and phone inspection if still available.

## Invariants and intentional defaults

- Reuse app call tables and add app-only migrations; never query Brain tables.
- Reuse the current Yggdras role; no second general orchestrator or Lia engine.
- Audio is not recorded. Summary goes to application storage only. No automatic
  Brain writes. Voice tools cannot retrieve sensitive/private Brain content.
- Incoming notification text is generic. A notification/action never proves a
  call is current; recheck authentication/state/expiry before answering.
- Live activation requires explicit server mode + complete configuration and an
  available worker. Missing configuration produces an honest unavailable state,
  not a simulated live success. Simulation is explicitly labeled and silent.
- Already saved messages/notes are never replayed as new agent requests.
- Laptop must be awake for local APIs/worker/Temporal. Firebase cannot make a
  sleeping local backend available. Force-stopped Android apps need reopening.
- No resets, new hosting, public secrets, paid test calls, or changes to unrelated
  consolidation work. Stage/restore-verify application migrations before use.

## Research

- https://docs.livekit.io/transport/sdk-platforms/expo/
- https://docs.livekit.io/agents/logic/sessions/
- https://docs.livekit.io/agents/start/voice-ai/
- https://firebase.google.com/docs/cloud-messaging/android/receive-messages
- https://firebase.google.com/docs/cloud-messaging/android-message-priority
- https://docs.expo.dev/versions/latest/sdk/notifications/
- https://docs.expo.dev/push-notifications/what-you-need-to-know/

## Final report requirements

Record exact automated/device results, installer location, migration verification,
zero paid spend and owner setup steps. Separate implemented/simulated behavior
from unverified live delivery. Never report live activation or closed-phone calls
as verified without the missing services and physical tests.

## Completion record

Source, silent simulations, native production-test APK and the installed local
backend upgrade are complete. Exact results and activation instructions are in
[verification](mobile-calls-verification.md). No live accounts, ringing or paid
calls were activated. Android v0.3 is installed on the A16; silent incoming/outgoing calls, native
goal/routine saves and the normal signed-out handback were physically verified.
Real media and push certification await the explicitly deferred service setup.
