# Notes editor milestone — BlockNote integration

This is an implementation/delivery record for the user's authorized Notes enhancement. It does not replace the architecture or roadmap.

## Reused infrastructure and source

The audit verified Next.js 16.4.5, React 19, TypeScript, Tailwind 4, the existing Notes route/list/drawer, Radix modal layer, app shell, shared application provider, protected workspace layout, same-origin application proxy, mock Brain adapter, Vitest and Playwright. Task/routine PostgreSQL services and personal-password authentication remain in their separate backend. No Brain or backend code or migrations are changed by this frontend milestone.

Installed exact official packages: `@blocknote/core@0.57.0`, `@blocknote/react@0.57.0`, `@blocknote/ariakit@0.57.0`. Each declares MPL-2.0; their installed LICENSE files were inspected. Ariakit UI is used to avoid adding a competing visual framework. Native BlockNote supplies rich formatting, headings/lists/checklists/quotes/code/dividers/basic tables, links/colors/alignment, contextual menus, slash commands, handles, block selection, clipboard editing and undo/redo. Small application controls call the native block manipulation API for accessible movement/duplication/insertion/removal. No XL/Pro/AI or collaboration package is used. See `THIRD_PARTY_NOTICES.md` and shipped `/licenses/blocknote/` notices/source references.

## Development persistence and serialization

- The existing authenticated mock Brain adapter remains the read/write boundary. The existing mock inventory is process-local; no new note database or application SQL table is introduced.
- Native block JSON is the authoritative **development editor representation**. A versioned text envelope carries blocks, derived Markdown and presentation icon through the existing mock content field. Adapter decoding exposes the Markdown projection to existing lists/search and retains structured blocks for the editor. This mock envelope is not an imposed production Brain contract: rich writes are rejected for non-mock notes. Claude must approve the eventual representation/write API.
- One latest browser-local recovery draft per note uses `yggdress.notes.development.v1:<id>`. It retains current title/summary/tags/blocks and the upstream opaque base token; it is not a hidden history, backup service or source of semantic relationships. `yggdress.notes.active.v1` remembers navigation only. Browser storage is readable by scripts on the origin; password sign-in does not encrypt or make it production Brain storage.
- Edits are immediate in memory. Saves wait 900 ms; native document conversion and storage are deferred to saves, not run for each key. The editor instance is stable for a note and the canvas is memoized. Pending writes serialize, later edits retain their revision, clean documents do not trigger redundant network writes, and note switching/closing flushes first. Refresh/navigation interruption checkpoints a local recovery draft. Storage errors remain visible and block unsafe switches. Explicit reload replaces a conflicting draft; export is offered first.
- The local draft is checkpointed before the mock write. Acknowledgment records the service-provided version; no application conflict-token generator is implemented. HTTP 409 stops automatic writes and retains the draft. Real validation/history/map updates stay exclusively Claude-owned.
- Delete previews and explicit confirmation remain. Local cleanup must succeed before the confirmed mock write; a rejected mock write restores the local draft. Successful deletion removes the current local copy as well as mock content. This is a development flow, not a claim about transactional deletion across a future Brain service and browser.
- Native JSON export preserves block properties and supported unknown attributes. Markdown export is labeled potentially lossy; tables, unsupported blocks, alignment, underline and colors raise visible warnings. Original unsupported/corrupt document representations are preserved for export instead of being converted to empty notes.

## Limits and future integration

The mock service must run and authenticate the source; browser drafts are not an offline replacement for Lia. Normal refresh restores documents and the active note. Restarting the mock service resets its inventory and tokens: existing fixture drafts can conflict and newly created IDs can become orphaned. Use the local recovery bundle/JSON export to retain those drafts. Clearing browser data removes local drafts. Multiple tabs have no collaborative merge protocol; upstream mock version checks reject stale writes. The mock API's existing content/request size limits remain; very large documents show a save failure and remain locally recoverable/exportable. File upload/storage and paid export formats are not provided.

Real shelves/detail/backlinks, transport/service authentication, authoritative version tokens, approved content serialization and create/replace/preview/confirm contracts remain dependencies on Claude. There is no real Brain connection, Brain SQL, semantic retrieval/generation, memory history, agent, notification delivery or deployment.

Dependency audit: runtime (`npm audit --omit=dev`) reports zero advisories after installing BlockNote. The full audit reports four existing development-tool findings affecting Vitest/mocker/tinypool and the root sharp image tool; remediation proposes major versions. They were not added by BlockNote and no unrelated major upgrade was applied. Deployment remains blocked.

## Files in this milestone

- `src/components/brain-explorer.tsx`: existing Notes page enhanced into responsive navigation/writing/context panels, synthetic shelf sections, search, creation and recovery export.
- `src/components/notes.tsx`, `note-editor-loader.tsx`, `note-editor.tsx`: retained virtualized NoteList, shared client-only BlockNote editing surface and existing drawer/modal integration.
- `src/lib/note-document.ts`, `development-drafts.ts`, `note-save-session.ts`: separate serialization, isolated recovery storage and serialized revision-aware saves.
- `src/lib/brain-adapter.ts`, `src/components/application-provider.tsx`: mock-only structured document normalization, guarded navigation and draft cleanup through the existing write interface.
- `src/components/ui.tsx`, `shell.tsx`, `src/app/layout.tsx`, `notes.css`: existing icons/tokens, native-editor shortcut preservation and scoped layout/theme styling.
- `package.json`, `package-lock.json`, `THIRD_PARTY_NOTICES.md`, `public/licenses/blocknote/`: exact dependencies and preserved notices.
- `tests/note-*.test.ts`, `e2e/notes.spec.ts`, updated `e2e/phase1.spec.ts`/Playwright selection: new editor verifiers and preserved Phase 1 regression scenarios.
- `requirements/spec-blocknote-notes.md`: the authorized milestone's scoped acceptance criteria.

## Verification

- Frontend type check and production build pass. The final standalone type check avoids running concurrently with Next's build/type generation.
- **89 unit/component tests pass**: all 68 prior checks, 11 serialization/storage checks, 8 save-session checks and 2 exact-package/license boundary checks.
- **All 9 production browser scenarios pass together** in Microsoft Edge: 4 Notes scenarios and the 5 Phase 1 regressions. Coverage includes native contextual bold formatting, slash heading/checklist/quote insertion, block movement, autosave, title/content search, refresh/active-note recovery, explicit deletion/local cleanup, Markdown parser/exporter round-trip, headings/lists/checklists/quotes/code/links/inline formatting, lossless JSON with rich styles/table cells, visible lossy-export warnings, storage quota failure/draft preservation/navigation guard/retry, native undo/redo, collapsible mobile panels, an empty note, a 180-paragraph paste, flush before switching and recovery on immediate refresh. Authentication, unauthorized rejection, PostgreSQL task/routine persistence, Today, outages and old Notes version/delete handling remain covered.
- Visually inspected `verification/blocknote-notes-desktop.png` (1344 px wide) and `verification/blocknote-notes-phone.png` (390 px wide), both local/ignored. Mobile is browser emulation; physical iOS/Android keyboards and touch drag gestures were not device-tested. Block movement was exercised through the native API's keyboard-accessible buttons; drag handles use the unmodified BlockNote implementation.
- The initial multiline test used direct contentEditable DOM filling, which does not represent BlockNote's paste pipeline; the final long-document test dispatches a native clipboard-data paste event, verifies all 180 paragraphs, then switches/reloads. No conversion workaround or alternate editor engine was added.
- Runtime dependency audit reports zero advisories. Full dependency audit and existing development-tool advisories are described above; no unrelated major upgrade was made.
- **All 29 application backend tests pass** against isolated PostgreSQL. The existing third-party Starlette/HTTPX deprecation warning remains non-fatal. Backend code and migrations were not modified. Existing Python memory tests, Brain implementation, original architecture/roadmap and production configuration are unchanged; the memory suite was not rerun or altered for this frontend-only milestone.
- `git diff --check` passes. No deployment or actual personal/Brain database access was performed. Test credentials and temporary PostgreSQL instances were removed by the harness; screenshots/downloads remain ignored local artifacts.
