# Separate Lia context from agent record updates

2026-11-15. The owner clarified that Lia extracts date/context, Yggdras routes it, and specialized agents decide application updates. The application must not collapse this into a new Lia interpreter or a hidden orchestrator.

Use separate authenticated scopes and durable records for note handoffs, future router acknowledgement, specialized agent commands and background-run state. The handoff endpoint cannot mutate tasks/calendar. Agent commands require a matching stored handoff and current readable source revision, plus stable commitment identity and target-version checks. Acknowledging a handoff is not an application mutation. No router/runner exists in this delivery.

Application code validates typed work and time, preserves original goals, and asks for explicit reconciliation when owner edits, completed execution, cancellation or uncertain meaning would otherwise be overwritten. Unsupported/coarse/relative meanings stay visible as proposals; the application does not invent dates or energy thresholds. Source lifecycle observations preserve existing application history. Whole-note archive/restore Brain HTTP writes remain unavailable rather than being reimplemented here.

Operational relationships use real foreign keys and a bounded read projection alongside the unchanged Brain viewer. Focus sessions and unattended runs are separate records and clocks. Run cancellation remains a request until its provider confirms. Chat conversation selections persist intent while individual requests retain their own agent/model destination; changing selection neither retargets an in-flight response nor replays held history.

Scope tokens and optional chat catalog metadata remain in private backend configuration. Default actual agent/model connections are disabled. Stable Brain identity beyond the current slug/revision reader remains a producer assertion to be agreed with Claude before connecting real agents. This is an explicit boundary, not an inferred identity-reconstruction algorithm.
