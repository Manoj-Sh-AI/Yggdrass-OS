/** Only application session credentials live on the phone. Never Brain/provider keys. */
import * as SecureStore from "expo-secure-store";
import { randomUUID } from "expo-crypto";
import type {
  Session,
  Snapshot,
  Conversation,
  History,
  Catalog,
  Attachment,
} from "./types";

const SESSION_KEY = "yggdras.mobile.session.v1";
let current: Session | null = null;
const pending = new Map<string, string>();
const expiredListeners = new Set<() => void>();
const sessionListeners = new Set<() => void>();
export function onSessionChanged(listener: () => void) {
  sessionListeners.add(listener);
  return () => {
    sessionListeners.delete(listener);
  };
}

export function onSessionExpired(listener: () => void) {
  expiredListeners.add(listener);
  return () => {
    expiredListeners.delete(listener);
  };
}
export function sessionExpired() {
  for (const listener of expiredListeners) listener();
}
export class MobileError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}
export function validOrigin(value: string) {
  const url = new URL(value.trim());
  if (
    url.username ||
    url.password ||
    url.search ||
    url.hash ||
    url.pathname !== "/"
  )
    throw new Error(
      "Enter just the application address, without a path or credentials.",
    );
  if (
    url.protocol !== "https:" &&
    !(
      url.protocol === "http:" &&
      ["localhost", "127.0.0.1", "[::1]"].includes(url.hostname)
    )
  )
    throw new Error(
      "Use HTTPS. Local USB testing can use http://127.0.0.1 with port forwarding.",
    );
  return url.origin;
}
export function session() {
  return current;
}
export async function restore() {
  current = null;
  const saved = await SecureStore.getItemAsync(SESSION_KEY);
  if (!saved) return null;
  try {
    const value = JSON.parse(saved) as Session;
    validOrigin(value.origin);
    if (
      !/^[A-Za-z0-9_-]{40,100}$/.test(value.token) ||
      !Number.isFinite(Date.parse(value.expires_at)) ||
      Date.parse(value.expires_at) <= Date.now()
    )
      throw new Error();
    current = value;
    await request("auth/session");
    return current;
  } catch (failure) {
    if (
      (failure instanceof MobileError && failure.status === 401) ||
      !current
    ) {
      current = null;
      await SecureStore.deleteItemAsync(SESSION_KEY);
    } else throw failure;
    return null;
  }
}
export async function signIn(origin: string, password: string) {
  const base = validOrigin(origin);
  const response = await fetch(`${base}/api/backend/mobile/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Origin: base },
    body: JSON.stringify({ password }),
  });
  const data = await decode(response);
  const value = {
    origin: base,
    token: data.token as string,
    expires_at: data.expires_at as string,
  };
  await SecureStore.setItemAsync(SESSION_KEY, JSON.stringify(value));
  current = value;
  for (const listener of sessionListeners) listener();
  return value;
}
async function decode(response: Response) {
  const data = await response.json().catch(() => ({
    detail: "The application returned an unreadable response.",
  }));
  if (!response.ok)
    throw new MobileError(
      response.status,
      typeof data.detail === "string"
        ? data.detail
        : "The request failed. Your draft is still here.",
    );
  return data;
}
export async function request<T = unknown>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  if (!current) throw new MobileError(401, "Sign in to continue.");
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 30000);
  try {
    return (await decode(
      await fetch(`${current.origin}/api/backend/${path}`, {
        ...init,
        signal: init.signal || controller.signal,
        headers: {
          "Content-Type": "application/json",
          Origin: current.origin,
          Authorization: `Bearer ${current.token}`,
          ...init.headers,
        },
      }),
    )) as T;
  } catch (failure) {
    if (failure instanceof MobileError) {
      if (failure.status === 401) sessionExpired();
      throw failure;
    }
    throw new MobileError(
      0,
      "Cannot reach your application. Check the connection and retry; your draft is still here.",
    );
  } finally {
    clearTimeout(timeout);
  }
}
/** Reuse a receipt after an interrupted response so a retry cannot duplicate a write. */
export async function command<T = unknown>(
  path: string,
  operation: string,
  data: object = {},
  id?: string,
  version?: number,
) {
  const values = {
    [path === "application/planning/commands" ? "op" : "operation"]: operation,
    data,
    id,
    version,
  };
  const fingerprint = JSON.stringify([path, values]);
  let key = pending.get(fingerprint);
  if (!key) {
    key = randomUUID();
    pending.set(fingerprint, key);
  }
  const result = await request<T>(path, {
    method: "POST",
    body: JSON.stringify({ key, ...values }),
  });
  pending.delete(fingerprint);
  return result;
}
export const api = {
  planning: (
    start: string,
    end: string,
    timezone: string,
    signal?: AbortSignal,
  ) =>
    request<Snapshot>(
      `application/planning?${new URLSearchParams({ start, end, timezone })}`,
      { signal },
    ),
  plan: (operation: string, data: object = {}, id?: string, version?: number) =>
    command("application/planning/commands", operation, data, id, version),
  time: (operation: string, data: object = {}, id?: string, version?: number) =>
    command("application/time/commands", operation, data, id, version),
  conversations: (q = "", before?: string, archived = false) =>
    request<{ conversations: Conversation[]; next: string | null }>(
      `chat/conversations?${new URLSearchParams({ q, archived: String(archived), ...(before ? { before } : {}) })}`,
    ),
  history: (id: string, before?: number) =>
    request<History>(
      `chat/conversations/${id}${before ? `?before=${before}` : ""}`,
    ),
  chat: <T = unknown>(
    operation: string,
    data: object = {},
    id?: string,
    version?: number,
  ) => command<T>("chat/commands", operation, data, id, version),
  catalog: () => request<{ catalog: Catalog }>("chat/capabilities"),
  export: (id: string) => request(`chat/conversations/${id}/export`),
  reviews: () =>
    request<{
      reviews: {
        id: string;
        version: number;
        agent_id: string;
        blocked: string;
        current: Record<string, unknown> | null;
        payload: {
          operation: string;
          data: Record<string, unknown>;
          explanation: string;
        };
      }[];
    }>("application/agents/reviews"),
  resolve: async (
    id: string,
    version: number,
    decision: "accept" | "dismiss",
  ) => {
    const fingerprint = JSON.stringify([id, version, decision]);
    let key = pending.get(fingerprint);
    if (!key) {
      key = randomUUID();
      pending.set(fingerprint, key);
    }
    const result = await request("application/agents/reviews/resolve", {
      method: "POST",
      body: JSON.stringify({ key, id, version, decision }),
    });
    pending.delete(fingerprint);
    return result;
  },
  upload: (
    conversation: string,
    file: { name: string; mimeType?: string; uri: string; size?: number },
    bytes: ArrayBuffer,
    uploadId: string,
  ) => {
    if (bytes.byteLength > 10 * 1024 * 1024)
      throw new Error("Choose a file smaller than 10 MB.");
    return request<Attachment>(
      `chat/attachments?${new URLSearchParams({ conversation_id: conversation, name: file.name, upload_id: uploadId })}`,
      {
        method: "POST",
        headers: { "Content-Type": "application/octet-stream" },
        body: bytes,
      },
    );
  },
  registerDevice: (pushToken: string) =>
    request("calls/devices", {
      method: "POST",
      body: JSON.stringify({
        platform: "android",
        push_token: pushToken,
        label: "phone",
      }),
    }),
  logout: async () => {
    try {
      await request("auth/logout", { method: "POST", body: "{}" });
    } catch (error) {
      if (!(error instanceof MobileError && error.status === 401)) throw error;
    }
    current = null;
    pending.clear();
    await SecureStore.deleteItemAsync(SESSION_KEY);
    await SecureStore.deleteItemAsync("yggdras.push.enabled");
    await SecureStore.deleteItemAsync("yggdras.push.device");
  },
};
