# Yggdras mobile (Expo)

Status: scaffold, not yet installed, typechecked or run on a device.

## What is here

- **Sign-in:** to the app's own address.
- **Chat with Yggdras:** source `mobile`, with approval cards: Approve or Reject, the old and new text, and an irreversible warning.
- **Notes and Graph:** the web components, in a WebView.
- **Call Yggdras:** room access comes from the app API; it's simulated until the LiveKit keys exist.
- **Ringing:** an interface (`src/calls.ts`).
  - Android: an FCM full-screen call notification.
  - iPhone: deferred; the stub refuses clearly.

## Not built yet

- **Native screens:** Today, Tasks, Calendar and Settings (full parity).
- **LiveKit audio:** `@livekit/react-native`, once `LIVEKIT_*` keys exist.
- **The ringing push itself:** Answer/Decline actions from the lock screen; the Firebase project gives `google-services.json` and a service account (`FIREBASE_*`).
- **Mobile sign-in:** today it reuses the web session cookie; bearer tokens for the phone are a later step.

## Run (after `npm install`)

Calls need a development build, not Expo Go:

    npx expo run:android

No key or secret belongs in this folder. The phone gets short-lived access from the app API.
