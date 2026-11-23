# Voice reminders: briefed calls 5 minutes before an item

Date: 2026-11-20. Owner choices: Firebase push to the phone, plus the laptop rings when the
desktop app is open; spoken "yes" marks the task started; one Haiku call writes the
briefing; briefings live in a new table (migration 013).

Amended 2026-11-20 (owner spec v2): Lia is the single door to the notes. Prep asks Lia
10 min before the start; the backup lookup asks Lia. No reminder code searches notes.

Amended again 2026-11-20 (owner choice): a reminder call can do what Yggdras does. It
hands calendar, task, reminder and suggestion requests to the full Yggdras voice role
(one orchestrator, not a second agent), whose knowledge now also goes through Lia. A
change Yggdras proposes on a call is read back and applied by Manoj's spoken yes.

**Why.** The full Yggdras/Lia answer takes 6–15 s, too slow for live speech. All slow work
moves before the call: a briefing is written in the background, and each spoken reply is
one small model call over it.

**How it fits the existing calls.** No second scheduler and no second voice stack.
- **Scheduler:** the existing Temporal sweep (every 15 s) still derives check-ins from
  calendar events and routines. Start reminders now ring `LEAD` (5 min) early. If that
  moment has passed but the item has not started, it rings at once. End-of-event check-ins
  stay on time.
- **Moved or edited items:** the schedule key carries the item's version (and for routines
  the real start), so the item gets a new schedule and a new briefing. A stale briefing is
  never read.
- **Briefing:** 10 min before the start (`PREPARE_BEFORE_START`, 5 min before the ring),
  the same sweep starts `BriefPreparer` in the background. It asks Lia one read-only
  question: the item, its details and its linked notes (`[[slug]]`), "what should I know
  or remember?". Lia does the search and the linked-node walk, through the same
  `ExistingLia` boundary Yggdras uses. If her answer cites a note marked sensitive, or she
  is unavailable, the briefing is written from the item alone (recorded in `failure`).
  Checking a cited note's sensitivity reads only that note, never a search. One Haiku call
  turns her answer into a spoken
  summary (≤3 sentences) and a context block (≤600 words, capped at 12k chars). The result
  is stored in `app.call_briefs` and pruned 6 h after its time.
- **The call:** the worker speaks the stored summary at once (no model call), then asks
  "Shall I mark it as started, or snooze it?". Replies use `Answerer`: Claude Haiku with
  the briefing as a cached system block and five tools (it never edits notes itself):
  - `confirm_start` starts the routine's task through the normal `execute_task` path, with
    history.
  - `snooze(minutes)` adds a snooze schedule that reuses the same briefing.
  - `ask_lia(question)`, the one backup lookup, for questions outside the briefing. It
    first says "Let me check with Lia, one moment." and then waits 6–15 s for Lia
    (read-only context, ≤3 spoken sentences, footnote lines dropped for speech). A cited
    sensitive note blocks the answer.
  - `hand_to_yggdras(request)` for anything else: his calendar, moving or adding events,
    tasks, new reminders, planning and suggestions. It says "One moment, I'll sort that
    out." and passes the request to `VoiceRuntime.turn`, the same full Yggdras role as a
    call he starts himself (calendar and task agents, Lia for knowledge). 10-30 s.
  - `end_call` hangs up.
- **Changes on a call:** Yggdras proposes; it reads each change back in one sentence and
  asks "Shall I?". The proposals wait on the call (`app.call_reviews`). A plain spoken
  yes applies them through the same `VoiceTools.execute` path as Accept in Calls; a plain
  no drops them. Each is noted on the call ("Applied: …" / "Declined: …"). While a change
  is waiting, a yes answers that change, not the reminder's own confirm.
- **Fallback:** if the briefing failed or is missing, a plain one is built from the item.
- **Calls you start yourself** use the full Yggdras role, now with Lia for knowledge
  (`LiaForVoice`, replacing `VoiceKnowledge`'s direct note search) and spoken-yes changes.
- **Ringing:**
  - Laptop: every open web/desktop window shows a phone-style incoming screen (`calls.css`).
  - Phone with the app open: the new `CallScreen`.
  - Phone with the app closed: Android's own call notification (needs Firebase).
  - The reason line ("Reminder · title") appears only to signed-in clients; push payloads
    stay generic.

**Replaceable pieces.** Each is one place in `call_briefs.py`: `LEAD`, `PREPARE_BEFORE_START`,
`BRIEF_MODEL`, `BriefStore`, `gather`, `write_brief`, `Answerer`, `ask_lia`. Delivery and voice
transport stay in `call_service.py` / `voice_worker.py`.

**Test one call.**
`python -m yggdress_app.call_briefs test [--event ID | --routine ID]`. It writes the
briefing now, prints what will be said, and rings on the next sweep.

## v3 (2026-11-20): planning by voice, outcomes, follow-ups

Plan and gap list: `planning/voice-calls-v3.md` (approved). Owner decisions: sensitive
notes may be used on every client (phone, desktop, web, voice); migration 014 adds
`app.item_outcomes`; retries 5 and 10 minutes after the first miss.

- **Sensitive notes:** no voice path filters them any more (`cites_sensitive` and
  `VoiceTools.linked` removed). Supersedes assumption 12.
- **Remove:** the reminder question is now "started, snooze, or remove". `remove_item` is
  read back ("Remove X? Shall I?"); yes removes an event, or skips a routine for that day
  only; no keeps it.
- **Outcomes** (`call_outcomes.py`, append-only `app.item_outcomes`): started, snoozed,
  removed, completed, not done, not answered, with who decided (voice, slot_end,
  after_retries, follow_up) and the call.
- **Retries:** a missed reminder (start, routine, snooze or retry) re-rings 5 and 10 min
  after the first miss with the same briefing; any answer cancels them. After both:
  an event counts completed, a routine not answered.
- **Slot end:** every event counts completed when it ends; a started task completes when
  its planned block (else its routine window) ends. Only slots ended in the last 2 h.
- **Follow-up:** the next call for a routine with an unanswered occurrence (14 days) opens
  "Before today's X: last time, on <day>, it went unanswered. Did you do it?" Yes marks it
  done; no gives a workload note (missed + today's minutes, minutes already planned today,
  one suggestion) and offers to start today's.
- **Planning by voice:** the calendar agent reads task blocks and, with `free_minutes`,
  free slots computed by `free_slots.py` (events, task blocks, routines; 08:00-22:00;
  10-min buffers). It can propose `block.create/update/remove`; an emergency is a
  priority-1 task in the earliest free slot, moving the lowest-priority block if needed
  (calendar-precision skill). Everything applies on a spoken yes.

## Edge cases (audited 2026-11-20, before daily use)

| Case | Behaviour | Where |
|---|---|---|
| A reminder comes due while Manoj is on a call | Not a second ring: the scheduler attaches it to the answered call; within 10 s the worker says "Pardon the interruption, sir. <summary> <question>" and puts that reminder in focus (yes, snooze, follow-ups, hand-off all work) | `call_service.tick`, `voice_worker.announce_due` |
| Two reminders at the same moment | The first rings; the second waits while it rings (≤45 s), then is announced in the call or rings next | same |
| The call ends before an attached reminder was spoken | It goes back to the queue: rings on its own, or shows as missed | `voice_worker.finish` |
| Laptop asleep, app off, voice worker down | A reminder more than 2 min overdue is never dropped silently: a still-current one becomes a "Missed Reminder · title" call in Calls (last 12 h only; removed items and quiet hours are not reported) | `call_service.record_late` |
| "Snooze 10 … no, 5" | The latest snooze replaces the earlier one: one ring, not two | `call_briefs.act` |
| End-of-event check-in | Says "<title> is due to end at HH:MM. Is there anything to note, change or plan next?"; no Lia prep (no paid call) | `call_briefs.is_end`, `end_summary`, `question` |
| Model, Lia, Yggdras or database error inside a turn | Spoken as "Sorry, sir, I ran into a problem with that. Could you try again?"; the call goes on | `livekit_adapter.answer_turn` |
| A hand-off to Yggdras or Lia takes over a minute | Turns may take 180 s (was 60/90 s, and prep took 72 s on the laptop) | `livekit_adapter.TURN_TIMEOUT` |
| Restarting the app | Each child is stopped with its whole process tree, and every stop step runs even if one fails (a `.venv` launcher's real interpreter, and a failing step, had left the brain service, voice worker and web server running, blocking the next start) | `local_runtime.stop_tree`, `quietly` |
| Lia slow or down during prep | Briefing from the item alone; the call still rings on time | `gather` |
| Item moved, edited or removed after prep | New schedule key and briefing; a removed item's ringing call ends | existing `seed_schedules` |
| Quiet hours (22:00-08:00) | No reminders, not reported as missed | existing |
| A change is waiting when the call ends | It stays in Calls for review | existing `call_reviews` |
| Typing in chat when a reminder is due | Not a call: the reminder rings as usual | existing |

## Assumptions

| # | Assumption | Status |
|---|---|---|
| 1 | Reminders are for calendar events and routine tasks (the items with a time); plain tasks with only a due date are not called | unconfirmed |
| 2 | Ring 5 min before the start; Lia asked 10 min before the start | confirmed (owner spec v2) |
| 3 | An item created less than 5 min before its start rings immediately | unconfirmed |
| 4 | Quiet hours 22:00–08:00 Europe/Berlin and one call at a time, as already set | confirmed (existing preferences) |
| 5 | "Yes" on an event only acknowledges it; on a routine whose task does not exist yet it also only acknowledges | unconfirmed |
| 6 | Snooze default 10 min, maximum 120 | unconfirmed |
| 7 | One Lia question per briefing; her answer capped at 8k chars, the context block at 12k | unconfirmed |
| 8 | Briefings are deleted 6 h after their time; transcripts are not kept; recording is off | confirmed (privacy rules) |
| 9 | In-call answers use Claude Haiku 5.5 through the existing Anthropic key (no new provider) | confirmed (summary choice) |
| 10 | Firebase setup (project + service-account file) is done by Manoj; until then, calls ring only where the app is open | confirmed |
| 11 | An item created less than 10 min ahead is prepared at once; if Lia has not finished when it rings, the call uses the plain fallback | unconfirmed |
| 12 | Sensitive notes may be used on every client, voice included | confirmed (owner, v3) |
| 13 | Lia is asked with her default model, through the existing `ExistingLia` subprocess (no new path) | confirmed (code: Yggdras already calls Lia this way) |
| 14 | Calls you start yourself use Lia for knowledge too (no direct note search left on any voice path) | confirmed (owner: hand off to Yggdras) |
| 15 | Reminder calls reach the calendar agent, Lia and reminders by handing the turn to the full Yggdras role | confirmed (owner) |
| 16 | A spoken yes applies the changes waiting on the call; a spoken no drops them; there is no spoken undo yet (fix in the calendar) | confirmed (yes applies) / unconfirmed (no spoken undo) |
| 17 | "Remind me at …" becomes a calendar event (which then rings 5 min early); there is no separate reminder type for Yggdras to create | unconfirmed |
| 18 | Anything other than a plain yes or no while a change waits goes back to Yggdras (it can revise the proposal) | unconfirmed |
| 19 | A reminder due during a call is announced in that call | confirmed (owner) |
| 20 | Missed reminders are reported for the last 12 h only, as missed calls in Calls (no push without Firebase) | unconfirmed |
| 21 | An unanswered reminder call is not retried; it shows as missed | unconfirmed |
| 22 | Retries 5 and 10 min after the first miss; after both, an event counts completed and a routine not answered | confirmed (owner) |
| 23 | Free-slot day 08:00-22:00 with 10-min buffers; emergency moves only task blocks, never events or essential work | unconfirmed |
| 24 | A declined call (pressed Decline) is not retried | unconfirmed |
| 25 | Slot-end completion only looks back 2 h (no backfill after the app was off longer) | unconfirmed |
| 26 | The phone rings as an in-app call via Firebase push (full-screen on the lock screen, same chime as desktop), not a real phone call | confirmed (owner, 2026-11-20) |
| 27 | Phone sign-ins last 30 days and renew with use (at most daily); desktop stays 8 h | confirmed (owner) |
| 28 | Laptop off or asleep: no reminders, no fallback alarms. Phone on but locked: it rings | confirmed (owner) |
| 29 | Answering away from the USB cable needs the backend reachable over the internet: the planned cloud move, which amends the private-by-default rule (D13) and is not built yet | open (owner to approve a plan) |
