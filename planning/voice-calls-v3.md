# Voice calls v3: planning by voice, outcomes and follow-ups

Status: approved and built 2026-11-20 (steps 1-6; step 7, live calls, with Manoj).
Builds on `rationale/decisions/voice-reminders.md`, which records what was built.
Owner decisions: sensitive notes allowed on every client; migration 014 approved;
retries 5 and 10 minutes.

## What Manoj asked for

1. On any call: add an emergency task or a one-off event, ask for free slots, let Yggdras
   place it (calendar agent + Lia), and move other tasks to make room. Writes go to the
   calendar after a spoken yes.
2. On a reminder call: a third choice besides start and snooze: **remove** the item.
3. When an item's time slot ends, it counts as **completed** automatically.
4. An unanswered reminder is retried **twice**. Still no answer:
   - a one-off task or event is marked completed anyway;
   - a recurring (routine) task is marked **not answered**.
5. The next call for that routine first asks what happened last time and records the
   answer. Not done: Yggdras advises on the combined workload (missed + today), then
   starts today's task.
6. Every outcome is recorded so the agents and Manoj can audit what happened.

## Gaps found in the code, and how each is filled

| Gap | Today | Plan |
|---|---|---|
| Free slots | Nothing computes them; the calendar agent reads only events, not task blocks or routines | A free, deterministic `free_slots(day(s), minutes)` read tool: busy = events + task blocks + routine windows; day = outside quiet hours; returns gaps ≥ minutes. No model call. |
| Rescheduling tasks | Task time blocks (`execution_blocks`) cannot be proposed by any agent | Add `block.create/update/remove` to the proposal operations, using the existing planning commands. Spoken yes applies, as today. |
| Emergency task | Can be created as a task, but nothing places it | "Emergency" = priority 1 + placed in the earliest free slot today; if none fits, Yggdras proposes which lower-priority block to move and where. |
| Remove on a reminder call | Only start / snooze | `remove_item` tool: event → removed; routine occurrence → skipped (the routine stays); one-off task → cancelled. Read back first: "Remove Pottery today? Shall I?" |
| Auto-complete at slot end | Events have no status; tasks complete only by hand | At the end of the slot: a task started or confirmed → completed (normal completion path, history). An event → outcome "completed". |
| Retries | One ring, then missed | Re-ring 5 and 10 minutes after the miss (2 retries), each with the same briefing. Retries stop as soon as the item is answered, removed or moved. |
| One-off vs recurring | Not distinguished | Recurring = from a routine template. Everything else is one-off. |
| "Not answered" | No such status | Recorded as an outcome (see storage below), never by changing the routine itself. |
| Follow-up next time | Calls know nothing about last time | The next reminder for the same routine starts with: "Last time, <title> on <day> went unanswered. Did you do it?" Yes → that occurrence becomes completed. No → it stays not done, and Yggdras gives a short workload note (missed minutes + today's minutes, one suggestion: do both, shorten, or move one) and then asks to start today's. |
| Audit trail | Tasks have history; events and calls do not record outcomes | One outcome record per item occurrence: completed / not done / not answered / removed / snoozed, with who decided it (Manoj by voice, automatic at slot end, automatic after retries) and the call it came from. |
| Sensitive notes (e.g. health notes) on a call | Blocked on every voice path | Decision for Manoj (below). |

## Defaults chosen (to confirm or change)

- Retry spacing: 5 min, then 10 min after the first miss.
- Free-slot day: 08:00-22:00 Europe/Berlin (the quiet hours bound it); 10-minute buffer
  around existing items; slots shorter than the task are never offered.
- Emergency placement never moves an item Manoj marked essential or a calendar event with
  other people; it moves task blocks only.
- An item snoozed past its own end follows the not-answered rule.
- An event with no answer after retries is completed anyway (it is one-off by nature).
- Auto-completion never touches an item Manoj removed, skipped or already completed.

## Storage (needs approval: application database only, never the brain)

Migration 014 adds `app.item_outcomes` (item kind and id, occurrence date, outcome,
decided_by, call id, note, time). Tasks keep their existing states and history; this
table is the single audit trail for calls. Staged and restore-verified like 012/013.

## Build order (each step tested before the next)

1. Outcomes table + recording (migration 014).
2. Remove on reminder calls.
3. Retries + one-off / recurring rule after 2 misses.
4. Auto-complete at slot end.
5. Follow-up on the next routine call + workload note.
6. Free slots tool + block proposals + emergency placement.
7. Live test calls (paid, Manoj present).

## Risks

- Auto-completion writes without a spoken yes; it is Manoj's explicit rule, recorded as
  `decided_by=automatic` so it is always visible and reversible in the task editor.
- Free slots depend on the calendar being complete; items only in other calendars are not
  seen (no external calendar connector is in this path).
