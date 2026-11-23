# Android completion

Owner-authorized 16 November 2026 after the agent-layer review. Work from the
existing application and Brain API boundaries. Preserve unrelated uncommitted
database-consolidation changes. No hosting or memory-engine work.

## Sequence and acceptance

1. Check existing execution work is committed and secrets ignored. It is committed;
   both environment files are ignored. Brain is already configured for rows.
2. Replace the mobile scaffold with native Today, Tasks, Calendar, saved Chat and
   Settings screens over the existing versioned APIs. Preserve fixed goals and
   ask before starting a focus timer. Preserve drafts on errors.
3. Add revocable mobile bearer authentication using existing hashed application
   sessions and device SecureStore. Reuse login throttling and password rotation
   invalidation. WebView sessions remain mobile-restricted.
4. Use the existing Notes editor and graph in authenticated WebViews. Sensitive
   notes are excluded server-side for mobile sessions, including graph data.
5. Test authentication, permissions, persistence, calendar/task commands, chat
   send/resend/cancel and error recovery with invented data. Typecheck the phone
   app and produce an Android bundle. Verify a physical USB phone if available.
6. Voice and push stay behind the explicit credential STOP gate. Simulations must
   identify themselves; no Connected label without an actual transport connection.

## Gate observed

The private environment currently has none of LIVEKIT_URL, LIVEKIT_API_KEY,
LIVEKIT_API_SECRET, FIREBASE_PROJECT_ID or FIREBASE_SERVICE_ACCOUNT_FILE. The
mobile google-services.json is also absent. No speech spending is authorized by
this work; all testing remains scripted/simulated. Live calling and closed-phone
push cannot be certified until this owner-only gate is resolved.

## Research

- Expo authentication: secure storage and session restoration:
  https://docs.expo.dev/develop/authentication/
- SDK 54 release: https://expo.dev/changelog/sdk-54
- Android local compilation: https://docs.expo.dev/guides/local-app-development/
- Remote Android notifications require a development build:
  https://docs.expo.dev/versions/latest/sdk/notifications/
- LiveKit requires its native SDK and a development build, not only signed tokens:
  https://docs.livekit.io/transport/sdk-platforms/expo/

Keep the existing Expo SDK 54 baseline rather than mixing an unrelated SDK upgrade
into completion. Device authentication uses the existing application password;
Brain, database and provider credentials never reach the phone.
