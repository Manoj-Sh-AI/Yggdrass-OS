import { expect, test } from "@playwright/test";
test.beforeEach(async ({ page }) => {
  await page.route("https://api.open-meteo.com/**", (route) =>
    route.fulfill({
      json: {
        timezone: "Europe/Berlin",
        current: { temperature_2m: 16, weather_code: 0, is_day: 1 },
        daily: {
          sunrise: [new Date().toISOString().slice(0, 10) + "T07:00"],
          sunset: [new Date().toISOString().slice(0, 10) + "T18:00"],
          daylight_duration: [39600],
        },
      },
    }),
  );
  await page.goto("/today");
  await expect(
    page.getByRole("heading", { name: "Alex", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Dismiss location suggestion" })
    .click();
});
test("capture, search, edit links, reload, and save a demo Lia response", async ({
  page,
}) => {
  await page.getByRole("button", { name: "Note", exact: true }).click();
  await page
    .getByLabel("Title", { exact: true })
    .fill("Garden of connected thoughts");
  await page
    .getByLabel("Details")
    .fill("A calm system for connecting useful ideas.");
  await page.getByLabel("Tags", { exact: true }).fill("clarity, reflection");
  await page.getByRole("button", { name: "Capture", exact: true }).click();
  await expect(page.getByRole("dialog")).toBeHidden();
  const search = page.getByRole("combobox", {
    name: "Search notes or ask Lia",
  });
  await search.fill("Garden");
  await page
    .getByRole("option")
    .filter({ hasText: "Garden of connected thoughts" })
    .click();
  await expect(page.getByRole("dialog")).toContainText("A calm system");
  await page.getByRole("button", { name: "Edit note" }).click();
  await page.getByLabel("Master’s Thesis", { exact: true }).check();
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(
    page.getByRole("dialog").getByRole("button", { name: /Master’s Thesis/ }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Close dialog" }).click();
  await page.reload();
  await search.fill("Garden");
  await page
    .getByRole("option")
    .filter({ hasText: "Garden of connected thoughts" })
    .click();
  await expect(page.getByRole("dialog")).toContainText("Master’s Thesis");
  await page.getByRole("button", { name: "Close dialog" }).click();
  await search.fill("German");
  await page.getByRole("option").filter({ hasText: "Ask Brain" }).click();
  await expect(page.getByRole("dialog")).toContainText("Demo response");
  await page.getByRole("button", { name: "Save to Notes" }).click();
  await expect(
    page.getByRole("button", { name: "Saved to Notes" }),
  ).toBeVisible();
});
test("graph, calendar, flashcards, and scene overrides", async ({ page }) => {
  await page.goto("/areas/german");
  await page.getByRole("tab", { name: "Graph", exact: true }).click();
  await expect(
    page.getByRole("group", { name: /Connected notes graph/ }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Zoom in" }).click();
  await page.getByRole("button", { name: "Open German A2.1" }).click();
  await expect(page.getByRole("dialog")).toContainText("German A2.1");
  await page.getByRole("button", { name: "Close dialog" }).click();
  await page.getByRole("button", { name: "Review", exact: true }).click();
  for (let i = 0; i < 3; i++) {
    await page.getByRole("button", { name: /Term:/ }).click();
    await page.getByRole("button", { name: "Got it" }).click();
  }
  await expect(page.getByRole("dialog")).toContainText("3 / 3");
  await page.getByRole("button", { name: "Finish session" }).click();
  await page.goto("/calendar");
  await page.getByRole("button", { name: "Next month" }).click();
  await page.getByRole("button", { name: "Today", exact: true }).click();
  await expect(
    page
      .getByRole("button", { name: /events, .*tasks/ })
      .filter({ has: page.locator(".day-number") })
      .first(),
  ).toBeVisible();
  await page.goto("/settings");
  await page.getByLabel("Season", { exact: true }).selectOption("summer");
  await page.getByLabel("Time of day").selectOption("night");
  await page.getByLabel("Weather", { exact: true }).selectOption("rainy");
  await expect(page.locator(".current-scene")).toContainText(
    "summer · night · rainy",
  );
  await page.reload();
  await expect(page.locator(".current-scene")).toContainText(
    "summer · night · rainy",
  );
});
test("keyboard dialog focus and mobile layout", async ({ page }) => {
  await page.getByRole("button", { name: "Note", exact: true }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByLabel("Title", { exact: true })).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(
    page.getByRole("button", { name: "Note", exact: true }),
  ).toBeFocused();
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(
    page.getByRole("button", { name: "Open navigation" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Open navigation" }).click();
  await page
    .getByRole("dialog")
    .getByRole("link", { name: "German", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "German", exact: true }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});
