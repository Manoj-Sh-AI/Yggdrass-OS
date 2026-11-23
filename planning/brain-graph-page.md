# Brain graph integration

1. Proxy the existing Brain note server's `/graph/` assets with application session protection and a narrow allowlist. Keep its renderer/data private and unchanged.
2. Add `/graph` below Notes, with loading, error/retry, and a presentation adapter for theme/layout, pause and note navigation.
3. Deep-link to Notes through its real selection path, without changing the editor design.
4. Test protections and host interactions, build/typecheck, run browser checks and inspect desktop/mobile screenshots. Preserve application data when restarting the preview.

Tradeoff: embedding preserves the mature viewer instead of maintaining a second graph implementation. The presentation bridge depends on its DOM and state markers, verified by compatibility tests. This is the latest generated snapshot served by Brain, not a newly derived graph or live regeneration.

## Delivered and verified, 2026-11-13

- `/graph` and the Graph visualization navigation entry directly after Notes. The page matches the shared navy appearance and embeds the existing Brain viewer with its original 3D rotation, 2D mode, filters, search, legends, sensitive-note protection and details. An explicit pause/resume control is provided.
- Authenticated backend transport and a separate allowlisted Next binary/HTML proxy. No real graph data or vendor bundles copied into public assets; only generic presentation CSS/JS are public. No memory-engine, graph-generation, schema or dependency changes.
- A node's open-note action selects the real Notes editor. The selected note loads before the full catalogue; the browser test deliberately holds the catalogue response and verifies that the requested editor still opens.
- Production build and TypeScript pass. All **106 frontend tests** pass. The full backend run passed **83 tests**, with two optional sibling-Brain tests skipped; the subsequently added preview restore regression test separately passed, for **84 backend checks**. Ruff checks and formatting pass for changed Python files.
- The final complete browser run passed **20 tests**, covering Graph, Notes and existing Phase 1/2 flows. An earlier overly broad graph error selector was corrected, and an interrupted test-service run was discarded; these are the final uninterrupted results.
- Separate read-only real-viewer verification passed: 82 nodes/190 displayed connections, 3D readiness, pause/resume, right-side note details, opening the matching real Notes editor, phone stacking/no page overflow, reduced-motion rotation disabled, anonymous viewer access refused and no page script errors. Desktop (1344 × 896) and phone (390 × 844) screenshots were visually inspected and remain in ignored `app/api/runtime/`.
- Current preview application records were backed up before refresh and restored into its fresh isolated application database. The restore helper now retains fresh login/session/migration state rather than replaying duplicate seed rows. The old generated Next build was preserved under ignored runtime storage to bypass a Windows/OneDrive unlink problem; no source files or Brain data were deleted.

## Main files

- Backend: `app/api/src/yggdress_app/graph_proxy.py`, `application.py`; `tests/test_graph_proxy.py`.
- Frontend: `app/web/src/components/brain-graph.tsx`, `(workspace)/graph/page.tsx`, `api/graph-viewer/[asset]/route.ts`, `graph.css`, and the two generic `public/graph-embed.*` adapters.
- Navigation/layout and Notes deep-link integration: `shell.tsx`, root layout/API allowlist, Notes page, `brain-explorer.tsx`, `notes-brain-provider.tsx`.
- Verification: `tests/graph-route.test.ts`, `e2e/graph.spec.ts`, Playwright configuration; preview restore helper/test. Usage and limits: `app/web/docs/brain-graph.md` and frontend README.

Remaining boundary: Reload retrieves the latest existing viewer snapshot. Automatic semantic review, graph generation changes and new graph editing features were not introduced. Existing life-area demo graphs are unchanged.
