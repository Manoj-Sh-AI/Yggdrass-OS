import { expect, test } from "@playwright/test";
import { ROUTINE_STORAGE_KEY } from "../src/lib/routine-repository";
import { STORAGE_KEY } from "../src/lib/repository";
const goal = "Read one chapter and capture three takeaways.";
test.beforeEach(async ({ page }) => {
  await page.route("https://api.open-meteo.com/**", (r) => r.abort());
  await page.goto("/today");
  await expect(page.locator(".routine-card")).toBeVisible();
  const dismiss = page.getByRole("button", {
    name: "Dismiss location suggestion",
  });
  if (await dismiss.isVisible()) await dismiss.click();
});
test("start, progress and completion survive reload while the goal stays fixed", async ({
  page,
}) => {
  const card = page.locator(".routine-card");
  const legacy = await page.evaluate(
    (key) => localStorage.getItem(key),
    STORAGE_KEY,
  );
  await expect(card.locator(".routine-goal")).toHaveText(goal);
  await expect(card).toContainText("18:00");
  await expect(card).toContainText("18:30");
  await expect(card).toContainText("30 min");
  await card.getByRole("button", { name: "Start routine" }).click();
  await expect(card.locator(".routine-status")).toHaveText("In progress");
  const started = await page.evaluate(
    (key) => JSON.parse(localStorage.getItem(key)!),
    ROUTINE_STORAGE_KEY,
  );
  await page.reload();
  await expect(card.locator(".routine-status")).toHaveText("In progress");
  await card.getByLabel("Progress (%)").fill("40");
  await card.getByRole("button", { name: "Save progress" }).click();
  await expect(card.getByRole("progressbar")).toHaveAttribute(
    "aria-valuenow",
    "40",
  );
  await page.reload();
  await expect(card.getByLabel("Progress (%)")).toHaveValue("40");
  await expect(card.locator(".routine-goal")).toHaveText(goal);
  await card.getByLabel("Progress (%)").fill("100");
  await card.getByRole("button", { name: "Save progress" }).click();
  await expect(card.getByRole("progressbar")).toHaveAttribute(
    "aria-valuenow",
    "100",
  );
  await expect(card.locator(".routine-status")).toHaveText("In progress");
  await card.getByRole("button", { name: "Complete routine" }).click();
  await expect(card.locator(".routine-status")).toHaveText("Completed");
  await expect(
    card.getByRole("button", { name: "Complete routine" }),
  ).toHaveCount(0);
  await page.reload();
  await expect(card.locator(".routine-status")).toHaveText("Completed");
  await expect(card.locator(".routine-goal")).toHaveText(goal);
  const completed = await page.evaluate(
    (key) => JSON.parse(localStorage.getItem(key)!),
    ROUTINE_STORAGE_KEY,
  );
  expect(completed.definition).toEqual(started.definition);
  expect(completed.execution.startedAt).toBe(started.execution.startedAt);
  expect(completed.execution.completedAt).toBeTruthy();
  expect(
    await page.evaluate((key) => localStorage.getItem(key), STORAGE_KEY),
  ).toBe(legacy);
});
test("invalid progress and a failed save retain the draft and saved execution", async ({
  page,
}) => {
  const card = page.locator(".routine-card");
  await card.getByRole("button", { name: "Start routine" }).click();
  const input = card.getByLabel("Progress (%)");
  await input.fill("101");
  await card.getByRole("button", { name: "Save progress" }).click();
  await expect(card.getByRole("alert")).toContainText("whole-number");
  await expect(card.getByRole("progressbar")).toHaveAttribute(
    "aria-valuenow",
    "0",
  );
  await input.fill("45");
  await page.evaluate((key) => {
    const original = Storage.prototype.setItem;
    Storage.prototype.setItem = function (k, v) {
      if (k === key)
        throw new DOMException("Routine quota exceeded", "QuotaExceededError");
      return original.call(this, k, v);
    };
  }, ROUTINE_STORAGE_KEY);
  await card.getByRole("button", { name: "Save progress" }).click();
  await expect(card.getByRole("alert")).toContainText("Could not save");
  await expect(input).toHaveValue("45");
  await expect(card.getByRole("progressbar")).toHaveAttribute(
    "aria-valuenow",
    "0",
  );
  await page.reload();
  await expect(input).toHaveValue("0");
  await input.fill("45");
  await card.getByRole("button", { name: "Save progress" }).click();
  await expect(card.getByRole("progressbar")).toHaveAttribute(
    "aria-valuenow",
    "45",
  );
  await expect(card.locator(".routine-goal")).toHaveText(goal);
});
test("narrow layout, keyboard controls and explicit demo reset", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const card = page.locator(".routine-card");
  const start = card.getByRole("button", { name: "Start routine" });
  await start.focus();
  await start.press("Enter");
  await expect(card.locator(".routine-status")).toHaveText("In progress");
  await card.getByLabel("Progress (%)").fill("25");
  await card.getByLabel("Progress (%)").press("Enter");
  await expect(card.getByRole("progressbar")).toHaveAttribute(
    "aria-valuenow",
    "25",
  );
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "verification/routine-phone.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 1344, height: 896 });
  await card.screenshot({ path: "verification/routine-card-desktop.png" });
  await page.screenshot({
    path: "verification/routine-today-desktop.png",
    fullPage: true,
  });
  await page.goto("/settings");
  await page.getByRole("button", { name: "Reset demo", exact: true }).click();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Reset demo", exact: true })
    .click();
  await page.goto("/today");
  await expect(card.locator(".routine-status")).toHaveText("Ready to begin");
  await expect(card.locator(".routine-goal")).toHaveText(goal);
});
test("unreadable routine data is preserved and never silently overwritten", async ({
  page,
}) => {
  const raw = '{"version":999,"privateDraft":"keep"}';
  await page.evaluate(({ key, raw }) => localStorage.setItem(key, raw), {
    key: ROUTINE_STORAGE_KEY,
    raw,
  });
  await page.reload();
  await expect(page.locator(".routine-loading")).toContainText(
    "could not be loaded",
  );
  await page.getByRole("button", { name: "Retry loading routine" }).click();
  await expect(page.locator(".routine-loading")).toContainText(
    "could not be loaded",
  );
  expect(
    await page.evaluate(
      (key) => localStorage.getItem(key),
      ROUTINE_STORAGE_KEY,
    ),
  ).toBe(raw);
});
