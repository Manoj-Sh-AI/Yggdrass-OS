# Yggdras for Windows

This laptop build displays the same application as the website, with persistent local services and records. Native mobile, agents, orchestration and hosting remain separate work.

Build `app/desktop/build.ps1` in PowerShell. It fetches the pinned Microsoft WebView2 SDK from NuGet and compiles `Program.cs` with Windows' .NET Framework compiler. Output and downloaded packages are ignored. Keep the included Microsoft license. WebView2 Runtime is supplied by Windows/Edge.

Provision the persistent application runtime explicitly through `yggdress_app.local_runtime.provision`, using an application-only source database and a verified dedicated production frontend build. This is an engineering import, not an ordinary startup action. It refuses an existing destination. Keep the private `runtime.json`, PostgreSQL data, webview profile and backups under `%LOCALAPPDATA%/Yggdras`, outside OneDrive. Never commit them or include them in the desktop folder.

**Hosted (Railway):** add `"url": "https://<web app address>"` to `dist/desktop.json` and the window opens that HTTPS address directly, starting and checking nothing on the laptop; the microphone and in-app navigation are allowed for that address only. Remove `url` to use the laptop runtime again.

The ignored `dist/desktop.json` contains three local paths: `python` (application virtual environment), `moduleRoot` (API `src`), and `dataRoot` (private local data directory). It contains no password or API credential. Launch `dist/Yggdras.exe` or its desktop shortcut. The normal personal password remains required; desktop sign-in persists in its own profile. Closing the window leaves shared services available to other clients.

Recovery is available in the window. To stop only the owned local application services, run the API environment's Python with `-m yggdress_app.local_runtime stop`. PostgreSQL shuts down cleanly and records remain on disk. Starting the app brings them back. This does not stop an independently running Brain service.

For a read-only native rendering check, run `Yggdras.exe --verify <absolute-output-path>`. It writes a page summary and PNG, then closes. It does not sign in automatically or change user data. The production window disables native bridges/host objects, foreign frame navigation and arbitrary URI schemes. External HTTP/HTTPS links open in the system browser.

This is a workspace-linked personal application: moving/removing the checkout, Python environment, Node installation or active `.next-*` build breaks startup. It is not yet a distributable standalone installer. Build future web candidates into another directory rather than overwriting the active one.
