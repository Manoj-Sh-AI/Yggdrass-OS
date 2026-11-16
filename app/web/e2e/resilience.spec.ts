import { expect, test } from "@playwright/test";
import { seed } from "../src/lib/data";
import { STORAGE_KEY } from "../src/lib/repository";
test("10,000 notes stay bounded in the rendered list and graph", async ({
  page,
}) => {
  const state = seed();
  state.preferences.locationPrompted = true;
  const original = state.notes[0];
  state.notes = Array.from({ length: 10000 }, (_, i) => ({
    ...original,
    id: `stress-${i}`,
    slug: `stress-${i}`,
    title: `Research thought ${i}`,
    links: i ? [`stress-${i - 1}`] : [],
  }));
  await page.addInitScript(
    ({ key, value }) => localStorage.setItem(key, value),
    { key: STORAGE_KEY, value: JSON.stringify(state) },
  );
  await page.route("https://api.open-meteo.com/**", (r) => r.abort());
  await page.goto("/areas/work");
  await expect(page.getByText("10000 thoughts", { exact: true })).toBeVisible();
  expect(await page.locator(".note-row").count()).toBeLessThan(30);
  await page.getByLabel("Search area notes").fill("Research thought 9999");
  await expect(page.locator(".note-row")).toHaveCount(1);
  await expect(page.locator(".note-row")).toContainText(
    "Research thought 9999",
  );
  await page.getByLabel("Search area notes").fill("");
  await expect(page.getByText("10000 thoughts", { exact: true })).toBeVisible();
  await page.getByRole("tab", { name: "Graph", exact: true }).click();
  await expect(page.locator(".graph-node")).toHaveCount(80);
});
test("denied location offers a manual city and failed captures retain content", async ({
  page,
}) => {
  await page.addInitScript(() => {
    Object.defineProperty(navigator, "geolocation", {
      value: {
        getCurrentPosition: (
          _success: unknown,
          error: (e: { code: number }) => void,
        ) => error({ code: 1 }),
      },
    });
  });
  await page.route("https://api.open-meteo.com/**", (r) => r.abort());
  await page.route("https://geocoding-api.open-meteo.com/**", (r) =>
    r.fulfill({
      json: {
        results: [
          {
            id: 1,
            name: "Vienna",
            country: "Austria",
            latitude: 48.2,
            longitude: 16.37,
            timezone: "Europe/Vienna",
          },
        ],
      },
    }),
  );
  await page.goto("/today");
  await page
    .getByRole("button", { name: "Use my location", exact: true })
    .click();
  await expect(page.locator(".toast")).toContainText("Using Hamburg");
  await page.goto("/settings");
  await page.getByLabel("Search cities").fill("Vienna");
  await page.getByRole("button", { name: "Vienna Austria" }).click();
  await expect(page.locator(".location-card h3")).toHaveText("Vienna");
  await page.addInitScript(() => {
    Storage.prototype.setItem = () => {
      throw new DOMException(
        "Demo storage quota exceeded",
        "QuotaExceededError",
      );
    };
  });
  await page.goto("/today");
  await page.getByRole("button", { name: "Note", exact: true }).click();
  await page.getByLabel("Title", { exact: true }).fill("Keep this thought");
  await page
    .getByLabel("Details")
    .fill("My words should remain here after a failed save.");
  await page.getByRole("button", { name: "Capture", exact: true }).click();
  await expect(page.getByRole("dialog")).toContainText("Could not save");
  await expect(page.getByLabel("Title", { exact: true })).toHaveValue(
    "Keep this thought",
  );
  await expect(page.getByLabel("Details")).toHaveValue(
    "My words should remain here after a failed save.",
  );
});
test("missing scenery assets keep a safe visible background", async ({
  page,
}) => {
  const state = seed();
  state.preferences = {
    ...state.preferences,
    locationPrompted: true,
    season: "winter",
    phase: "night",
    sky: "rainy",
  };
  await page.addInitScript(
    ({ key, value }) => localStorage.setItem(key, value),
    { key: STORAGE_KEY, value: JSON.stringify(state) },
  );
  await page.route("https://api.open-meteo.com/**", (r) => r.abort());
  let missingRequests = 0;
  await page.route("**/scenes/winter-night-rainy-*.webp", (r) => {
    missingRequests++;
    return r.abort();
  });
  await page.goto("/today");
  await expect(page.locator(".greeting")).toBeVisible();
  await expect(page.locator(".scene-fallback")).toBeVisible();
  await expect.poll(() => missingRequests).toBeGreaterThan(0);
  // An already loaded automatic scene may beat hydration of the saved override.
  // The contract is to retain the last good scene, not a particular poster.
  const currentScene = page.locator(".scene-image.current");
  await expect(currentScene).toHaveCSS("opacity", "1");
  await expect(currentScene).toHaveCSS(
    "background-image",
    /\/scenes\/[a-z]+-[a-z]+-[a-z]+-1920\.webp/,
  );
  await expect(currentScene).not.toHaveCSS(
    "background-image",
    /winter-night-rainy/,
  );
});
