import * as SecureStore from "expo-secure-store";
import { randomUUID } from "expo-crypto";
import { request } from "./api";
export type Call = {
  id: string;
  state: string;
  version: number;
  media_state: string;
  simulated: boolean;
  expires_at: string;
  created_at: string;
  answered_by: string;
  summary: string;
  reason?: string;
};
export type Capabilities = {
  mode: string;
  simulated: boolean;
  voice_ready: boolean;
  push_ready: boolean;
  worker_ready: boolean;
  missing: string[];
};
export type CallSnapshot = {
  calls: Call[];
  cursor: number;
  capabilities: Capabilities;
};
export type CallPreferences = {
  version: number;
  scheduled: boolean;
  calendar_starts: boolean;
  calendar_ends: boolean;
  routines: boolean;
  timezone: string;
  quiet_start: string;
  quiet_end: string;
};
const pending = new Map<string, string>();
export async function deviceId() {
  let value = await SecureStore.getItemAsync("yggdras.device.v1");
  if (!value) {
    value = randomUUID();
    await SecureStore.setItemAsync("yggdras.device.v1", value);
  }
  return value;
}
export async function callCommand<T>(path: string, data: object = {}) {
  const device = await deviceId();
  const fingerprint = JSON.stringify([path, data]);
  const key = pending.get(fingerprint) || randomUUID();
  pending.set(fingerprint, key);
  const result = await request<T>(`calls${path}`, {
    method: "POST",
    body: JSON.stringify({ key, device, ...data }),
  });
  pending.delete(fingerprint);
  return result;
}
export const callApi = {
  snapshot: () => request<CallSnapshot>("calls"),
  preferences: () => request<CallPreferences>("calls/preferences"),
  savePreferences: (body: CallPreferences) =>
    request("calls/preferences", { method: "PUT", body: JSON.stringify(body) }),
  schedule: async (data: { at?: string; minutes?: number }) => {
    const fingerprint = JSON.stringify(["schedule", data]);
    const key = pending.get(fingerprint) || randomUUID();
    pending.set(fingerprint, key);
    const result = await request("calls/schedule", {
      method: "POST",
      body: JSON.stringify({ key, ...data }),
    });
    pending.delete(fingerprint);
    return result;
  },
};
