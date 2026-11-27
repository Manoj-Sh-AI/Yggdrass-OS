# Phone dev loop: how changes reach Manoj's phone, and the work log

Living log (Claude keeps it current). Read it first when picking up phone, call or
deploy work. Newest log entries at the bottom.

## Rule (Manoj, 2026-11-27)

Test locally on the phone first; push and merge in batches at the end. Each merge plus
Railway deploy costs ~10 min, so never merge one change at a time just to see it.

## The loop

| Change | How it reaches the phone | Time |
|---|---|---|
| Phone JS (screens: Calendar, Chat, Tasks…) | Dev build + Metro over USB, reload | seconds |
| Phone native (Kotlin, channels, permissions) | Release APK built locally, `adb install -r` | ~12 min |
| Web pages shown in the app (Notes, Graph) | Merge to `main` → Railway web deploy (or run web locally) | ~5–10 min |
| Backend (chat, calls, reminders) | Merge to `main` → Railway backend deploy | ~5–10 min |
| Backend experiments | `railway ssh` into the container, run a probe script | ~1 min |

Over-the-air screen releases (`npm run release:screens -- --publish`) ask for the app
password, which Claude never types: Manoj runs them, or Claude uses the APK/dev build.

## Tools and paths (this PC)

- **adb**: `<worktree>/app/mobile/.cache/android-tools/sdk/platform-tools/adb.exe`
  (junction to the main checkout's tool cache). Phone: Samsung SM-A165F, Android 16.
  Screenshot only when `dumpsys activity activities | grep topResumedActivity` shows
  `app.yggdras.mobile`; never press Back (it can leave the app); relaunch with
  `adb shell monkey -p app.yggdras.mobile -c android.intent.category.LAUNCHER 1`.
  Tab bar taps (1080×2340): Today 140, Tasks 345, Calendar 539, Chat 737, More 933 at y=2097.
- **APK build** (in a worktree with junctions `local-data/android-signing`,
  `app/mobile/.cache/android-tools`, `app/mobile/node_modules`, and a copied
  `app/mobile/google-services.json`):
  `python scripts/android-tools.py expo prebuild --platform android --no-install`, then
  set `networkTimeout=120000` in `android/gradle/wrapper/gradle-wrapper.properties`
  (the 10 s default times out downloading Gradle), then `android-tools.py build`.
  Install: `adb install -r android/app/build/outputs/apk/release/app-release.apk`.
  Only one Gradle build at a time (shared cache).
- **Railway CLI**: use the exe directly, not `railway.cmd` through `cmd //c` (cmd eats
  `|`, `>` and parentheses): `/c/Users/shman/AppData/Roaming/npm/node_modules/@railway/cli/bin/railway.exe`.
  Linked to project `8b20de5a-…`, env `55387f72-…` (services: backend, web, Postgres).
  - Logs: `railway.exe logs --service backend --since 10m` (current deployment only).
  - SSH: `railway.exe ssh --service backend -- "<shell command>"` with `< /dev/null`.
    Upload a script: `echo <base64> | base64 -d > /tmp/x.py; cd /repo/app/api && .venv/bin/python /tmp/x.py`.
  - Variables: print names only; never values (`--json` contains secrets).
- **Production DB, read-only**: `scratchpad prod_read.py` pattern: admin URL from
  `C:\Users\shman\AppData\Local\Yggdras\railway-admin.url` (never printed),
  `SET TRANSACTION READ ONLY`, states and error columns only, never message content.
- **Migrations**: `uv run python -m yggdress_app.migrate_hosted plan|apply --home "C:\Users\shman\AppData\Local\Yggdras"`
  (pass `--home`: this app redirects %LOCALAPPDATA%).

## Development build (seconds per JS change)

Built once in the `fix-loopback` worktree, from the already prebuilt `android/` project:
1. In `android/app/build.gradle`, debug `signingConfig signingConfigs.release`: the dev
   build then installs **over** the release app (same key, same package), keeping the
   sign-in and the WebView's local drafts. Never uninstall to switch builds.
2. Loopback HTTP: the app is HTTPS-only, so Metro (`http://127.0.0.1:8081`) is refused
   ("CLEARTEXT communication … not permitted"). Either prebuild with `YGGDRAS_DEV_USB=1`
   or put the loopback `domain-config` in
   `android/app/src/main/res/xml/yggdras_network_security.xml` (127.0.0.1, localhost).
3. `python <scratchpad>/build_debug.py <worktree>/app/mobile` runs `gradlew assembleDebug`
   with android-tools' environment (~10 min first time, incremental after).
4. `adb install -r android/app/build/outputs/apk/debug/app-debug.apk`,
   `adb reverse tcp:8081 tcp:8081`.
5. Metro in a terminal tab, from the worktree whose JS should run:
   `npx expo start --dev-client --port 8081`.
6. Open: `adb shell am start -a android.intent.action.VIEW -d "yggdras://expo-development-client/?url=http%3A%2F%2F127.0.0.1%3A8081" app.yggdras.mobile`.
Back to a release build at the end: `adb install -r` the release APK (higher or equal
version code, same key).

## Facts learned the hard way

- The hosted API must listen dual-stack: uvicorn's `::` is IPv6-only, and every
  in-container `127.0.0.1` call (chat worker, voice worker) failed silently (#67).
- `clean_environment()` strips all `YGGDRAS_*`, `ANTHROPIC_*`, `BRAIN_*` variables from
  child processes; the voice worker reads its settings from the brain `.env` or needs
  them passed explicitly (#76).
- The phone's WebRTC `audioLevel` is an instant; judge call audio with
  `totalSamplesReceived`/`concealedSamples` or by ear.
- Railway's GitHub deployment status says "failure" while services are fine; trust
  `railway.exe deployment list --service <name>`.
- `/data` in the backend container is not a persistent volume (recreated each deploy).
- Backup verification compares schema statements, not pg_dump order (#69).

## Open items

- FIREBASE_SERVICE_ACCOUNT_JSON: Railway still has FIREBASE_SERVICE_ACCOUNT_FILE = a
  laptop path, so server pushes (reminders, call ringing) cannot work. Waiting for Manoj
  to download a new key to `C:\Users\shman\.yggdras\firebase-service-account.json`;
  then set it from the file via `--set-from-stdin`, delete the FILE variable.
- A spoken call turn fails with `voice turn failed: AgentError` (27 Nov 21:23 UTC). The
  same question run directly in the container works. Debug logging (#73 + #76, with
  `YGGDRAS_VOICE_DEBUG=1` on Railway) will name it on the next call. Turn the switch off
  afterwards.
- Remove the Railway SSH key `yggdras-laptop-claude` when this work is done (Manoj's choice).

## Log

- 2026-11-25/26: chat fixed (#67), call greeting instant (#68), backup check (#69),
  table test contract-safe (#70), reminders push merged (#66, migration 046 applied with
  backup `pre-migrate-20261125-231140.dump`).
- 2026-11-26: Android 0.3.5 installed over USB: Google-style Calendar, phone ringtone (#71).
- 2026-11-27: Notes phone layout (#72, #74), voice debug (#73, #76), no duplicate header
  band (#75). Calls have sound (Manoj heard Yggdras). Railway CLI + SSH set up.
- 2026-11-27: switched to the local loop. Branch `claude/20261127-chat-markdown`
  (local): chat messenger layout + Markdown replies, not pushed yet.
- 2026-11-27 23:20: dev build running on the phone (debug, release-signed, loopback HTTP,
  code-signing removed in `src/debug/AndroidManifest.xml` only; Metro needs no key then).
  Chat verified on the phone: Markdown replies, bubbles, one-row composer, compact list,
  opens at the newest message (inverted list), readable Resend on own bubbles.
  Trap: the dev build asks for "display over other apps" on first start (Android
  Settings opens); not needed, return with the monkey launch.
