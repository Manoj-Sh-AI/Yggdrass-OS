# Notes → Brain API integration

Scope: approved Notes page/editor plumbing only, 2026-11-12. The notebook layout is retained. No changes to Lia, the connector/note server, graph viewer, Brain schemas, or Markdown source switch. Other pages retain their existing data port.

**Later integration authorization and current runtime:** Manoj subsequently explicitly authorized enabling the existing database write mode without changing Lia's engine. The private Brain environment now selects `rows`, and the existing HTTP API was restarted on loopback port 8100. The live Notes proxy lists/opens 82 notes and the safe absent-note preview confirms the Markdown gate is gone. No personal test writes were performed. Two new actual-Brain/PostgreSQL integration tests plus all 19 existing Notes proxy tests pass. See `requirements/spec-notes-live-write-integration.md` and `planning/notes-live-write-integration.md`. The earlier source-switch restriction and Markdown-only verification below describe the original delivery, not today's runtime.

The existing editor supports **fact edits via Save now → combined preview → Confirm**, followed by an authoritative refresh. Creating notes and Undo use the same real API. It does not yet provide every-save asynchronous Lia review, archive/restore controls or arbitrary metadata/summary editing. The recorded answer-parity failure remains unresolved, and the Brain's existing scratch workspaces were not replaced.

## Delivered

- Notes-only backend HTTP client attaches Basic Auth from private backend `BRAIN_API_USER`/`BRAIN_API_PASSWORD`; `BRAIN_SERVER_URL` defaults to `http://localhost:8100`. Browser requests contain the existing application session/CSRF credentials, never the Brain credential. Redirects are refused.
- Empty-query search loads the upstream list in its supplied order. Bounded parallel detail reads provide titles (slug fallback), first-fact previews, areas and relationship data. Search queries are forwarded to the upstream search endpoint. Selecting a note obtains an authoritative full body/version and a session-bound fetched-snapshot token.
- The existing vibrant New note action opens the same notebook editor as an unsaved draft. Explicit Save validates the title, builds the full existing-format Markdown note and calls POST `/api/note`. Returned detected links are displayed. A successful create receipt prevents a repeated acknowledged create from issuing another POST in the same session.
- Existing Save sends the entire edited body plus its opaque fetched token. Backend computes fact-line changes and retains upstream replace/remove previews and locally staged additions under a random session-bound preview token. One combined panel shows old → new text, available link changes, permanent removal warnings, Confirm and Cancel.
- Confirm executes operations in order with upstream-supplied versions, refreshing the note between writes. It stops on stale 409 and reports partial completion. Successful duplicate confirmation returns its saved receipt. Cancel never executes staged changes. After success the authoritative note is reopened.
- Page/editor share the session's one latest remote Undo action. Its ID stays in the backend. No ID disables Undo; success refreshes notes, while upstream 400/409 errors remain visible.
- Markdown refusal is a visible banner: **Writes are not live yet — the brain is still on markdown.** Draft content remains available. No silent mock fallback and no remote autosave. Dirty drafts require explicit save/reload before in-app navigation or Undo.
- Native editor drafts use a separate `yggdress.notes.brain.v1:` recovery namespace; mock drafts remain separate. New-note drafts can recover after reload. Export remains available.

## API limits and operational tradeoffs

- Existing metadata, headings, summaries and link-section edits cannot be represented by the supplied fact endpoints. Metadata controls are read-only for existing notes; unsupported body edits and fact moves are rejected explicitly. New notes retain editable title/description. This is an API limitation, not a replacement memory implementation.
- `add-fact` writes immediately and ignores a preview flag, so additions are staged in application memory until Confirm. Their displayed references are provisional; actual detected links come back after saving. The API cannot insert before the first fact: that placement is disclosed as an append in review.
- Multi-line writes are individual upstream transactions, not one atomic batch. A later failure can leave earlier confirmed changes saved; the response reports the known completed count and prompts refresh. A transport failure after a write may require authoritative reload to establish its outcome. No automatic replay of failed confirmations.
- Fetched snapshots expire after 30 minutes, previews/confirmation receipts after 10 minutes, sessions after 8 hours. Memory is bounded and lost on service restart. Use one application worker for this prototype; distributed workers would need separately approved shared ephemeral storage or sticky routing.
- Native BlockNote blocks support local recovery/export, while the Brain wire format remains Markdown. Unsupported rich formatting is not claimed to round-trip through the fact API.
- Brain occupies port 8100. Use a different application service port (e.g. 8101) or the existing random-port local preview. The preview launcher accepts a private `--brain-env` path, reads only the three connection settings into the backend client and excludes Brain environment variables from the Next child.
- Upstream search returns catalogue rows without fact previews. Eight concurrent detail reads avoid serial request timeouts, but the complete live list of 82 notes still took 27.6 seconds in local verification. Faster initial listing would need an upstream preview/pagination contract; it is not a reason to bypass Brain ownership. Loading and connection errors remain visible.
- The API does not expose an update timestamp in its note DTO. Missing dates display “—” rather than an invented timestamp. Shared header search, capture and Lia demo flows retain their prior port; this task connects only the Notes page/editor.

## Files in this slice

Backend: `app/api/src/yggdress_app/notes_proxy.py`, `application.py`, `.env.example`, `README.md`; synthetic fixtures/tests in `tests/notes_fixture.py` and `tests/test_notes_proxy.py`; Notes injection and private preview setup in `scripts/browser_check.py` and `scripts/local_preview.py`.

Frontend: `src/lib/notes-api.ts`, `src/components/notes-brain-provider.tsx`, the existing `brain-explorer.tsx` and `note-editor.tsx`, Notes route wrapper, backend proxy allowlist/timeout, structured API errors, isolated draft namespace, and retryable Markdown save state. `shell.tsx` changes only Notes-specific source labels; other pages keep their prior behavior. Tests: `tests/notes-api.test.ts`, `e2e/notes.spec.ts`, and existing Phase 1 fixture assumptions adapted for Notes' new port.

Requirements/planning/rationale: `requirements/spec-notes-brain-api.md`, `planning/notes-brain-api.md`, `rationale/decisions/D45-notes-http-proxy.md`.

## Verification

- Frontend: **103 tests passed**, including safe full-note serialization, server-only auth boundary, structured Markdown refusal and isolated recovery storage.
- Backend: **66 tests passed** in the complete application suite, including 19 Notes tests for bounded parallel reads, auth/session/CSRF, line diff/preview/confirmation, cancellation/expiry/ownership, authoritative version chaining, partial/stale failure, Markdown refusal, create retry receipts, Undo and fact-move rejection. Ruff checks and formatting pass. One existing Starlette/httpx deprecation warning remains; no dependency changes were introduced.
- Production frontend build and TypeScript pass.
- Browser: **17 scenarios passed** across Notes, Phase 1 and Phase 2. Notes checks cover delayed-response selection, blank-title validation, explicit capture → search → reload, preview Cancel/Confirm, remote Undo, Markdown-banner draft preservation/recovery, stale confirmation/refresh, permanent-removal warning and phone layout. Existing Today/task/routine/Calendar/authentication/mock-drawer flows also pass.
- Synthetic desktop/phone screenshots were inspected. No horizontal overflow was observed; no stylesheet/layout redesign was made.
- Live check on the final running preview: signed-in Next proxy → application backend → Basic-authenticated Brain search returned **82 notes**; note detail returned the full body and an owned snapshot token. Undo was correctly disabled with no session write. The exact Brain credential values were absent from response payloads and all browser JavaScript bundles.
- The existing Brain API was started from the clean PR #44 sibling checkout on port 8100. Its Markdown mode and both checkouts' Brain source files remain unchanged. Real Brain writes were **not** attempted. All write verification used invented fixtures.
- Local preview: `http://127.0.0.1:3000/notes`. Application-only preview records were backed up and restored before restarts; private preview sign-in details remain in ignored `app/api/runtime/preview-session.json`. Brain credentials are separate and were not printed.
