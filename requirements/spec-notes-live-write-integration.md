# Notes: enable the existing PostgreSQL write interface

Manoj's explicit integration authorization, 2026-11-12: enable the existing database write mode and make the current Notes application work with it. Memory-engine architecture, retrieval, semantic algorithms and schemas remain owned by Claude and are unchanged.

This narrowly amends the earlier Notes plumbing prohibition on operating the source-mode setting. It does not authorize application SQL writes into Brain tables or a replacement semantic engine.

## Acceptance

- Use the existing Brain HTTP API and its server-only Basic Auth. No browser database access or credentials.
- Configure the existing source switch to `rows` and start the verified local Brain API with that mode. Preserve unrelated environment settings and services.
- Keep the existing Notes UI and its preview/Confirm/Undo behavior. Test application proxy → actual Brain HTTP implementation → isolated PostgreSQL using invented notes: create/read, add, replace, remove, Undo, stale edits and reload persistence.
- Read the live catalogue and make only a preview request against a deliberately absent diagnostic slug to verify the write gate is open. Do not mutate personal notes as a test.
- Verify that an unauthenticated request is still refused. Report configuration failures without revealing secrets.
- Keep the failed historical answer-quality parity gate visible and unchanged. Enabling the explicitly requested write interface is not evidence that the answer-quality gate passed, or that the memory engine is approved as correct.
- Clearly distinguish working fact-API saves from still-unsupported summary/metadata edits, archive/restore UI and the pending asynchronous Lia-review integration. Do not claim these are complete by enabling a setting.

## Operational tradeoff

Use a small local-service launcher that calls the Brain's existing startup interfaces unchanged. This adds a repeatable operational entry point at the cost of depending on those startup interfaces. It implements no persistence, parsing, relationship or retrieval logic. The Brain's existing scratch workspaces remain a separate Brain-owner concern. Database-backed text is still serialized in the API's existing note-body format; the application introduces no Markdown file store.

The full database backup has passed isolated restoration; the user confirmed OneDrive upload. The historical parity result still reports a failed trap-answer bar on both paths. This remains an open engine-owner issue; do not edit the evidence or lower its thresholds.
