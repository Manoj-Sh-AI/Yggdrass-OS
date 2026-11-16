# Dedicated Brain graph page

Manoj's instruction, 2026-11-12: place a separate Graph visualization page immediately after Notes in main navigation. Integrate the entire existing real Brain viewer, with the rotating graph in the centre and its existing descriptions/details on the right, matching the site's aesthetics. Do not replace it with the synthetic area graphs or modify the memory engine.

## Acceptance

- `/graph` uses the shared authenticated shell; Graph visualization follows Notes in desktop and mobile navigation.
- Reuse the existing Brain service's generated `graph.html` and its vendored local scripts/fonts. No personal graph data in public assets/source, no new graph layout or semantic algorithms.
- Open the existing 3D map by default. Preserve slow rotation, interaction pause, 2D, filters, search, legends, sensitive-note reveal and description/summary/facts/relationship panel. Respect reduced motion and provide explicit pause.
- Match navy/glass typography and borders through an application presentation adapter. Details remain on the right on desktop, stacked on phones without horizontal overflow.
- HTML/assets require an application session. Brain Basic Auth stays in the backend. Allowlist assets, refuse redirects, disable private-response caching and block external frame requests.
- Loading and retryable error; never demo fallback. Refresh reopens the latest generated viewer, not a promise of live regeneration.
- Open note actions navigate to real Notes. No graph edits or Brain writes.
- Verify proxy protection, navigation, frame failures, note opening, responsiveness and the real read-only viewer in a browser. Real screenshots stay in ignored runtime output.

Existing area prototype graphs remain unchanged. Lia orchestration, graph generation and post-save semantic review are separate work.
