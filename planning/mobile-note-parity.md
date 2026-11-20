# Desktop and phone Notes/Graph parity — 17 November 2026

## Cause and approved change

The live desktop catalogue had 82 notes and 190 graph connections. Mobile had 70
notes and 142 connections because the earlier brief explicitly excluded sensitive
notes from phone sync. The excluded 12 notes accounted for the 48 missing edges;
no database records were missing or lost.

The owner explicitly approved replacing that phone restriction with the desktop's
**Show** concealment. The installed owner runtime now sets
`mobile_sensitive_access: true`. New/unconfigured runtimes still default to the
restricted policy. This is a server setting; client headers cannot elevate it.
The same mobile bearer/WebView session boundary, CSRF protection and legacy-route
restrictions remain in place. Voice still excludes sensitive notes.

## Changes

- `app/api/src/yggdress_app/config.py`, `application.py`, `local_runtime.py`:
  explicit server-owned mobile access setting, applied to authenticated requests.
- `mobile_policy.py`, `notes_proxy.py`, `graph_proxy.py`: approved owner sessions
  use the same Brain HTTP catalogue and viewer as desktop, without dropping notes
  or incident graph edges. No Brain engine or storage changes.
- `app/web/src/lib/notes-catalogue.ts`, `notes-brain-provider.tsx`: searches select
  matches without replacing the full catalogue or losing backlink targets;
  refreshed catalogues preserve the fetched editing baseline and local drafts.
- `brain-explorer.tsx`: sensitive search excerpts and note context stay hidden
  until Show. Reload or selecting another note conceals the editor again.
- `brain-graph.tsx`, `app/mobile/src/embedded.tsx`, `App.tsx`: returning to a view
  or resuming the phone refreshes the catalogue/graph; Notes is refreshed through
  an event instead of reloading away an open draft. No credentials in injected JS.
- Native Settings privacy wording reflects the chosen policy. Android patch
  version 0.3.1 installed with existing data and sign-in preserved.

Show conceals content on screen; the owner-approved authenticated phone receives
the full note/graph payload, matching desktop. It is not a separate encryption
or per-note server authorization mechanism.

## Verification

- **Live running API: desktop 82 notes / 190 connections; mobile 82 / 190.**
  Aggregate-only verification wrote four integer counts; no private content files.
  Its short-lived application test sessions were removed afterward.
- 50 targeted PostgreSQL/API tests passed, including restricted defaults, approved
  desktop/mobile payload equality, preserved WebView restrictions, header-spoofing
  rejection and unchanged voice filtering. Fixtures were invented notes only.
- 129 web tests passed, including catalogue stability and editing-baseline tests.
- 27 mobile tests passed, including refresh without discarding a note draft;
  native typecheck passed.
- Packaged browser integration passed with desktop and phone sessions: identical
  note/graph payloads, hidden sensitive previews/context, explicit Show, concealment
  after reload, stable search totals, and draft preservation during refresh.
- Final Next production candidate `.next-parity-ready` built successfully.
  Initial candidate hit a Windows directory permission error; a fresh verified
  candidate resolved it. Python lint/format checks passed.
- Local upgrade backup/restore and staged verification passed; existing values
  and Brain fingerprints preserved. No new migration or Brain write was needed.
- Android build succeeded and A16 update returned Success. Package manager confirms
  version 0.3.1. Phone was locked afterward; the lock was respected and no personal
  screen contents were inspected. Final live counts were verified through the API.

APK: `app/mobile/dist/Yggdras-android.apk`, 50,007,710 bytes.
SHA256: `227094227c9a6357a19172ef81590f1983524839d3f3cc14da4d762be982a891`.
Test signing remains unchanged. No paid calls, hosting, credential changes, Brain
test writes or changes to the memory engine. Live calls/push remain disabled.

The broader live comparison was initially rejected by automatic approval review
over a possible sensitive-content report. It was replaced with the approved
aggregate-only check. No raw live payload report was created.
