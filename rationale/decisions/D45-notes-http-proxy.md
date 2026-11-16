# D45 — Notes-only authenticated Brain HTTP adapter

(Renumbered from D43 on 2026-11-16: D43 and D44 are the brain's PostgreSQL records on PRs #43/#44.)

Approved scope: Manoj's Notes API plumbing request, 2026-11-12. Brain ownership and Markdown source stay unchanged.

- Use the published PR #44 HTTP contract, with Basic credentials attached only by the application service. Do not import Lia or grant the application database role Brain access. This trades extra HTTP latency for process isolation and maintainability.
- Scope live Notes state to the Notes route and reuse the existing notebook editor. Keep the global mock port used by other pages unchanged. This trades temporary provider duplication for a narrow change and reliable page isolation.
- Hold fetched snapshots (30 minutes), combined previews/receipts (10 minutes), recent create receipts and the latest Undo in bounded process-local application-session memory. A restart expires them and requires reload; multi-worker deployments require sticky routing or a separately approved shared ephemeral store. This favors simplicity and fail-closed confirmation over distributed availability.
- Stage additions locally because add-fact has no dry-run. Call replace/remove previews upstream, then execute ordered writes with freshly read authoritative versions. Calls are individually atomic, not a multi-line transaction. Report partial completion and stop on conflict; never silently retry a failed confirmation.
- The current API changes Facts only. Preserve frontmatter verbatim and reject unsupported edits; do not rebuild Brain text/history/link algorithms. Brain-maintained History changes are allowed during authoritative refresh. This protects consistency at the cost of temporarily restricted metadata editing.
- Native blocks are recovery/export data in the browser. The wire format is the existing Markdown note format, not a new BlockNote storage schema. Rich formatting that Markdown cannot represent is not claimed to round-trip through Brain.
- No remote autosave. Explicit Save opens review, Confirm writes; dirty drafts block in-app navigation and Undo until handled. Synthetic fixtures cover writes; final personal-data checks are read-only.
