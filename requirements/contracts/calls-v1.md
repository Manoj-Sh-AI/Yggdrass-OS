# Application calls v1

Approved scope: Android and existing web/desktop shell; application-only storage,
existing Yggdras role, LiveKit media, Firebase Android delivery. Live activation is
off until explicitly configured. Development verification uses silent simulated
transport, disposable records, and no paid model/speech calls.

## Ownership and authentication

`app.calls` is the call state authority. `app.call_events` records lifecycle
changes; `app.call_delivery` is the retryable push outbox. Preferences, command
receipts, device registrations and proposed changes remain in `app`. No Brain
schema migration or raw audio/transcript storage. Summaries stay in application
storage. Brain context is read through the existing HTTP proxy, with sensitive
content excluded before model use; unreadable provenance fails closed.

All `/v1/calls` routes require the existing cookie+CSRF or mobile bearer session.
Room access is scoped to the authenticated winning session and device, with
microphone-only publication. Registration is tied to session expiry and password
generation; logout revokes it. Provider credentials never reach either client.

## API and lifecycle

- `GET /v1/calls`: calls, durable event cursor and capability flags.
- `GET /v1/calls/events`: authenticated SSE snapshots; reconnect reloads state.
- `GET /v1/calls/capabilities`: disabled/simulated/live mode and service readiness.
- `POST /v1/calls`: start an outgoing call using a retry key and device identity.
- `POST /v1/calls/{id}/answer|decline|end`: retry-safe lifecycle commands.
- `POST /v1/calls/{id}/media`: winning device reports versioned transport state.
- `GET|PUT /v1/calls/preferences`: versioned timezone, quiet hours and source choices.
- `POST /v1/calls/schedule`: future offset-aware instant or snooze minutes.
- `POST /v1/calls/devices`, `DELETE /v1/calls/devices/{id}`: register/revoke Android push.
- `GET /v1/calls/reviews`, `POST /v1/calls/reviews/{id}`: explicit versioned decisions.
- `POST /v1/calls/simulation`: available only in explicit simulated mode.

Ringing invitations expire after 45 seconds. First answer wins transactionally;
other devices reconcile and dismiss. Answered means accepted, not connected:
connected requires actual room, agent presence and enabled microphone. Calls have
a one-hour safety limit. SDK reconnect handles transient network loss. After a
client process is lost, end the prior call explicitly and start another; never
silently create a competing connection. Expired sessions close access.

## Scheduling and delivery

Default source preferences enable calendar starts/ends and routine windows, with
quiet hours **22:00–08:00 Europe/Berlin**. All remain inert in disabled mode.
Existing Temporal runs the durable check-in sweep, wakes on application changes,
and reconciles source versions/cancellation before ringing. Stale appointments
are not replayed after an outage. Routine scheduling does not require opening
Today first. Goal content and human focus time are never rewritten by check-ins.

Push contains only call UUID, lifecycle state and expiry: no titles, notes or
secrets. Delivery is at least once, with bounded retries and client-side UUID /
expiry deduplication. Revoked/expired/invalid tokens are excluded. Answer actions
revalidate current server state. Android uses CallStyle notification, optional
full-screen display, explicit microphone permission and a foreground microphone
service during media. It does not bypass device unlocking, DND, notification
permissions, battery policies or Android force-stop restrictions.

## Model actions and limitations

Voice reuses the existing Yggdras coordinator with constrained application tools.
Changes are proposals, followed by explicit approval/rejection and the existing
version/conflict checks. No automatic Brain writes or new memory engine. Paid
model steps have no automatic retry. The worker waits for the authenticated human
participant before greeting. Connection/worker failures remain visible.

Local APIs and workers require the laptop awake. No hosting, iPhone transport,
store release signing, native Telecom integration or real locked-phone delivery
certification is part of this package. Live service tests await owner setup.
