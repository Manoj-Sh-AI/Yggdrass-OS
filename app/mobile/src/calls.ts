/** Ringing the phone. One interface, one implementation per platform.
 *
 * Android: the app API sends a high-priority FCM data message (FIREBASE_* keys on the server);
 * the app shows a full-screen call notification on a dedicated channel, Answer/Decline. That
 * needs a development build (not Expo Go) and google-services.json from Firebase.
 *
 * iPhone: deferred (Manoj, 2026-11-16). PushKit + CallKit go behind the same interface later.
 */
import * as Notifications from "expo-notifications";
import { Platform } from "react-native";
import { api } from "./api";

export interface Ringer {
  /** Ask for permissions, register this phone with the app API for pushes. */
  register(): Promise<void>;
  /** Show the incoming-call screen for a ring from the app API. */
  ring(call: { id: string; reason: string }): Promise<void>;
  stop(callId: string): Promise<void>;
}

const CHANNEL = "yggdras-calls";

class AndroidRinger implements Ringer {
  async register() {
    await Notifications.setNotificationChannelAsync(CHANNEL, {
      name: "Calls from Yggdras",
      importance: Notifications.AndroidImportance.MAX,
      vibrationPattern: [0, 600, 400, 600],
      lockscreenVisibility: Notifications.AndroidNotificationVisibility.PUBLIC,
      bypassDnd: false,
    });
    const { granted } = await Notifications.requestPermissionsAsync();
    if (!granted) throw new Error("Notifications are off, so Yggdras can't ring this phone.");
    const token = await Notifications.getDevicePushTokenAsync(); // the FCM token
    await api.registerDevice(String(token.data));
  }

  async ring(call: { id: string; reason: string }) {
    await Notifications.scheduleNotificationAsync({
      identifier: `call-${call.id}`,
      content: {
        title: "Yggdras is calling",
        body: call.reason,
        data: { callId: call.id },
        categoryIdentifier: "call",
        sticky: true,
      },
      trigger: { channelId: CHANNEL, seconds: 1 },
    });
  }

  async stop(callId: string) {
    await Notifications.dismissNotificationAsync(`call-${callId}`);
  }
}

class IosRinger implements Ringer {
  async register() {
    throw new Error("iPhone calls are not built yet (PushKit/CallKit, deferred).");
  }
  async ring() {}
  async stop() {}
}

export const ringer: Ringer = Platform.OS === "ios" ? new IosRinger() : new AndroidRinger();
