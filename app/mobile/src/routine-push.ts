import * as Notifications from "expo-notifications";
import * as SecureStore from "expo-secure-store";
import Constants from "expo-constants";
import { Linking, Platform } from "react-native";
import { onSessionChanged, request } from "./api";

const ENABLED = "yggdras.routine.push.enabled";
const DEVICE = "yggdras.routine.push.device";
let registration = Promise.resolve();

type Status = { configured: boolean; registered: boolean };

async function registerToken(token: string, explicit = false) {
  const operation = registration.catch(() => {}).then(async () => {
    if (!explicit && (await SecureStore.getItemAsync(ENABLED)) !== "true") return;
    const previous = await SecureStore.getItemAsync(DEVICE);
    const current = await request<{ id: string }>("routine-delivery/android/devices", {
      method: "POST",
      body: JSON.stringify({ push_token: token }),
    });
    await SecureStore.setItemAsync(DEVICE, current.id);
    if (previous && previous !== current.id)
      await request(`routine-delivery/android/devices/${previous}`, { method: "DELETE" });
  });
  registration = operation;
  return operation;
}

async function reconcile() {
  if (
    Platform.OS !== "android" ||
    (await SecureStore.getItemAsync(ENABLED)) !== "true" ||
    !(await Notifications.getPermissionsAsync()).granted ||
    !Constants.expoConfig?.extra?.firebaseConfigured
  ) return;
  const token = await Notifications.getDevicePushTokenAsync();
  await registerToken(String(token.data));
}

export const routinePush = {
  status: () => request<Status>("routine-delivery/android/status"),
  enabled: async () => (await SecureStore.getItemAsync(ENABLED)) === "true",
  async enable() {
    if (Platform.OS !== "android") throw new Error("Android reminders are available first.");
    if (!Constants.expoConfig?.extra?.firebaseConfigured)
      throw new Error("This phone build does not contain the Firebase configuration.");
    if (!(await Notifications.requestPermissionsAsync()).granted)
      throw new Error("Allow notifications in Android settings to receive reminders.");
    const token = await Notifications.getDevicePushTokenAsync();
    await registerToken(String(token.data), true);
    await SecureStore.setItemAsync(ENABLED, "true");
  },
  async disable() {
    await registration.catch(() => {});
    const id = await SecureStore.getItemAsync(DEVICE);
    if (id) await request(`routine-delivery/android/devices/${id}`, { method: "DELETE" });
    await SecureStore.deleteItemAsync(DEVICE);
    await SecureStore.deleteItemAsync(ENABLED);
  },
  async test() {
    const id = await SecureStore.getItemAsync(DEVICE);
    if (!id) throw new Error("Enable daily reminders before sending a test.");
    return request<{ sent: boolean }>("routine-delivery/android/test", {
      method: "POST",
      body: JSON.stringify({ device_id: id }),
    });
  },
  listen(onOpen: () => void, onError: (message: string) => void) {
    const handled = new Set<string>();
    async function link(url: string | null) {
      const match = url?.match(
        /^yggdras:\/\/routine\/([a-f0-9-]{36})\?action=(open|started|not_yet)$/i,
      );
      if (!match) return;
      const key = `${match[1]}:${match[2]}`;
      if (handled.has(key)) return;
      handled.add(key);
      onOpen();
      if (match[2] === "open") return;
      try {
        await request("routine-delivery/android/respond", {
          method: "POST",
          body: JSON.stringify({ delivery_id: match[1], action: match[2] }),
        });
      } catch (error) {
        handled.delete(key);
        onError(error instanceof Error ? error.message : "Could not record your response.");
      }
    }
    const url = Linking.addEventListener("url", ({ url }) => void link(url));
    void Linking.getInitialURL().then(link).catch(() => {});
    const token = Notifications.addPushTokenListener((value) => {
      void registerToken(String(value.data)).catch(() => {});
    });
    const changed = onSessionChanged(() => void reconcile().catch(() => {}));
    void reconcile().catch(() => {});
    return () => {
      url.remove();
      token.remove();
      changed();
    };
  },
};
