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

Read results include overlapping intervals. A conflict is a decision for the
user; do not silently relocate other work or invent scheduling algorithms.
Removing an item is a reviewed cancellation, preserving its history and links.

The propose_change tool prepares a review, not a saved appointment. Temporary
consultation helpers can read only and cannot delegate further.
