# Mobile updates on the existing Railway deployment

The Android app uses Expo Updates with a pinned RSA signing certificate and
Expo's native fingerprint runtime version. Screen updates cover Today, Tasks,
Calendar, Chat and other JavaScript UI. A native dependency, permission, Firebase
configuration or Kotlin change requires a new APK. An incompatible screen update
is never offered to an older native runtime.

## First installation

Deploy the new API and web routes through the existing Railway deployment, then
install the newly built APK once. The backend keeps releases under
`$YGGDRAS_HOME/mobile-updates` (`/data/mobile-updates` in the existing container).
Keep that directory on the existing persistent volume. No Expo account or new
cloud service is needed.

The backend serves public, signed application releases through the web app's
`/api/mobile-updates` routes. Releases contain application code and assets only.
Publishing requires the existing owner sign-in and a valid release signature.
No database, Brain, model key or Firebase service-account file enters a release.

## Signing identity

The public certificate is committed in `app/mobile/certs` and the API package.
Its private key is in the ignored `local-data/mobile-update-signing` directory.
Back that directory up privately. Never commit it or put it in an APK.
The release tool reuses this identity and fails if the key/certificate disagree.
Rotating the signing identity requires a new APK with the new certificate.

## Publish screen changes

From `app/mobile`:

```powershell
npm run release:screens -- --publish
```

This exports Android JavaScript/assets, resolves the native fingerprint, signs
the release and asks for the application's password without saving it. It then
uploads using a short-lived publishing session and signs that session out.
Run without `--publish` to produce a reviewable signed ZIP locally first.
Use `--origin https://your-web-app` if the deployment origin changes.

The app checks on startup and downloads a compatible update for a subsequent
launch. For an explicit update, use More → Settings → App updates → Check for
updates → Reload to apply update. Reloading requires confirmation so the user
can save drafts and finish a call first. When offline, the installed/cached app
continues to run. Expo's normal recovery and embedded fallback remain enabled.

For a rollback, publish the desired earlier JavaScript as a new signed release
with a new update ID and timestamp. Assets from earlier releases are preserved
so an already downloading phone can finish.

## Publish native Android changes

Increment the Android version/code, regenerate and build the native project,
verify its APK, then run:

```powershell
npm run release:android -- --publish
```

This packages `android/app/build/outputs/apk/release/app-release.apk` with its
build metadata. A phone on an older build sees Download Android VERSION in
Settings. Android's installer performs the update and validates the APK signing
identity. The app does not silently grant new Android permissions or install
native code. Every APK is signed with the owner's upload key in
`local-data/android-signing` (see `rationale/decisions/android-release-signing.md`);
back it up with the update key. Keep the same key for subsequent APKs.

After installing the Firebase-enabled build, enable incoming calls in More →
Calls and grant notifications, microphone and full-screen call display as needed.
An actual locked-screen ringing/audio test is still required on the phone.

## Deployment validation

- API tests cover authentication, signatures, tampered assets, archive traversal,
  runtime matching, immutable IDs and retention of older assets.
- Mobile tests cover download/reload separation, failed/offline checks and native
  update version/origin validation.
- Public manifests contain only releases for the exact requested native runtime.
  A missing channel returns HTTP 204 so the installed app keeps working.
- Deploying source alone does not publish a screen release: run the release
  command after tests pass. Native changes always require the APK build step.
