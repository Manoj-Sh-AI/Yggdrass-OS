# Windows laptop host and persistent services

2026-11-15. This release targets the owner's existing Windows laptop. Use a small WinForms/WebView2 host compiled with Windows' .NET Framework compiler. The installed .NET command has no SDK; Rust is present, but adding a Rust-based app framework and a second packaging toolchain is unnecessary for this local build. Native mobile is explicitly deferred. WebView2 is the supported Microsoft web rendering control; its SDK is pinned and its license accompanies the output.

The host does not reimplement the website or connect to PostgreSQL directly. It starts the shared loopback runtime and displays the existing authenticated origin. Native messages and host objects are disabled; the page gains no filesystem/process bridge. External navigation is restricted. The webview has a private persistent profile distinct from the user's browser. The desktop window closes independently of the shared local services, allowing web and desktop use without interrupting a timer or another open client.

Application data moves from process-managed temporary PostgreSQL into a current-user private local-data directory. The import first verifies a full backup in a disposable cluster, compares the restored records before additive app migrations, then checks old tables remain unchanged. Brain data is not copied. Normal launches never migrate or seed. Separate restricted runtime credentials serve requests; administrative credentials stay in the private local service configuration, outside the frontend/desktop bundle.

The first output is workspace-linked, not a portable all-dependencies installer. It preserves the owner's existing development environment and enables useful laptop testing now. Retain the checkout and its dedicated frontend build. No cloud deployment or automatic update system is introduced.

References: [Microsoft WebView2 WinForms guide](https://learn.microsoft.com/en-us/microsoft-edge/webview2/get-started/winforms), [WebView2 security guidance](https://learn.microsoft.com/en-us/microsoft-edge/webview2/concepts/security).
