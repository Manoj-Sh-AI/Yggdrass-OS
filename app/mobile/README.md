# Yggdras mobile (Expo)

Native Android client over the existing application APIs. Local use only; no
hosting or changes to Lia's memory engine are required.

## What is here

- Native Today, task board/editor, month calendar/editor, saved Chat and Settings.
- Task completion, progress, reopen and explicit focus handoff. Goals remain fixed;
  inspecting a task does not start its timer.
- Saved chat history, attachments, conversation actions, agent/model choices and
  existing application review decisions. Held messages are never replayed automatically.
- Notes and Graph reuse the existing editor/viewer in an authenticated WebView.
  Owner-approved phone access matches desktop, with sensitive details behind Show.
  Restricted runtimes still exclude sensitive notes and incident graph edges.
- Revocable, hashed bearer sessions stored in device SecureStore. The password is
  discarded after sign-in. Database, Brain Basic Auth and provider keys stay server-side.

## Calls and advanced controls (v0.3)

- More → Calls: outgoing/incoming UI, mute, audio route, end, call history,
  versioned check-in preferences and explicit proposed-change decisions.
- Calendar start/end and routine check-in preferences default on, with quiet
  hours 22:00–08:00 Europe/Berlin. Live activation remains **off**.
- LiveKit native media and Firebase data-push integration are implemented. Android
  CallStyle/full-screen notifications remain subject to OS permissions and DND.
  No microphone or notification request occurs just from opening the app.
- Settings → Goals / Routines: author and edit existing planning records; Tasks
  supports exact deadlines; More → Background jobs separates unattended elapsed
  time from the single human focus timer.
- See [setup and verification](../../planning/mobile-calls-verification.md) and
  [call contract](../../requirements/contracts/calls-v1.md).

## Ringtone

On Android, calls ring with the phone's own ringtone (the `yggdras-calls-v3` channel;
channel sounds cannot change after creation, so the older `yggdras-calls` and
`yggdras-calls-v2` channels are deleted). Pick any sound for it in Android Settings →
Notifications → Yggdras → "Calls from Yggdras". The push notification is insistent, so
it rings until the call is answered, declined, answered on another device or expires
after 45 s. With the app open and no push, the app plays the phone ringtone at the ring
volume, and stays silent in silent/vibrate mode or Do Not Disturb. The channel never
bypasses Do Not Disturb. The desktop still uses the original chime
(`../web/public/sounds/`).

## Phone ringing with the desktop app closed (Firebase setup)

The laptop must be on and awake, with the application running: it holds the
scheduler, the call service and the voice worker. The push carries only a call id,
state and expiry; never note content.

1. In the [Firebase console](https://console.firebase.google.com/) create a project
   (Analytics off). Add an **Android app** with package name `app.yggdras.mobile`.
2. Download its `google-services.json` and save it as `app/mobile/google-services.json`
   (git-ignored; never commit it).
3. Project settings → Service accounts → **Generate new private key**. Save the JSON
   file outside the repo, e.g. `C:\Users\<you>\.yggdras\firebase-service-account.json`.
4. In the backend `.env` that `runtime.json`'s `brain_env` points to, add:

       FIREBASE_PROJECT_ID=<the project id, e.g. yggdras-12345>
       FIREBASE_SERVICE_ACCOUNT_FILE=C:\Users\<you>\.yggdras\firebase-service-account.json

   The backend needs the voice extra (`firebase-admin`) installed: `uv sync --extra voice`
   in `app/api`. Restart the local application; Calls then reports `push_ready`.
5. Rebuild and install the APK (the build only includes Firebase when
   `google-services.json` exists):

       ../api/.venv/Scripts/python.exe scripts/android-tools.py expo prebuild --platform android --no-install
       ../api/.venv/Scripts/python.exe scripts/android-tools.py build
       ../api/.venv/Scripts/python.exe scripts/android-tools.py adb install -r android/app/build/outputs/apk/release/app-release.apk

6. On the phone: Settings → **Enable daily reminders** and **Send a test reminder**.
   This is separate from Calls. The server must report Firebase delivery as ready,
   and the test should visibly arrive on this phone before scheduling reminders.
   The test contains no private note or task text.
7. For incoming voice calls: More → Calls → **Enable incoming calls** (allow notifications), then
   **Android call display settings** → allow full-screen notifications (Android 14+).
   Also set the app's battery use to *Unrestricted* so a high-priority push wakes it.

The phone rings only while its sign-in is valid; More → Calls shows until when.

## Boundaries

The Android Firebase client file alone does not authorize server sends. A valid
server service account, a current phone build, phone notification permission and
an actual test delivery are required. LiveKit voice and locked-phone ringing are
**not certified** by silent simulations. The laptop
must stay awake for local APIs and workers. Process-loss recovery ends the old
call before a fresh call; ordinary transient reconnect uses the SDK.

Sensitive-content provenance across historical AI chat answers is not certified;
Notes/Graph access and voice context filtering are enforced separately.
No iPhone build, store signing, remote hosting or closed-laptop connectivity.

## Build and verify on Windows

From this folder, install dependencies with `npm ci`, then run `npm run typecheck`
and `npm test`. The project-local tool helper downloads publisher-verified Java
and Android tools into ignored `.cache`; it uses a short drive alias for native
Windows path limits. It does not install tools machine-wide.

    ../api/.venv/Scripts/python.exe scripts/android-tools.py setup
    ../api/.venv/Scripts/python.exe scripts/android-tools.py expo prebuild --platform android --no-install
    ../api/.venv/Scripts/python.exe scripts/android-tools.py build

The release APK is generated under `android/app/build/outputs/apk/release/`.
It is signed with the owner's own upload key in `local-data/android-signing`
(git-ignored), created once with:

    ../api/.venv/Scripts/python.exe scripts/android-tools.py android-key

A release build stops if that key is missing, and the release tool refuses an
APK signed with the public debug key. Back the folder up privately: without it
the next APK cannot install over the current one.

Install on a USB-debugging device:

    ../api/.venv/Scripts/python.exe scripts/android-tools.py adb install -r android/app/build/outputs/apk/release/app-release.apk

The app connects to the hosted application over HTTPS. Its address is set in one
place, `app.config.ts` (`serverOrigin`), and can be overridden at build time with
`YGGDRAS_SERVER_ORIGIN=https://...` before `expo prebuild` and `build`. Release
builds allow HTTPS only.

Developer option (laptop over USB): build with `YGGDRAS_DEV_USB=1` (allows cleartext
to `127.0.0.1` only), run `adb reverse tcp:3000 tcp:3000`, and sign in at
`http://127.0.0.1:3000`.

Device smoke tests use `../api/scripts/mobile_device_fixture.py` and port 3300,
with invented data, a disposable PostgreSQL database and zero paid model calls.
Never use personal Brain notes as test fixtures. See
`../../planning/android-mobile-verification.md` for actual verification and gaps.

## Notes/Graph parity patch

Android 0.3.1 follows the approved owner catalogue setting and refreshes embedded
views when returning to them. See [parity verification](../../planning/mobile-note-parity.md)
for the live 82-note / 190-connection comparison and the revised privacy policy.

## Android 0.3.2 calls and updates

This build includes the project's Firebase Android configuration when
`google-services.json` is present. Enable incoming calls in More → Calls after
installation and grant the Android permissions shown there.

Settings includes signed screen-update checks and an Android-package download
when native changes require a new installation. See the [Railway update and
release guide](../../planning/mobile-updates.md) for publishing commands.
The first installation of this build is required before screen updates work.

On Windows, the Android helper keeps Gradle's reproducible cache in the user's
local temporary directory. This avoids OneDrive cache-move locks and Windows
native-tool path limits; the SDK and Java installation remain project-local.
