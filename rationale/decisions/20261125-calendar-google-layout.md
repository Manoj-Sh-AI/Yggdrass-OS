# Phone calendar follows Google Calendar's layout; ringtone is the phone's own

Date: 2026-11-25. Decided by Manoj ("make a detailed research on Google Calendar and
replicate it, even in terms of design placement"; "the ringtone is shitty").

## Calendar

Placement follows Google Calendar's Android app (research: five views Schedule, Day,
3 Day, Week, Month; tasks shown beside events; Schedule lists upcoming events and tasks
together; 2026 Material 3 refresh rounds the Month grid and boxes the Day timeline):

- Top bar: ☰ (views and filters, Google's drawer), month name with ▾ (a mini month to
  jump to a date), and a today button showing today's date number.
- Views: Schedule (default; date column on the left, today circled), Day and 3 days
  (all-day strip, then a 24-hour timeline with a red now-line, overlapping items side
  by side), Month (grid with item labels, "+N"). Swipe left/right moves by a day, three
  days or a month. Tapping a day in Month or Schedule opens that Day.
- A floating + opens Event or Task; tapping an empty hour opens a new event that day.
- Tasks are ticked off in place.

Week view is left out: on a phone it is the 3-day view with less room per day.

**Colours.** Google colours items by calendar. The token layer is closed (no new hues
without Manoj), so kinds are told apart by shape using existing tokens: events filled
with `accent`, tasks outlined with a tick-circle, availability dashed. If Manoj wants
per-kind colours, that is a token decision for him.

## Ringtone

Calls ring with the phone's default ringtone (`Settings.System.DEFAULT_RINGTONE_URI`)
on a new channel `yggdras-calls-v3`; `yggdras-calls-v2` (the generated chime) is
deleted, because Android never lets an app change a channel's sound after creation.
Manoj can pick any sound for "Calls from Yggdras" in Android notification settings.
The desktop keeps the chime.
