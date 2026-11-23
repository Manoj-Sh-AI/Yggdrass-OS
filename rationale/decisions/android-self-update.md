# Android updates install themselves, "when safe"

Date: 2026-11-21. Owner choice: "Silent when safe", picked over "one tap in the app"
and "keep the browser download". It reverses the earlier line in
`planning/mobile-updates.md` that the app does not silently install native code.

**Why.** Native updates needed Settings → Download (browser) → Install every time.
Android lets a sideloaded app update itself with `PackageInstaller`; on Android 12+
it can do so without a prompt once it is its own installer of record.

**When it installs.** It downloads in the background after a check (on open, at most
every 6 h). It installs only after the app has been in the background for 2 minutes
with no call ringing, connecting or in progress. Returning to the app, or a call
starting, cancels the wait. Android replaces the process; the next open is the new
version. If Android still wants a tap (the first time, since adb or the browser was
the installer of record), a notification asks for it.

**Safety.** The native side refuses an APK unless its SHA-256 matches the signed
release record, its package is `app.yggdras.mobile`, its version code is higher, and
its signing certificate equals the installed app's own (see
`android-release-signing.md`). A compromised server therefore cannot push another
key's APK; Android enforces the same key again. New runtime permissions are still
asked by Android as usual.

**Not covered.** If Android kills the backgrounded app before the 2 minutes pass, it
installs on a later backgrounding. Nothing checks for updates while the app is
closed (no background job), by design.
