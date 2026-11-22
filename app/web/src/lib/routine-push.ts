import { applicationApi } from "@/lib/api";

export type RoutinePushStatus = {
  configured: boolean;
  public_key: string;
  subscribed: boolean;
};

export function routinePushStatus() {
  return applicationApi<RoutinePushStatus>("routine-delivery/status");
}

export async function enableRoutinePush() {
  if (
    !window.isSecureContext ||
    !("serviceWorker" in navigator) ||
    !("Notification" in window) ||
    !("PushManager" in window)
  ) {
    throw new Error(
      "Open this app over HTTPS. On iPhone, add it to your Home Screen and open it there.",
    );
  }
  // Safari requires a direct gesture; request permission before the first network await.
  if ((await Notification.requestPermission()) !== "granted") {
    throw new Error(
      "Allow notifications in this browser to receive reminders.",
    );
  }
  const { configured, public_key } = await routinePushStatus();
  if (!configured) throw new Error("Web Push is awaiting configuration.");
  await navigator.serviceWorker.register("/routine-sw.js", { scope: "/" });
  const worker = await navigator.serviceWorker.ready;
  const key = Uint8Array.from(
    atob(public_key.replace(/-/g, "+").replace(/_/g, "/")),
    (c) => c.charCodeAt(0),
  );
  const existing = await worker.pushManager.getSubscription();
  const sub =
    existing ||
    (await worker.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: key,
    }));
  const { endpoint, keys } = sub.toJSON();
  await applicationApi("routine-delivery/subscribe", {
    method: "POST",
    body: JSON.stringify({ endpoint, keys }),
  });
}

export async function disableRoutinePush() {
  await applicationApi("routine-delivery/unsubscribe", {
    method: "POST",
    body: "{}",
  });
  if (!("serviceWorker" in navigator)) return;
  const worker = await navigator.serviceWorker.getRegistration("/");
  const sub = await worker?.pushManager.getSubscription();
  if (sub) await sub.unsubscribe();
}
