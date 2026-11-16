import { expect, test, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import { dateInZone } from "../src/lib/planning";

const seededEvents: { id: string; version: number }[] = [];
test.afterEach(async ({ page }) => {
  const { csrf } = await (
    await page.request.get("/api/backend/auth/session")
  ).json();
  for (const event of seededEvents.splice(0)) {
    const response = await page.request.post(
      "/api/backend/application/planning/commands",
      {
        headers: { Origin: "http://127.0.0.1:3100", "X-Yggdress-CSRF": csrf },
        data: {
          key: crypto.randomUUID(),
          op: "event.remove",
          data: {},
          ...event,
        },
      },
    );
    expect(response.ok()).toBe(true);
  }
});

async function openCalendar(page: Page) {
  await page.route("https://api.open-meteo.com/**", (route) => route.abort());
  await page.goto("/login");
  await page
    .getByLabel("Personal password")
    .fill(
      JSON.parse(readFileSync("../api/runtime/browser-session.json", "utf8"))
        .password,
    );
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).toHaveURL(/\/today$/);
  const dismiss = page.getByRole("button", {
    name: "Dismiss location suggestion",
  });
  if (await dismiss.isVisible()) await dismiss.click();
  const { csrf } = await (
    await page.request.get("/api/backend/auth/session")
  ).json();
  const day = dateInZone(new Date(), "Europe/Berlin");
  for (const [index, title] of [
    "Morning walk",
    "Design review",
    "Lunch with Alex",
    "Read and reflect",
  ].entries()) {
    const hour = String(9 + index * 2).padStart(2, "0");
    const result = await page.request.post(
      "/api/backend/application/planning/commands",
      {
        headers: { Origin: "http://127.0.0.1:3100", "X-Yggdress-CSRF": csrf },
        data: {
          key: crypto.randomUUID(),
          op: "event.create",
          data: {
            title,
            start: `${day}T${hour}:00`,
            end: `${day}T${hour}:45`,
          },
        },
      },
    );
    expect(result.ok()).toBe(true);
    seededEvents.push(await result.json());
  }
  await page.goto("/calendar");
  await expect(page.locator(".planning-time-scroll")).toBeVisible();
  return day;
}

test("calendar hierarchy, views, and date navigation remain usable at every width", async ({
  page,
}) => {
  const day = await openCalendar(page);
  for (const [name, width, height] of [
    ["desktop", 1344, 896],
    ["tablet", 820, 1180],
    ["phone", 390, 844],
    ["small-phone", 320, 740],
  ] as const) {
    await page.setViewportSize({ width, height });
    for (const view of ["Week", "Month", "Day", "Agenda"]) {
      await page.getByRole("tab", { name: view, exact: true }).click();
      await expect(page.locator(".calendar-surface")).toHaveAttribute(
        "data-view",
        view.toLowerCase(),
      );
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
      if (view === "Month" && width > 760) {
        await expect(
          page.getByRole("button", { name: "View all 4", exact: true }),
        ).toBeVisible();
      }
      if (view === "Month" && width <= 760) {
        await expect(page.locator(".calendar-day-count")).toHaveText("4 items");
        await page
          .getByRole("button", {
            name: `${day}, 4 scheduled items, 0 deadlines`,
            exact: true,
          })
          .click();
        await expect(page.locator(".calendar-surface")).toHaveAttribute(
          "data-view",
          "day",
        );
        await page.getByRole("tab", { name: "Month", exact: true }).click();
      }
      if (name !== "small-phone")
        await page.screenshot({
          path: `../api/runtime/calendar-refined-${view.toLowerCase()}-${name}.png`,
          fullPage: true,
        });
    }
  }
  await page.setViewportSize({ width: 1344, height: 896 });
  await page.getByRole("tab", { name: "Month", exact: true }).click();
  await expect(page.locator(".calendar-heading h2")).toContainText(
    day.slice(0, 4),
  );
  await page.getByRole("button", { name: "Next month", exact: true }).click();
  await expect(
    page.getByLabel("Calendar date", { exact: true }),
  ).not.toHaveValue(day);
  await page.locator(".calendar-today").click();
  await expect(page.getByLabel("Calendar date", { exact: true })).toHaveValue(
    day,
  );
  await page.getByRole("tab", { name: "Month", exact: true }).focus();
  await page.keyboard.press("ArrowRight");
  await expect(
    page.getByRole("tab", { name: "Agenda", exact: true }),
  ).toHaveAttribute("aria-selected", "true");
  await expect(page.locator(".planning-agenda")).toContainText("Morning walk");
  await page.getByRole("button", { name: /Morning walk/ }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toBeHidden();
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.evaluate(
    () => (document.documentElement.dataset.transparency = "reduced"),
  );
  await expect(page.locator(".calendar-surface")).toHaveCSS(
    "backdrop-filter",
    "none",
  );
});
