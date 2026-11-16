# Existing Notes write integration

1. Record the latest explicit authorization and retain the failed historical parity result as a separate unresolved issue.
2. Verify current service identity before changing its private source-mode setting. Do not print credentials.
3. Test the current application proxy against the actual Brain HTTP implementation with an isolated, invented PostgreSQL Brain. Fix application integration defects only.
4. Provide a local launcher reusing existing Brain startup functions; persist only the authorized private environment setting and restart only the verified API process.
5. Verify authenticated reads, authentication rejection, and the write gate with a preview-only nonexistent-note request. Do not change personal notes for testing.
6. Report the working interface and remaining contract gaps accurately. Background semantic review is not supplied by the current HTTP API and is not made operational by this switch.

## Completed, 2026-11-12

- Preserved the existing Brain implementation and the Notes interface. The only sibling project change made in this slice is the ignored private `.env` source-mode entry, now `YGGDRAS_BRAIN_SOURCE=rows`.
- Verified the identity of the old loopback API launcher, stopped that process alone, and started the existing Brain API using `app/api/scripts/brain_api_service.py`. The launcher refuses Markdown mode, missing credentials and an occupied port. It does not start Lia or implement a storage engine.
- Two actual-API integration tests passed against independent disposable PostgreSQL databases of invented notes. They cover create, add, replace, remove, Undo, re-opening with a fresh application proxy, persisted database bodies, concurrent-edit refusal and authentication.
- All 19 existing Notes proxy regression tests passed. Ruff check/format checks pass for the new launcher and integration tests. No frontend code changed, so the existing frontend build/browser results are historical rather than newly rerun results.
- Live verification: authenticated Brain catalogue read succeeded; the write-gate diagnostic on a random, absent slug returned database-mode 404 rather than Markdown-mode 409; unauthenticated search returned 401. Signed-in Next → application backend → Brain search listed 82 notes and opened an authoritative full body/snapshot. Brain credentials were absent from those responses. No personal note was changed for testing.
- The optional actual-Brain tests use `YGGDRAS_BRAIN_TEST_PROJECT` and the owner's existing checkout/test helpers. They do not load its `.env`. On Windows they fall back to the Brain environment's installed pure-Python dependencies, preserving the application's package precedence. No application dependencies were added.

## Still open

- The historical answer-parity traps bar remains FAIL on both paths; its evidence and criteria were not changed or rerun. The explicit integration request enabled write configuration; it does not resolve this separate engine-owner assessment.
- Every-save background Lia review is not implemented by the existing HTTP interface. No automatic semantic-review completion is claimed. Archive/restore UI and full metadata/summary editing likewise remain outside the supported fact endpoints.
- RowStore still uses its existing temporary scratch workspaces internally. The application does not add a file store, but this is not a claim of zero temporary Markdown files in the Brain implementation.
- Existing Lia/MCP sessions were not restarted. A session that already loaded Markdown configuration may need a separate restart to pick up the shared private environment setting; the verified service here is the application's Brain HTTP endpoint.
