import { expect, test, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";

async function auth(page: Page) {
  await page.route("https://api.open-meteo.com/**", (route) => route.abort());
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
const viewer = `<!doctype html><html><body style="background:#0b1728;color:white"><h1>Invented viewer fixture</h1><button id="open">Open sample</button><script>
parent.postMessage({type:'yggdras:graph',event:'ready'},location.origin);
document.getElementById('open').onclick=()=>parent.postMessage({type:'yggdras:graph',event:'open-note',slug:'sample'},location.origin);
addEventListener('message',e=>{if(e.data.type==='yggdras:graph-control')document.body.dataset.paused=String(e.data.paused)});
</script></body></html>`;

test("graph follows Notes, loads privately, supports rotation control and opens real Notes", async ({
  page,
}) => {
  await auth(page);
  await page.route("**/api/backend/graph/status", (route) =>
    route.fulfill({ json: { nodes: 12, links: 6, source: "brain-viewer" } }),
  );
  await page.route("**/api/graph-viewer/graph.html", (route) =>
    route.fulfill({ contentType: "text/html", body: viewer }),
  );
  const links = page
    .getByRole("navigation", { name: "Main navigation" })
    .getByRole("link");
  const labels = await links.allTextContents();
  expect(labels.indexOf("Graph")).toBe(labels.indexOf("Notes") + 1);
  await page.getByRole("link", { name: "Graph", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Graph" })).toBeVisible();
  await expect(page.getByText("12 notes", { exact: true })).toBeVisible();
  const embedded = page.frameLocator(
    'iframe[title="Interactive Brain graph and note details"]',
  );
  await expect(
    page.getByRole("button", { name: "Resume rotation" }),
  ).toBeEnabled();
  await page.getByRole("button", { name: "Resume rotation" }).click();
  await expect(embedded.locator("body")).toHaveAttribute(
    "data-paused",
    "false",
  );
  await page.getByRole("button", { name: "Pause rotation" }).click();
  await expect(embedded.locator("body")).toHaveAttribute("data-paused", "true");
  let releaseCatalogue!: () => void;
  const catalogue = new Promise<void>((resolve) => {
    releaseCatalogue = resolve;
  });
  await page.route("**/api/backend/notes/search**", async (route) => {
    await catalogue;
    await route.continue();
  });
  try {
    await embedded.getByRole("button", { name: "Open sample" }).click();
    await expect(page).toHaveURL(/\/notes\?note=sample$/);
    // The requested editor opens even while the catalogue is still loading.
    await expect(page.getByLabel("Title", { exact: true })).toHaveValue(
      "Sample",
    );
  } finally {
    releaseCatalogue();
  }
});

test("unavailable graph shows retry and recovers without demo fallback", async ({
  page,
}) => {
  await auth(page);
  let failed = true;
  await page.route("**/api/backend/graph/status", (route) =>
    failed
      ? route.fulfill({ status: 503, json: { detail: "Brain viewer offline" } })
      : route.fulfill({
          json: { nodes: 12, links: 6, source: "brain-viewer" },
        }),
  );
  await page.route("**/api/graph-viewer/graph.html", (route) =>
    route.fulfill({ contentType: "text/html", body: viewer }),
  );
  await page.goto("/graph");
  await expect(page.locator(".brain-graph-error")).toContainText(
    "Brain viewer offline",
  );
  await expect(page.locator("iframe")).toHaveCount(0);
  failed = false;
  await page.getByRole("button", { name: "Reload graph", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Resume rotation" }),
  ).toBeEnabled();
  await expect(page.locator(".brain-graph-error")).toHaveCount(0);
});

test("phone graph page has no horizontal overflow and remains navigable", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await auth(page);
  await page.route("**/api/backend/graph/status", (route) =>
    route.fulfill({ json: { nodes: 12, links: 6, source: "brain-viewer" } }),
  );
  await page.route("**/api/graph-viewer/graph.html", (route) =>
    route.fulfill({ contentType: "text/html", body: viewer }),
  );
  await page.goto("/graph");
  await expect(page.getByRole("heading", { name: "Graph" })).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.getByRole("button", { name: "Open navigation" }).click();
  await expect(
    page.getByRole("link", { name: "Graph", exact: true }),
  ).toHaveAttribute("aria-current", "page");
});
