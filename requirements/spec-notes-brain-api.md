# Notes → Brain API plumbing

Authorized by Manoj, 2026-11-12. Scope: existing Notes page/editor only; preserve its design. No changes to Lia, the note server, graph viewer, Brain source switch, schemas, or other product pages.

- Backend-only Basic Auth from BRAIN_API_USER/BRAIN_API_PASSWORD; BRAIN_SERVER_URL defaults to http://localhost:8100. No secrets in browser payloads, logs, source or public environment variables.
- List through GET /api/search (empty q); open through GET /api/note/{slug}; title/slug fallback, first fact one-liner and areas.
- Add opens a blank existing editor; explicit save sends the full note text to POST /api/note and displays returned detected links.
- Existing saves submit the full edited text and a session-bound fetched-snapshot token. Backend computes line changes, obtains replace/remove previews, and retains all operations/previews in memory behind an expiring session-bound request token. No confirm payload from the browser supplies executable changes.
- One combined review shows old/new lines, links added/removed, permanent-removal warning, Confirm and Cancel. Confirmation executes in order and stops on stale 409. Refresh/display the authoritative note afterward. No automatic confirmation or remote autosave.
- Add-fact has no upstream dry-run: stage additions locally until Confirm; never call it during preview. Preserve upstream versions between operations and refuse ambiguous/non-fact edits that the fact-only API cannot represent. Report partial writes; do not claim a multi-call transaction.
- Page/editor Undo delegates the session's latest upstream undo_id; disabled with none. Show upstream 400/409 and success.
- Surface Markdown 409 as “Writes are not live yet — the brain is still on markdown.” Never switch sources or silently fall back to mock data.
- Test authenticated proxying, session isolation, expiry/cancel/double-confirm, multi-line operations/version chaining, partial/stale failure, Markdown errors, add/undo, secret isolation and existing UI regressions using invented notes only.

Verified PR #44 head b86f216084671db17414995ee35723a84da5bf70: search is present. Started the existing HTTP API on loopback port 8100 with Markdown mode unchanged. Authenticated empty-query search and a note read passed; no real writes were attempted. API fact changes cannot represent metadata/summary/heading edits, so those changes must be rejected explicitly rather than silently lost. Existing metadata fields remain read-only. A dirty live draft requires explicit save or reload before in-app navigation/Undo; navigation does not create or confirm remote writes.
