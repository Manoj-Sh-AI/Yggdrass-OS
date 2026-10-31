# Future: the executive layer and Lia

> Status: **parked ideas, not decisions.** Captured from a planning
> conversation on 2026-10-31. Memory comes first (see
> `intent/big-picture.md`); nothing here is built until the memory rung
> passes its hard eval. Items marked **Conflict** need a register decision
> before they can be adopted.

## The goal

Yggdras should keep working when the laptop is off: plan the day, track
current work, remind, and **call** the owner at the right moment with
enough context to say what to do next. The assistant's voice is called
**Lia**.

First milestone (proposed):

> Yggdras can plan the day, track current work, and call at the right
> time with enough context to say what to do next.

## Three layers

1. **Brain layer:** the Markdown brain and the librarian, as today.
2. **Executive layer:** runs all the time. Calendar, tasks, scheduling
   rules, reminders, and Lia's calls.
3. **Interaction layer:** the same dashboard, calendar, tasks and
   activity history on laptop and phone.

## Working memory vs long-term memory

- **Working memory:** active tasks, recent progress, pending decisions,
  what is happening now. Small, always current, synced across devices.
- **Long-term memory:** the Markdown brain (concepts, relationships,
  experiences, preferences). Integrated gradually.
- **Current Context Service:** keeps a compact, up-to-date summary of
  active commitments. Routine calls read this, not the whole brain, so
  they stay fast and cheap. Long-term memories are fetched only when a
  call needs them.

## What Lia needs on a call (first version)

1. **Calendar:** what's on today, what's next, how much time is free.
2. **Tasks:** pending, in progress, overdue, done.
3. **Current work:** what's being worked on, where it stopped, what's
   left, the next step.
4. **Recent activity:** what changed since the last conversation.

Example: "Your coding session is complete. The memory retrieval tests are
done; logging is still pending. Your German lesson starts now. I
recommend saving and switching." If the answer is "give me five
minutes", the extension is recorded and Lia calls again when it ends.

After every call, Lia saves a short structured summary of what was
agreed, so the next call continues from there.

## Calls: cheapest first

| Option | Cost | Notes |
|---|---|---|
| High-priority push notification that opens a voice chat | cheapest | start here |
| In-app incoming call screen (like WhatsApp) | near zero call cost | full-screen, Lia's name, answer / decline |
| Real phone call (e.g. Twilio) | most expensive | not planned |

Pieces needed for a call:
1. **Scheduler:** decides when Lia calls.
2. **Push delivery** (e.g. Firebase Cloud Messaging): wakes the phone
   app even when the laptop is off.
3. **Android call screen:** Android restricts full-screen calls and
   background work; ringing in every phone state can't be guaranteed.
4. **Voice API:** connects microphone and speaker to Lia once answered.

Rule: the cloud starts the call, Android rings, the voice API talks. One
job each. Test the whole reminder-to-call flow with a **simulated
conversation** first, so tests cost nothing in AI voice usage.

## Capturing memories from the phone

- Example: "Remember that I want to practise German every evening."
- **Capture is separate from integration.** The phone saves a proposed
  memory with its source right away (nothing is lost if the librarian
  is unavailable); the librarian files it into the right note later,
  after approval. This matches the existing inbox + approval rule.
- Needs versioning and conflict handling when laptop and phone change
  the same information.

## Proposed build order (from the conversation)

1. Shared responsive interface for laptop and phone.
2. Synced tasks and calendar.
3. Reliable notifications and scheduling.
4. Connect the Markdown librarian through an API.
5. Phone-to-brain memory capture.
6. Lia's voice and the incoming-call experience.

## Conflicts and open questions

- **Conflict, D13 (brain is never a cloud-queryable store):** the
  conversation proposed syncing the brain to encrypted cloud storage so a
  cloud librarian can answer when the laptop is off. That is exactly what
  D13 forbids. Options: keep D13 and accept that brain answers need the
  laptop online (calls still work from working memory); or amend D13 for
  a narrow, encrypted, owner-controlled subset. Decide before building.
- **Conflict, tech stack:** suggested Next.js, FastAPI, PostgreSQL,
  Kotlin and Firebase. The plan so far says a Tauri desktop app and
  SQLite. Treat the suggestions as options, not decisions.
- **Privacy:** sensitive notes must never reach the phone or a cloud
  model unless the owner allows it (see the governance / sensitivity
  question still open).
- **Open:** detect current work automatically from the development
  environment, or tell Lia manually? Deferred; assume manual for now.
- **Open:** real working-memory format and where it lives.
