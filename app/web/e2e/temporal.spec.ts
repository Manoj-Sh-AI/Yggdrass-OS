import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";

test("calendar keeps inclusive all-day ranges separate from availability and persists them", async ({
  page,
}) => {
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
  await page.goto("/calendar");
  await page.getByRole("button", { name: "New event", exact: true }).click();
  await page.getByLabel("Calendar item type").selectOption("date_item");
  await page.getByLabel("Calendar item title").fill("Synthetic all-day range");
  await page.getByLabel("Start date", { exact: true }).fill("2026-11-15");
  await page.getByLabel("End date", { exact: true }).fill("2026-11-17");
  await page
    .getByRole("button", { name: "Create date item", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page.getByLabel("Calendar date", { exact: true }).fill("2026-11-16");
  await expect(
    page.getByRole("button", { name: /Synthetic all-day range/ }).first(),
  ).toBeVisible();
  await page.reload();
  await page.getByLabel("Calendar date", { exact: true }).fill("2026-11-16");
  await page
    .getByRole("button", { name: /Synthetic all-day range/ })
    .first()
    .click();
  await expect(page.getByLabel("End date", { exact: true })).toHaveValue(
    "2026-11-17",
  );
  await page
    .getByRole("button", { name: "Remove this calendar item", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: /Synthetic all-day range/ }),
  ).toHaveCount(0);
});
