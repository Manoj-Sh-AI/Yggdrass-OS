import { expect, test, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";

async function auth(page: Page) {
  await page.route("https://api.open-meteo.com/**", (r) => r.abort());
  await page.goto("/today");
  await page
    .getByLabel("Personal password")
    .fill(
      JSON.parse(readFileSync("../api/runtime/browser-session.json", "utf8"))
        .password,
    );
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).toHaveURL(/\/today$/);
}

test("reduced transparency persists and reaches the embedded graph", async ({
  page,
}) => {
  await auth(page);
  await page.goto("/settings");
  const toggle = page.getByRole("switch", {
    name: "Reduce transparency",
    exact: true,
  });
  await expect(toggle).toHaveAttribute("aria-checked", "false");
  await toggle.focus();
  await expect(toggle).toBeFocused();
  await page.keyboard.press("Space");
  await expect(page.locator("html")).toHaveAttribute(
    "data-transparency",
    "reduced",
  );
  await page.reload();
  await expect(toggle).toHaveAttribute("aria-checked", "true");
  const material = await page
    .locator(".panel")
    .first()
    .evaluate((el) => ({
      blur: getComputedStyle(el).backdropFilter,
      fill: getComputedStyle(el).backgroundColor,
    }));
  expect(material.blur).toMatch(/none|blur\(0px\)/);
  expect(material.fill).toMatch(/^rgb\(/);
  await page.route("**/api/backend/graph/status", (r) =>
    r.fulfill({ json: { nodes: 1, links: 0, source: "brain-viewer" } }),
  );
  await page.route("**/api/graph-viewer/graph.html", (r) =>
    r.fulfill({
      contentType: "text/html",
      body: `<html><body><script>addEventListener('message',e=>{if(e.data.type==='yggdras:graph-appearance')document.documentElement.dataset.transparency=e.data.reducedTransparency?'reduced':'glass'});parent.postMessage({type:'yggdras:graph',event:'ready'},location.origin)</script></body></html>`,
    }),
  );
  await page.goto("/graph");
  await expect(page.frameLocator("iframe").locator("html")).toHaveAttribute(
    "data-transparency",
    "reduced",
  );
});

test("system reduction, forced colours and keyboard focus remain clear", async ({
  page,
}) => {
  await auth(page);
  const cdp = await page.context().newCDPSession(page);
  await cdp.send("Emulation.setEmulatedMedia", {
    features: [{ name: "prefers-reduced-transparency", value: "reduce" }],
  });
  expect(
    await page.evaluate(
      () => matchMedia("(prefers-reduced-transparency: reduce)").matches,
    ),
  ).toBe(true);
  const panel = page.locator(".today-schedule").first();
  expect(
    await panel.evaluate((el) => getComputedStyle(el).backdropFilter),
  ).toMatch(/none|blur\(0px\)/);
  await page.emulateMedia({ forcedColors: "active", reducedMotion: "reduce" });
  expect(await panel.evaluate((el) => getComputedStyle(el).boxShadow)).toBe(
    "none",
  );
  expect(
    await page
      .locator(".scene-image")
      .last()
      .evaluate((el) => getComputedStyle(el).transitionDuration),
  ).toBe("0s");
  const nav = page.getByRole("link", { name: "Notes", exact: true });
  await page.keyboard.press("Tab");
  await nav.focus();
  expect(
    await nav.evaluate((el) => parseFloat(getComputedStyle(el).outlineWidth)),
  ).toBeGreaterThanOrEqual(2);
});

test("glass pages remain readable and fit narrow screens", async ({ page }) => {
  test.setTimeout(240000);
  await auth(page);
  for (const width of [1344, 390]) {
    await page.setViewportSize({ width, height: 896 });
    for (const route of [
      "/today",
      "/dashboard",
      "/calendar",
      "/tasks",
      "/notes",
      "/settings",
      "/graph",
    ]) {
      await page.goto(route);
      await expect(page.locator("#main")).toBeVisible();
      await expect(page.locator("#main h1").first()).toBeVisible({
        timeout: 30000,
      });
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
        `${route} at ${width}`,
      ).toBe(true);
    }
  }
});
