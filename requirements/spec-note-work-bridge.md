# Notes → work bridge

Owner authorization, 2026-11-14: finish interconnected application fundamentals before specialist agents, Yggdras orchestration, or its eventual conversational interface.

## This delivery

- A saved Brain note can create a canonical task or fixed appointment with its source link in one application transaction.
- The backend verifies the requested note identity and saved revision through the existing authenticated Brain reader. It does not write Brain or copy a note body into application reference tables.
- Existing work can be attached/detached from optional Notes context. Unlinking never deletes work. Completed tasks and removed appointments retain their links until explicitly unlinked.
- Task, Calendar, and Today event details expose optional source context. The same canonical work records feed existing Calendar and Today views.
- Source revision belongs to each link. Another use of a newer note revision cannot rewrite earlier provenance. A changed source is reviewable context, not permission to replace a task's fixed objective or deadline.
- Retrying a command returns its committed result. Stale source notes, invalid related records, and missing/offline Brain fail without partial creation. Form drafts remain on failure.
- Interface additions follow the existing quiet design, remain optional, and do not block opening the notebook.

## Subsequent component contract

Leah retains her librarian responsibility and supplies application-relevant interpretations of committed changes. Yggdras will eventually route those interpretations to individually tested specialist agents. Agents and the orchestrator are outside this delivery. The future ChatGPT-style Yggdras chat is explicitly deferred until those foundations work.

Automatic note-change processing requires a Brain-owned durable revision/change contract and a typed interpretation contract. The currently inspected Brain HTTP API exposes neither. Do not call a second model from the application, parse dates with a replacement semantic engine, or claim a best-effort callback guarantees every save. See `contracts/lia-workflow-change-v1.md`.

## Acceptance

Verify atomic task/event creation and source linking, source revision checks, concurrent retries, offline replay, rollback, authenticated/CSRF-protected access, restart persistence, note change/archive behavior, and preservation through completion/unlink. Exercise the real UI with synthetic notes: create from note → task → Calendar/Today → complete → reopen source context; also event creation, existing-work linking, saved-note revision changes, failed writes, keyboard controls, and phone layout.
