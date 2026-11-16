# Dedicated Brain graph page

The authenticated `/graph` page follows Notes in main navigation. It embeds the existing Brain graph rather than the prototype area graphs. The default is the original rotating 3D view, with its search, filters, legends, sensitive-note reveal, summary, facts and relationship details. The application adds a navy presentation adapter, pause/resume and a bridge to the real Notes editor. The existing renderer controls layout and relationships; no memory-engine or graph-generation code is changed.

## Data and privacy

- The application backend fetches the existing Brain note server's `/graph/` resources with the same private server-only connection/authentication as Notes.
- `/v1/graph/status` exposes counts from the viewer snapshot. `/v1/graph/assets/{name}` allowlists only the HTML, three renderer scripts and two fonts. Every request uses application session verification; redirects, oversized assets and unknown names are refused.
- Next forwards the application cookie, never a Brain secret. Private responses use `no-store`; the embedded HTML has a restrictive content policy blocking external network connections, forms and nonlocal scripts/fonts.
- No real graph HTML, node data or vendor copy is placed in `public/`. Its two public presentation files contain only generic CSS/JavaScript. No additional dependencies or Brain SQL writes are introduced.
- The page shows the **latest generated viewer snapshot** that the Brain service serves. Reload retrieves it again; it does not generate/rebuild the graph or promise live synchronization with every database edit. The existing Brain write path owns viewer regeneration.

## Behaviour and compatibility

The bridge uses the original viewer's DOM/state markers to detect ready/error, preserve its reduced-motion behaviour, pause its existing rotation function, and forward explicit open-note actions. It styles presentation only. If the renderer cannot start, the page offers Retry and 2D; it never substitutes synthetic data. The desktop details remain on the right, while phone layouts stack the graph and details.

The Notes deep link is `/notes?note=<slug>` and selects through the existing authenticated real-note path. Neither viewing the graph nor opening a note saves anything.

Deep links fetch the requested authoritative note before the full catalogue, so the editor can open while catalogue previews load in the background. The browser test deliberately holds the catalogue response to verify this ordering.

The shared application preview restore helper was corrected to omit stale login/session/migration rows when restoring a full data snapshot into its fresh disposable database. Business records and sequences are retained; the source backup is unchanged.

Verification results are recorded in `planning/brain-graph-page.md`. Real browser screenshots remain under ignored `app/api/runtime/` rather than public assets.
