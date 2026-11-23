# Android release APKs are signed with the owner's own key

Date: 2026-11-21. Owner choice: "take the correct steps", after being told the
APK was signed with the public debug key.

**Why.** Expo/React Native templates sign release builds with `debug.keystore`,
which is the same public key in every project. Android only lets an APK update
an installed app if both carry the same signing key, so with the public key anyone
could build an APK that installs over Yggdras and inherits its sign-in. The
in-app "Download Android VERSION" path depends on that check meaning something.

**What.**
- `scripts/android-tools.py android-key` creates a 4096-bit RSA PKCS12 key once
  in `local-data/android-signing` (git-ignored) with a random password stored in
  `signing.properties` beside it. It never replaces an existing key.
- `plugins/with-release-signing.js` survives `expo prebuild`: release builds sign
  with that key (via `YGGDRAS_ANDROID_SIGNING`, set by `android-tools.py`), and a
  release build without it fails instead of falling back to the debug key.
  Debug builds keep the debug key.
- `mobile-release.py android` refuses an APK whose signer is the public debug key.

**Cost.** Changing keys meant uninstalling the debug-signed app once. The phone
loses only its sign-in, device id, call opt-in and timezone choice; all user data
is on the server. Losing the key means the same again, so it is backed up with
the update-signing key.
