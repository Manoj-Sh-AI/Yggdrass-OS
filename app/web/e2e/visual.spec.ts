import { expect, test } from "@playwright/test";
test("visual layouts across desktop, tablet and phone", async ({ page }) => {
  await page.route("https://api.open-meteo.com/**", (r) => r.abort());
  await page.goto("/today");
  await expect(
    page.getByRole("heading", { name: "Alex", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Dismiss location suggestion" })
    .click();
  await page.goto("/settings");
  await page.getByLabel("Season", { exact: true }).selectOption("autumn");
  await page.getByLabel("Time of day").selectOption("sunrise");
  await page.getByLabel("Weather", { exact: true }).selectOption("clear");
  await page.getByRole("switch", { name: "Quiet transitions" }).click();
  await page.goto("/today");
  await expect(page.locator(".greeting")).toBeVisible();
  await page.screenshot({
    path: "verification/today-desktop.png",
    fullPage: true,
  });
  for (const route of ["dashboard", "areas/projects", "calendar", "settings"]) {
    await page.goto(`/${route}`);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await page.screenshot({
      path: `verification/${route.replaceAll("/", "-")}-desktop.png`,
      fullPage: true,
    });
  }
  await page.setViewportSize({ width: 820, height: 1180 });
  await page.goto("/today");
  await expect(page.locator(".greeting")).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "verification/today-tablet.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/today");
  await expect(page.locator(".greeting")).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "verification/today-phone.png",
    fullPage: true,
  });
  await page.goto("/settings");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "verification/settings-phone.png",
    fullPage: true,
  });
});
