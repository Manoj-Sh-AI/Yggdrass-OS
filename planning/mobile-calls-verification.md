# Android calls and controls — 17 November 2026

This records the v0.3.0 call delivery. The current installer is the later
[Android 0.3.1 parity patch](mobile-note-parity.md), which also records the owner’s
revised phone-access policy. Voice privacy and disabled live activation remain.

## Delivered source

- Durable authenticated call API, first-answer arbitration, expiring invitations,
  idempotent commands, call/event history, device revocation and bounded push outbox.
- LiveKit worker using the existing Yggdras role, microphone-only room credentials,
  explicit SDK connection state, private-context filtering, app-only summaries and
  versioned proposals requiring approval. No new Lia/memory implementation.
- Android CallStyle/full-screen notification integration, generic payloads,
  answer/decline reconciliation and foreground microphone service; explicit
  notification/microphone consent and no DND bypass.
- Native call controls/history/preferences, calendar/routine check-ins,
  goal/routine editing, exact task deadlines and separate background-run controls.
- Web/desktop-shell call UI using the same service and real browser media adapter.
- CI now checks native client types/tests and the optional voice SDK adapter.

## Verification

All call checks are **silent simulations or scripted SDK tests**. No paid model,
speech or real LiveKit/Firebase calls; no real Brain test writes. Provider spend: 0.

- Mobile: typecheck and **26 tests / 7 suites passed**.
- Web: production candidate `.next-voice-ready` and **126 tests / 17 files passed**.
- Two isolated browser windows: first answer wins, invitation closes elsewhere,
  end and decline propagate, explicitly simulated status, no microphone request.
- Mobile HTTP integration: task retry/completion/reopen, fixed goal, calendar,
  saved chat without replay, note preview/confirm/refresh, authenticated WebView
  and sensitive Notes/Graph exclusions passed against disposable invented data.
- Python lint/format checks passed across application sources, tests and scripts.
- Android ARM64 release-test package compiled successfully. APK **50,007,254 bytes**;
  SHA256 `ab295dc5a175099673a5337b40f1a328394bb2065e54eb6c10f21d23644324b3`.
  Version 0.3.0 confirmed from the packaged manifest; camera permission is absent.
  Expo development signing key, not a store release key.
- Installer: `app/mobile/dist/Yggdras-android.apk` (ignored build output).

- Backend full suite: **241 passed, 2 skipped** in 10m18s, including the installed
  media SDK with a scripted model. No paid provider access.
- Installed application upgrade: backup restore verified; staged migrations
  preserved original values and Brain fingerprints; migrations 011/012 applied.
  Runtime reports ready at port 3000 on `.next-voice-ready`, 58 application tables,
  call mode `disabled`, zero active calls, and a reachable sign-in page.
- **Android v0.3 installed and physically checked on Samsung A16 (SM-A165F).**
  Authorized USB update completed with `Success`, preserving app data; Android
  package manager confirms version 0.3.0. The app launched successfully.
- On-phone invented-data checks: outgoing simulated start/end and incoming
  simulated Answer/end passed, clearly labeled simulation throughout. No
  microphone/notification permission prompt or paid service was invoked.
- Calls preferences displayed Europe/Berlin, 22:00–08:00, and enabled calendar /
  routine choices. Background-job empty state explicitly distinguishes its clock
  from focus time. A goal and routine were created successfully through the native
  forms against the disposable database.
- Temporary fixture session signed out; app cold-reopened at the normal
  `http://127.0.0.1:3000` sign-in screen with an empty password. USB port 3300
  forwarding removed; disposable fixture stopped. Normal port 3000 forwarding
  remains. Phone permissions, DND and screen-lock settings were not changed.
- Ignored device evidence: `app/mobile/.cache/voice-phone-verification.json`,
  `calls-v03-phone.png`, `call-v03-simulated-phone.png`, `routine-v03-phone.png`.
  These contain invented test records, not personal notes.


## Owner activation later

1. Create LiveKit and Firebase projects. In the existing ignored backend `.env`
   used by the local runtime, set `LIVEKIT_URL`, `LIVEKIT_API_KEY`,
   `LIVEKIT_API_SECRET`, `FIREBASE_PROJECT_ID`, and
   `FIREBASE_SERVICE_ACCOUNT_FILE` (absolute private service-account file path).
   Never put service secrets in Expo config, source control or chat.
2. Register Firebase Android package `app.yggdras.mobile`. Put its client
   `google-services.json` in ignored `app/mobile/google-services.json`, then
   prebuild/rebuild/install the APK. This build intentionally has no Firebase project.
3. Install locked optional backend dependencies with `uv sync --project app/api
   --extra voice` when the runtime is stopped. Set `YGGDRAS_CALLS_MODE=live` in
   that backend environment and restart the existing laptop runtime. It starts
   the named voice worker; voice readiness also requires its recent heartbeat.
   STT/TTS defaults use LiveKit Inference, which requires the corresponding
   LiveKit billing/credits/provider access. Claude uses existing backend keys.
4. In More → Calls, explicitly enable incoming calls. Allow notifications and
   microphone when desired; review Android full-screen-call display settings.
   OS permission, DND, battery restrictions and browser autoplay still apply.
5. Owner tests live media, mute/output/end, permission denial, network reconnect,
   locked-phone answer/decline, multi-device arbitration and quiet hours. No claim
   of live delivery certification is made before these tests.

Check-in preferences default enabled for calendar starts/ends and routines with
quiet hours **22:00–08:00 Europe/Berlin**. They do nothing while mode is disabled.
No overdue burst is replayed after activation. Laptop APIs/worker must remain
awake; Firebase does not make a sleeping computer reachable. Force-stopped Android
apps may require reopening. Phone access away from USB still requires the later
secure device-connection/hosting setup; that was not deployed in this task.

## Intentional limits

Transient media reconnect uses the SDK. After app process loss, end the previous
call and start another instead of silently creating a second transport. Audio is
not recorded; summaries remain application records, with no Brain writes. No
iPhone, native Telecom service or production app-store signing was added.

Dependency audits still report existing Expo/Next development-toolchain
advisories (including high/critical development dependencies). A forced framework
major upgrade was deliberately avoided; do not treat this local test package as
a completed production security review.
