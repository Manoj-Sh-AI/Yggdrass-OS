# Mobile app and calls with Yggdras: plan

Status: proposed, 2026-11-16. Waiting for Manoj's approval; nothing is built yet.

## Decisions (Manoj, 2026-11-16)

- One set of databases serves web, desktop and phone. Manoj deploys; this build targets
  the local environment, with every host, URL and key coming from configuration.
- A call is a voice call with **Yggdras, the manager** (the existing Yggdras agent role).
- **Mobile:** Expo React Native, Android and iPhone, with full parity with the web app.
- **Voice:** LiveKit Cloud on the free Build plan; speech through LiveKit Inference.
- **Yggdras rings when:**
  - you call him;
  - at scheduled check-ins: calendar starts and ends, and routine times;
  - when asked to ring later ("call me at 6pm").
- **Every open client rings:** web, desktop (which shows the web app) and phone.

## Architecture

```
phone (Expo) ─┐                      ┌─ LiveKit Cloud (media, Inference STT/TTS)
web / desktop ┼─ HTTPS ─ app API ────┤
              │  (FastAPI)           ├─ voice agent worker (LiveKit Agents, Python)
              │    │                 │     └─ Yggdras role (Claude) + its tools
              │    ├─ app database   └─ Temporal: call schedules, retries, "5 more minutes"
              │    └─ brain API (PR #44), never touched by clients directly
              └─ push: FCM (Android) / APNs VoIP (iPhone), for ringing a closed app
```

- **Only the app API talks to anything.**
  - Clients never hold LiveKit secrets, database credentials or brain credentials.
  - The app API mints short-lived LiveKit room tokens per call.
- **One ring, many devices.** A call is a row: `ringing → answered | declined | missed`.
  - The app API fans the ring out to every live web or desktop session (server-sent events) and to every registered phone (push).
  - The first device to answer takes the call; the others stop ringing.
- **The voice agent** is a LiveKit Agents worker. It takes:
  - LiveKit Inference for listening and speaking;
  - the existing Yggdras role and tools (calendar, tasks, current work, recent activity) for thinking.

  After each call it saves a short structured summary, so the next call continues from there.
- **Scheduling** runs on Temporal (already approved for agent execution):
  - check-in rules on calendar events and routines;
  - one-off "call me at …";
  - "give me five minutes" as a re-ring.
- **Testing costs nothing.** A simulated conversation transport replaces LiveKit and the models, so tests never pay for voice (as your planning note asks).

## Steps

1. **Contract and backend:**
   - mobile login (bearer tokens beside today's web session);
   - device registry (push tokens);
   - the call model and endpoints, with LiveKit token minting;
   - ring fan-out (server-sent events plus push), call history and summaries;
   - the Temporal schedules;
   - migrations for the app database only.
2. **Voice agent worker:** LiveKit Agents, Inference speech, the Yggdras role as the brain, interruption handling, the post-call summary; plus the simulated transport for tests.
3. **Web and desktop:**
   - a Call Yggdras button;
   - a full-window incoming-call overlay that rings in every open tab, answer/decline, in-call controls and call history;
   - the desktop shell (WebView2) grants microphone permission to the app's own origin only.
4. **Mobile app** (`app/mobile`, Expo with a development build, since calls can't run in Expo Go):
   - sign-in, Today, Chat, Tasks/Kanban, Calendar, Settings and quick memory capture;
   - Notes: the BlockNote editor in a WebView;
   - Graph: the existing viewer in a WebView;
   - native calls: CallKit and PushKit on iPhone; a full-screen call notification on Android through FCM, with ConnectionService;
   - LiveKit React Native for audio.
5. **Verification:**
   - API and scheduler unit tests;
   - Playwright: two open tabs both ring and the first answer stops the other, with the simulated conversation;
   - mobile unit tests;
   - a manual device checklist for locked, background and closed phones, both platforms.

## What I need from you before steps 2–4 can run for real

I can't create accounts or enter credentials; everything is built and tested against simulated services until these are in `.env`:

- **LiveKit Cloud:** a free Build project (URL, API key and secret).
- **Firebase:** a project for Android push (`google-services.json` and a server key).
- **Apple:** a Developer account ($99/year) for iPhone VoIP push and installs (APNs key, team ID, bundle ID).
- **Expo:** an account, for EAS builds of the development app.

## Open points to settle with you

- **Uncommitted work:** the Temporal agent execution in this folder is uncommitted on branch `lia-restore`. I'd build on a new branch on top of it, so it has to be committed first; it's yours to commit.
- **D13 when you deploy:** a hosted database amends D13 (and D44 for the brain). That decision is yours at deploy time; this build changes nothing about where data lives.
- **Decision numbering:** settled 2026-11-16: the Notes HTTP adapter record is now `D45-notes-http-proxy.md`; the brain keeps D43/D44.
- **Sensitive notes:** your planning note says they must never reach the phone or a cloud model without your consent. Calls and the phone app will exclude `sensitivity: high` content unless you change that.
- **Ringing while closed is best-effort:** Android and iOS both limit background ringing; the device checklist will show where it falls short.
