/** The app API, as the phone uses it. The phone never holds a database, brain or LiveKit
 * secret: it signs in like the web app and receives short-lived room access per call. */
import * as SecureStore from "expo-secure-store";

export type Card = {
  id: string;
  title: string;
  offer: boolean;
  old_text: string | null;
  new_text: string | null;
  links_added: string[];
  links_removed: string[];
  warning: string;
};

let base = "";
let csrf = "";

export async function signIn(origin: string, password: string) {
  base = origin.replace(/\/$/, "");
  const response = await fetch(`${base}/api/backend/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Origin: base },
    body: JSON.stringify({ password }),
  });
  if (!response.ok) throw new Error("Sign-in failed.");
  csrf = (await response.json()).csrf;
  await SecureStore.setItemAsync("yggdras.origin", base);
}

async function call<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(`${base}/api/backend/${path}`, {
    method: body === undefined ? "GET" : "POST",
    headers: { "Content-Type": "application/json", Origin: base, "X-Yggdress-CSRF": csrf },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Failed.");
  return data as T;
}

export const api = {
  origin: () => base,
  /** Asks Yggdras (source: mobile). The reply arrives as server-sent events in one body. */
  ask: async (text: string) => {
    const response = await fetch(`${base}/api/backend/yggdras/requests`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Origin: base, "X-Yggdress-CSRF": csrf },
      body: JSON.stringify({ text, source: "mobile" }),
    });
    const raw = await response.text();
    const events = raw
      .split("\n\n")
      .filter((chunk) => chunk.startsWith("data: "))
      .map((chunk) => JSON.parse(chunk.slice(6)));
    return {
      answer: events.map((e) => e.delta || "").join(""),
      cards: events.filter((e) => e.card).map((e) => e.card as Card),
      error: events.find((e) => e.error)?.error as string | undefined,
    };
  },
  cards: () => call<Card[]>("yggdras/cards"),
  approve: (id: string) => call(`yggdras/cards/${id}/approve`, {}),
  reject: (id: string, correction = "") => call(`yggdras/cards/${id}/reject`, { correction }),
  undo: () => call("yggdras/undo", {}),
  registerDevice: (pushToken: string) =>
    call("yggdras/devices", { platform: "android", push_token: pushToken, label: "phone" }),
  answer: (id: string) =>
    call<{ url: string; token: string; simulated: boolean }>(`calls/${id}/answer`, { device: "phone" }),
  decline: (id: string) => call(`calls/${id}/decline`, {}),
  callYggdras: () => call<{ id: string; url: string; token: string; simulated: boolean }>("calls", {}),
};
