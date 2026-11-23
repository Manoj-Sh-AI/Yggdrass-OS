import { expect, test, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
const password = () =>
  JSON.parse(readFileSync("../api/runtime/browser-session.json", "utf8"))
    .password as string;
const goal = "Read one chapter and capture three takeaways.";
async function signIn(page: Page) {
  await page.goto("/today");
  await page.getByLabel("Personal password").fill(password());
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).toHaveURL(/\/today$/);
  await expect(
    page.getByRole("heading", { name: "Today", exact: true }),
  ).toBeVisible();
  const dismiss = page.getByRole("button", {
    name: "Dismiss location suggestion",
  });
  if (await dismiss.isVisible()) await dismiss.click();
}
async function headers(page: Page) {
  const session = await page.request.get("/api/backend/auth/session");
  return {
    Origin: "http://127.0.0.1:3100",
    "X-Yggdress-CSRF": (await session.json()).csrf,
  };
}
test.beforeEach(async ({ page }) => {
  await page.route("https://api.open-meteo.com/**", (route) => route.abort());
});
test("private pages and APIs reject anonymous access; login and logout protect the workspace", async ({
  page,
}) => {
  for (const path of [
    "/today",
    "/notes",
    "/dashboard",
    "/calendar",
    "/settings",
    "/areas/work",
  ]) {
    await page.goto(path);
    await expect(page).toHaveURL(/\/login$/);
    await expect(page.locator(".app-shell")).toHaveCount(0);
  }
  expect((await page.request.get("/api/backend/brain/notes")).status()).toBe(
    401,
  );
  expect(
    (await page.request.get("/api/backend/application/tasks")).status(),
  ).toBe(401);
  await page.screenshot({ path: "verification/phase1-login.png" });
  await page.getByLabel("Personal password").fill(password() + "wrong");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.locator('.login-panel [role="alert"]')).toContainText(
    "Incorrect password",
  );
  await signIn(page);
  await expect(page.locator(".integration-banner")).toHaveCount(0);
  expect(
    (
      await page.request.post("/api/backend/application/routine/actions", {
        data: { type: "start" },
        headers: { Origin: "https://other.example" },
      })
    ).status(),
  ).toBe(403);
  expect(
    (
      await page.request.post("/api/backend/application/routine/actions", {
        data: { type: "start" },
        headers: { Origin: "http://127.0.0.1:3100" },
      })
    ).status(),
  ).toBe(403);
  await page.getByRole("button", { name: "Open account menu" }).click();
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await expect(page).toHaveURL(/\/login$/);
  expect(
    (await page.request.get("/api/backend/application/routine")).status(),
  ).toBe(401);
});

// Retired mock drawers/AI-answer tests are replaced by the connected Notes suite.
// The reusable routine component retains its component/state tests; its historical
// application endpoint remains verified here without putting a sample on Today.
test("existing routine execution remains persisted independently of Today presentation", async ({
  page,
}) => {
  await signIn(page);
  const initial = await (
    await page.request.get("/api/backend/application/routine")
  ).json();
  const post = async (data: object) =>
    page.request.post("/api/backend/application/routine/actions", {
      data,
      headers: await headers(page),
    });
  expect((await post({ type: "start" })).ok()).toBe(true);
  expect((await post({ type: "progress", percent: 101 })).status()).toBe(422);
  expect((await post({ type: "progress", percent: 45 })).ok()).toBe(true);
  await page.reload();
  const saved = await (
    await page.request.get("/api/backend/application/routine")
  ).json();
  expect(saved.definition).toEqual(initial.definition);
  expect(saved.execution.progress).toBe(45);
  expect((await post({ type: "complete" })).ok()).toBe(true);
  expect(
    (await (await page.request.get("/api/backend/application/routine")).json())
      .execution.status,
  ).toBe("completed");
  await expect(page.locator(".routine-card")).toHaveCount(0);
});

