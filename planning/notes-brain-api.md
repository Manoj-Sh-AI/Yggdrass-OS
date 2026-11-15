# Notes plumbing sequence

1. Inspect PR #44 without merging/replacing current working files; preserve Markdown source.
2. Add a Notes-only backend HTTP client and authenticated router. Session-scoped read snapshots, preview bundles, execution receipts and latest Undo stay in bounded expiring process memory, never in Brain/application SQL.
3. Add a scoped Notes binding around the existing page. Other pages retain their current providers and behavior. Reuse the same editor with an optional live save port; retain mock drawer behavior outside Notes.
4. Explicit Save stages/awaits the combined preview; Confirm/Cancel resolves that save. Add uses the same editor, not a second editor. Keep the notebook layout/tokens.
5. Exercise server contracts with synthetic responses and the existing production browser harness. Check real reads only if the Brain service is available; never perform real writes or change YGGDRAS_BRAIN_SOURCE.
6. Report auth, reads, add, preview/confirm/refresh, Undo, Markdown banner, verified tests and remaining API limitations; then stop.

Completed 2026-11-12. Final evidence: 103 frontend tests, 66 backend tests, 17 browser scenarios, TypeScript/production build, Ruff and authenticated live reads passed. A delayed-open response race was reproduced and guarded; the regression test passes. Live initial-list latency and fact-only editing limits are documented in `app/web/docs/notes-brain-api.md`. No real writes, source switches, Brain modifications, deployment or subsequent phase work were performed.
