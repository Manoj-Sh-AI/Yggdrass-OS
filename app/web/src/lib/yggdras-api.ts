import { ApiError, applicationApi } from "./api";

/** A card waiting on Manoj: exactly what changes, and whether it can be undone. */
export type YggdrasCard = {
  id: string;
  tool: string;
  title: string;
  reasons: string[];
  offer: boolean;
  state: string;
  old_text: string | null;
  new_text: string | null;
  links_added: string[];
  links_removed: string[];
  warning: string;
};

export type YggdrasEvent =
  | { stage: string; source?: string }
  | { card: YggdrasCard }
  | { delta: string }
  | { done: string; route?: string; error?: string }
  | { error: string };

export type HubEvent =
  | { type: "hello" }
  | { type: "card"; card: YggdrasCard }
  | { type: "notification"; id: string; kind: string; title: string; body: string }
  | {
      type: "call";
      state: "ringing" | "answered" | "declined" | "ended";
      id: string;
      reason?: string;
      answered_by?: string;
    };

export type RoomAccess = { url: string; token: string; simulated: boolean };

let csrf: string | undefined;
async function token() {
  if (!csrf)
    csrf = (await applicationApi<{ csrf: string }>("auth/session")).csrf;
  return csrf;
}

/** Ask Yggdras; the reply streams back as events (stages, cards, text pieces, done). */
export async function askYggdras(
  text: string,
  history: { role: string; content: string }[],
  onEvent: (event: YggdrasEvent) => void,
  signal?: AbortSignal,
) {
  const response = await fetch("/api/backend/yggdras/requests", {
    method: "POST",
    credentials: "same-origin",
    cache: "no-store",
    signal,
    headers: {
      "Content-Type": "application/json",
      "X-Yggdress-CSRF": await token(),
    },
    body: JSON.stringify({ text, source: "chat", history: history.slice(-12) }),
  });
  if (!response.ok || !response.body) {
    const data = await response.json().catch(() => ({}));
    throw new ApiError(
      response.status,
      typeof data.detail === "string" ? data.detail : "Yggdras is unavailable.",
    );
  }
  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += value;
    let end: number;
    while ((end = buffer.indexOf("\n\n")) >= 0) {
      const chunk = buffer.slice(0, end);
      buffer = buffer.slice(end + 2);
      if (chunk.startsWith("data: ")) onEvent(JSON.parse(chunk.slice(6)));
    }
  }
}

export const yggdrasApi = {
  cards: () => applicationApi<YggdrasCard[]>("yggdras/cards"),
  approve: (id: string) =>
    applicationApi<{ done: boolean; undo: boolean }>(
      `yggdras/cards/${id}/approve`,
      { method: "POST", body: "{}" },
    ),
  reject: (id: string, correction = "") =>
    applicationApi(`yggdras/cards/${id}/reject`, {
      method: "POST",
      body: JSON.stringify({ correction }),
    }),
  undo: () => applicationApi("yggdras/undo", { method: "POST", body: "{}" }),
  runs: () => applicationApi<Record<string, unknown>[]>("yggdras/runs"),
  callYggdras: () =>
    applicationApi<RoomAccess & { id: string }>("calls", {
      method: "POST",
      body: "{}",
    }),
  answer: (id: string, device: string) =>
    applicationApi<RoomAccess>(`calls/${id}/answer`, {
      method: "POST",
      body: JSON.stringify({ device }),
    }),
  decline: (id: string) =>
    applicationApi(`calls/${id}/decline`, { method: "POST", body: "{}" }),
  end: (id: string, summary = "") =>
    applicationApi(`calls/${id}/end`, {
      method: "POST",
      body: JSON.stringify({ summary }),
    }),
};

/** Every open window listens: cards, notifications and rings arrive here. */
export function listen(onEvent: (event: HubEvent) => void) {
  const source = new EventSource("/api/backend/yggdras/events");
  source.onmessage = (message) => onEvent(JSON.parse(message.data));
  return () => source.close();
}
