# D40 — Routine execution is application data

Date: 2026-11-08. Status: approved scope; implementation conventions recorded for the authorized prototype.

Keep an immutable routine definition separate from mutable execution state. The controlled card receives both and emits commands; the Today wrapper handles persistence. This makes reuse possible without coupling weekly/mobile interfaces to the current browser repository.

Use a separate versioned application key, `yggdras.app.routines.v1`. The existing demo notes and the Claude-owned private Brain are not storage targets. Browser persistence is deliberately local and small; it trades cross-device availability and multi-writer coordination for a testable prototype with no backend dependencies.

Use self-reported integer percentages and explicit completion, rather than inferring work from a timer or inventing adaptation rules. Timestamps/history track execution only. The original goal, window and expected duration remain unchanged. Revisit percentage units, correction/reopen behavior and concurrency when the production task contract is approved.

The current architecture permits future database-backed Brain storage, but this record does not implement or authorize that migration, amend the memory engine, or silently replace older Brain privacy/storage decisions. Those depend on Claude's contract and explicit design approval.
