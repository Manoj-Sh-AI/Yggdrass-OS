# Android mobile verification

Historical v0.2 record. Later implementation and owner-approved phone access are
recorded in [calls verification](mobile-calls-verification.md) and
[Notes/Graph parity](mobile-note-parity.md). The latter supersedes the phone-only
sensitive-note exclusion; voice exclusions remain.

Work branch: `codex/android-completion`. Local implementation; no cloud deployment,
Brain engine changes, production note test writes or paid model test calls.

## Verified

- Android release test package compiled successfully (`assembleRelease`, ARM64).
  Expo development signing key; not a Play Store release.
- APK: `app/mobile/dist/Yggdras-android.apk`, 36,088,619 bytes.
  SHA256: `a2a18dc40c57e8dd84b70588e040c35bc872139118bf21a5d2d7c61ec535770a`.
- Native TypeScript check passed; five component/API/date test suites, 18 tests passed.
- Backend mobile/auth/Notes/Graph/application regressions: 62 tests passed. Scoped
  Ruff check passed. One existing Starlette/httpx deprecation warning remains.
- Next.js production build `.next-phone-ready` passed. Five proxy/session tests
  passed, including Android WebView form POST and invalid-origin rejection.
- Packaged-frontend integration against a disposable PostgreSQL database and
  invented Brain HTTP fixture passed: native sign-in, retry-safe task save,
  completion/reopen with fixed goal, calendar save, saved/held chat, note
  preview-confirm-refresh, HttpOnly WebView session, mobile editor layout, and
  sensitive Notes/Graph exclusion. No real Brain writes or model calls.
- Existing laptop services started successfully with `.next-phone-ready`; desktop
  verification reached the real sign-in page. Only the build selection changed;
  database, password and provider configuration were preserved. Previous runtime
  selection retained privately for rollback.

## Physical device status

Samsung Galaxy A16 physical verification completed with invented data:

- Installed version 0.2.0; Android's package installer returned `Success`.
- Native sign-in, Today, task board/detail, completion/reopening and preservation
  of the original goal worked. Starting focus displayed an explicit confirmation.
- Calendar month/day selection showed the saved sample item. Physical inspection
  identified wrapping month controls; compact labeled arrow controls fixed this.
  The Calendar tests passed again (3 tests), the updated package rebuilt and
  installed, and the corrected screen was inspected on the phone.
- Saved chat displayed its existing sample conversation and accepted another
  invented message. Session and saved message survived force-stop/relaunch.
- Notes opened the existing editor with sample content. Graph opened the owner's
  viewer with the safe sample node. The sensitive sample node was absent.
- Settings displayed the verified fixture origin. The sample account was signed
  out through the normal UI, and the actual local address selected for the owner.
- USB reverse ports 3000/3300 were configured. App-only screenshots were inspected;
  no personal note was edited or captured during these checks.

At the owner's explicit request, the local application password was reset using
non-echoing input. Only its scrypt hash was stored in the private runtime settings.
The service restarted successfully; live sign-in/session/logout verified the new
password. Existing sessions are rejected by the existing password-fingerprint
checks. Other runtime settings and application/Brain records were not changed.
No password or session token is included in this report.

## Remaining limits

- LiveKit/Firebase keys and `google-services.json` are absent. Live microphone
  transport, incoming calls and locked-phone push are not implemented/verified.
- Native goal/routine authoring and precise timed task-deadline editing do not
  yet match all web controls. Routine viewing/preparation is available.
- Sensitive Notes/Graph exclusion is tested. Historical AI chat does not have
  complete source provenance, so blanket sensitive-data exclusion across chat
  and derived application records is not certified.
- USB development needs this laptop awake, app services running, and ADB reverse
  active. No remote connectivity, iPhone install or store release is claimed.
- The existing broader orchestration review findings remain outside this mobile
  integration change; the duplicate unsaved chat panel is not used by mobile.

## Change groups

- `app/mobile`: native screens, API/session layer, timezone/date logic, shared
  controls, authenticated embedded views, tests, Expo configuration and local
  Android build helper.
- `app/api`: mobile bearer/session bridge and server-side Notes/Graph privacy
  policy, corresponding regression tests and isolated device fixtures.
- `app/web`: native-session bridge, mobile layout, sensitive desktop reveal and
  existing saved-chat entry point; production/proxy verification.

Unrelated database-consolidation changes predated this task and were preserved.
