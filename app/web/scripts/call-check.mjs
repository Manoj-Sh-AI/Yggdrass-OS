// Runs only against the explicit disposable phone fixture, never the owner's app.
import { chromium, expect } from "@playwright/test";
import { readFile, writeFile } from "node:fs/promises";
import { randomUUID } from "node:crypto";
import { fileURLToPath } from "node:url";
const cache = new URL("../../mobile/.cache/", import.meta.url);
const fixture = JSON.parse(
  await readFile(new URL("device-fixture-state.json", cache), "utf8"),
);
if (
  !fixture.ready ||
  fixture.origin !== "http://127.0.0.1:3300" ||
  fixture.data !== "invented only"
)
  throw new Error("Start the isolated phone fixture first.");
const browser = await chromium.launch({
  headless: true,
  ...(process.platform === "win32" ? { channel: "msedge" } : {}),
});
try {
  const context = await browser.newContext({ baseURL: fixture.origin });
  const login = await context.request.post("/api/backend/auth/login", {
    headers: { Origin: fixture.origin },
    data: { password: "mobile-fixture-password-123" },
  });
  expect(login.ok()).toBeTruthy();
  const { csrf } = await login.json();
  async function command(path, extra = {}) {
    const result = await context.request.post("/api/backend/calls" + path, {
      headers: { Origin: fixture.origin, "X-Yggdress-CSRF": csrf },
      data: { key: randomUUID(), device: "browser-fixture", ...extra },
    });
    expect(result.ok()).toBeTruthy();
    return result.json();
  }
  const first = await context.newPage();
  const second = await context.newPage();
  await Promise.all([first.goto("/today"), second.goto("/today")]);
  await Promise.all(
    [first, second].map((p) =>
      expect(
        p.getByRole("button", { name: "Call Yggdras", exact: true }),
      ).toBeVisible(),
    ),
  );
  const invitation = await command("/simulation");
  for (const page of [first, second])
    await expect(
      page.getByRole("heading", { name: "Yggdras is calling", exact: true }),
    ).toBeVisible();
  await first.getByRole("button", { name: "Answer", exact: true }).click();
  await expect(
    first.getByText("Simulation · no microphone or paid services", {
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    second.getByRole("heading", { name: "Yggdras is calling", exact: true }),
  ).not.toBeVisible();
  await first.screenshot({
    path: fileURLToPath(new URL("call-browser-simulation.png", cache)),
    fullPage: false,
  });
  await first.getByRole("button", { name: "End call", exact: true }).click();
  await expect(
    first.getByRole("button", { name: "End call", exact: true }),
  ).not.toBeVisible();
  const snapshot = await (
    await context.request.get("/api/backend/calls")
  ).json();
  expect(snapshot.calls.find((c) => c.id === invitation.id).state).toBe(
    "ended",
  );
  const next = await command("/simulation");
  await expect(
    second.getByRole("heading", { name: "Yggdras is calling", exact: true }),
  ).toBeVisible();
  await second.getByRole("button", { name: "Decline", exact: true }).click();
  for (const page of [first, second])
    await expect(
      page.getByRole("heading", { name: "Yggdras is calling", exact: true }),
    ).not.toBeVisible();
  const ended = await (await context.request.get("/api/backend/calls")).json();
  expect(ended.calls.find((c) => c.id === next.id).state).toBe("declined");
  const report = {
    two_clients: true,
    first_answer_wins: true,
    end_propagates: true,
    decline_propagates: true,
    microphone_requested: false,
    paid_calls: 0,
  };
  await writeFile(
    new URL("call-browser-verification.json", cache),
    JSON.stringify(report, null, 2),
  );
  console.log(JSON.stringify(report));
} finally {
  await browser.close();
}
