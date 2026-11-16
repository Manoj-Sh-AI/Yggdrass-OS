# Windows laptop application

Owner authorization: 2026-11-15, following local application building/testing. Native mobile is later; no deployment or home-network connection work.

The Windows application reuses the existing Next.js interface, authenticated application API and PostgreSQL records. It is a personal, workspace-linked laptop build, not a standalone installer for other computers. It must not duplicate task/note stores, expose server credentials, change Lia's memory engine, or add agents/orchestration.

Acceptance:

- Launch from a normal desktop/Start menu shortcut, without opening a terminal.
- Start persistent application services if stopped; reuse the exact owned services if already running. Never terminate an unrelated listener or guess that any localhost page is this application.
- Keep existing personal sign-in, saves, preview/confirm rules, keyboard controls, files, and graph intact. Persist the desktop browser profile and application records across restarts.
- Store application PostgreSQL data outside OneDrive's synchronized working tree, with current-user access and SCRAM credentials. Provision explicitly from a verified full application-only backup; refuse overwrite/reseed. Normal startup never runs migrations.
- Bind services only to loopback. No native bridge, host objects or credential injection. External web links open in the browser; arbitrary native URI schemes and foreign frame navigation are blocked.
- Show a usable startup/recovery screen if the local service or display fails.
- Reuse the existing approved Brain HTTP launcher only when its configured local port is unoccupied. Do not modify its engine, migrate its database, run agents, or stop an existing independently running Brain process.
- Verify native startup/rendering, existing-service reuse, restart persistence, authorization boundaries, and production/browser tests before handing over.

This build requires the existing local checkout and its Python/Node/PostgreSQL installations plus Windows WebView2. The window is implemented with the Windows-provided .NET Framework and Microsoft's WebView2 SDK; there is no .NET SDK installation or additional cross-platform application framework. Future distributable packaging can replace the workspace-linked launcher without changing application APIs or data.
