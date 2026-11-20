---
name: calendar-precision
description: Distinguish appointments, calendar dates and availability precisely.
domains: [calendar]
---

Read existing calendar records in the relevant bounded interval before proposing
changes. Use exact record identities and versions; never silently duplicate an
appointment because its title differs.

Timed events and availability need an explicit offset-aware start and end or
duration, plus a named timezone. Date-only items use starts_on and an exclusive
ends_before; never invent midnight. Availability is not a human focus session.
Ask when a duration, timezone, recurrence or relative date is uncertain.

Read results include overlapping intervals and task blocks (when a task is
scheduled). For "when am I free" or placing new work, read with free_minutes set
to the needed duration: the free slots are computed by code (events, task blocks
and routines, 08:00-22:00, 10-minute buffers). Never compute free time yourself.

Emergency or urgent work: create it as a priority-1 task and propose a task block
in the earliest free slot today. If no slot fits, propose moving the lowest-
priority task block (never an event with other people, never essential work) to
its next free slot, and say exactly what moves where. Moves are block.update
proposals; nothing moves until Manoj says yes. A conflict is still his decision.
Removing an item is a reviewed cancellation, preserving its history and links.

The propose_change tool prepares a review, not a saved appointment. Temporary
consultation helpers can read only and cannot delegate further.
