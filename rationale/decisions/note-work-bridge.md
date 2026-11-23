# Explicit Notes-to-work bridge before automated interpretation

The shared planning records and staged connection tables already establish canonical ownership. This pass makes those connections usable without coupling ordinary saves to a new model, agent, or filesystem adapter.

Use existing task/event validators and command logic inside the same PostgreSQL transaction as the source link and retry receipt. This preserves task relationships, history, reminders, versions, and existing Calendar/Today projections. Brain is only read server-side to verify source identity/revision; no cross-database transaction or latest-at-commit guarantee is asserted.

Each link stores its creation-time source revision separately from the note reference's last-observed revision. Legacy links remain unknown rather than backfilled with invented provenance. A note update signals context to review; it does not silently change a task objective, cancel work, or erase history.

Keep linked work inside optional note context and reverse links inside a disclosure in work details. Reuse existing forms; avoid a second editor, task inventory, notification layer, or agent dashboard. The graph's Brain-owned visualization remains unchanged in this pass.

Every-save background interpretation cannot be honestly delivered by appending a callback to a remote commit. The durable producer and semantic output contracts are documented separately. No new semantic algorithm or autonomous worker is introduced to hide that dependency.
