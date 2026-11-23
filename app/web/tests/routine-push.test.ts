import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";
import { expect, it, vi } from "vitest";

function browser(ok = true) {
  const listeners = new Map<string, (event: unknown) => void>();
  const showNotification = vi.fn(async () => {});
  const openWindow = vi.fn(async () => {});
  const fetch = vi.fn(async () => ({ ok }));
  runInNewContext(readFileSync("public/routine-sw.js", "utf8"), {
    self: {
      addEventListener: (name: string, fn: (event: unknown) => void) => listeners.set(name, fn),
      registration: {showNotification}, clients: {openWindow}
    }, fetch
  });
  async function fire(name: string, value: Record<string, unknown>) {
    let done;
    listeners.get(name)!({...value, waitUntil: (promise: Promise<void>) => { done = promise; }});
    await done;
  }
  return { fire, openWindow, showNotification, fetch };
}

const token = "a".repeat(32) + "." + "b".repeat(64);
it("renders generic notifications and acks actions from a closed tab", async () => {
  const b = browser();
  await b.fire("push", { data: {json: () => ({kind: "pre_task", token, title: "private example"})}});
  const shown = b.showNotification.mock.calls as unknown[][];
  expect(JSON.stringify(shown)).not.toContain("private example");
  expect(shown[0][1]).toMatchObject({actions: [{action:"started"},{action:"not_yet"}]});
  await b.fire("notificationclick", { notification: {close() {},data:{token}}, action:"started" });
  expect(b.fetch).toHaveBeenCalledWith("/api/backend/routine-delivery/respond", expect.objectContaining({
    credentials: "omit", body: JSON.stringify({token, action:"started"})
  }));
  expect(b.openWindow).not.toHaveBeenCalled();
});

it("offers the same one-tap page on a plain tap or failed background send", async () => {
  const b = browser(false);
  for (const action of ["", "not_yet"]) {
    await b.fire("notificationclick", { notification: {close() {},data:{token}}, action });
    expect(b.openWindow).toHaveBeenLastCalledWith("/routine-response#" + token);
  }
  await b.fire("notificationclick", { notification: {close() {},data:{target:"https://example.invalid/"}} });
  expect(b.openWindow).toHaveBeenLastCalledWith("/daily-routines");
});
