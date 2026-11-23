/** Push contains a call UUID, state and expiry; never private note content. */
import * as Notifications from "expo-notifications";
import * as SecureStore from "expo-secure-store";
import Constants from "expo-constants";
import { NativeModules, Platform } from "react-native";
import { api, request } from "./api";
let registration = Promise.resolve();
async function rememberToken(value: string, explicit = false) {
  const operation = registration
    .catch(() => {})
    .then(async () => {
      if (!explicit && await SecureStore.getItemAsync("yggdras.push.enabled") !== "true") return;
      const previous = await SecureStore.getItemAsync("yggdras.push.device");
      const next = (await api.registerDevice(value)) as { id: string };
      await SecureStore.setItemAsync("yggdras.push.device", next.id);
      if (previous && previous !== next.id)
        await request(`calls/devices/${previous}`, { method: "DELETE" });
    });
  registration = operation;
  return operation;
}
export const ringer = {
  async register() {
    if (Platform.OS !== "android")
      throw new Error("iPhone calling is deferred.");
    if (!Constants.expoConfig?.extra?.firebaseConfigured)
      throw new Error("Firebase is not configured in this Android build yet.");
    // The native side owns the call channel (custom chime, Do Not Disturb respected).
    NativeModules.YggdrasCalls?.ensureCallChannel();
    if (!(await Notifications.requestPermissionsAsync()).granted)
      throw new Error(
        "Notifications are off. Enable them in Android settings when you want incoming calls.",
      );
    await Notifications.setNotificationCategoryAsync("yggdras-call", [
      {
        identifier: "answer",
        buttonTitle: "Answer",
        options: { opensAppToForeground: true },
      },
      {
        identifier: "decline",
        buttonTitle: "Decline",
        options: { opensAppToForeground: true },
      },
    ]);
    const token = await Notifications.getDevicePushTokenAsync();
    await rememberToken(String(token.data), true);
    await SecureStore.setItemAsync("yggdras.push.enabled", "true");
  },
  async disable() {
    await SecureStore.deleteItemAsync("yggdras.push.enabled");
    await registration.catch(() => {});
    const id = await SecureStore.getItemAsync("yggdras.push.device");
    if (id) await request(`calls/devices/${id}`, { method: "DELETE" });
    await SecureStore.deleteItemAsync("yggdras.push.enabled");
    await SecureStore.deleteItemAsync("yggdras.push.device");
  },
  async stop(callId: string) {
    NativeModules.YggdrasCalls?.cancelCallNotification(callId);
    await Notifications.dismissNotificationAsync(`call-${callId}`);
  },
  listen(update: (url?: string) => void) {
    const token = Notifications.addPushTokenListener((value) => {
      void SecureStore.getItemAsync("yggdras.push.enabled")
        .then((enabled) => {
          if (enabled === "true") return rememberToken(String(value.data));
        })
        .catch(() => {});
    });
    const received = Notifications.addNotificationReceivedListener(() =>
      update(),
    );
    const response = Notifications.addNotificationResponseReceivedListener(
      (value) => {
        const id = value.notification.request.content.data?.callId;
        const action = value.actionIdentifier;
        if (
          typeof id === "string" &&
          /^[a-f0-9-]{36}$/i.test(id) &&
          ["answer", "decline"].includes(action)
        )
          update(`yggdras://calls/${id}?action=${action}`);
      },
    );
    if (Platform.OS === "android") NativeModules.YggdrasCalls?.ensureCallChannel();
    void ringer.reconcile().catch(() => {});
    return () => {
      token.remove();
      received.remove();
      response.remove();
    };
  },
  async reconcile() {
    if (await SecureStore.getItemAsync("yggdras.push.enabled") === "true" && (await Notifications.getPermissionsAsync()).granted && Constants.expoConfig?.extra?.firebaseConfigured) {
      const value=await Notifications.getDevicePushTokenAsync();await rememberToken(String(value.data));
    }
  },
  /** Ring with the Yggdras chime while the app is open (skipped if a push is already ringing). */
  ringInApp(callId: string, expiresAt: string) {
    const at = Date.parse(expiresAt);
    if (Platform.OS === "android" && Number.isFinite(at))
      NativeModules.YggdrasCalls?.ringInApp(callId, at);
  },
  /** Show the app over the lock screen only while an answered call is open. */
  overLockScreen(value: boolean) {
    if (Platform.OS === "android")
      NativeModules.YggdrasCalls?.showOverLockScreen(value);
  },
  fullScreenSettings() {
    NativeModules.YggdrasCalls?.openFullScreenSettings();
  },
};
