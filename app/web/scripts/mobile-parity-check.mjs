// Explicit invented-data fixture only; never reads or edits the owner's notes.
import { chromium, expect } from "@playwright/test";
import { readFile, writeFile } from "node:fs/promises";
const cache = new URL("../../mobile/.cache/", import.meta.url);
const fixture = JSON.parse(
  await readFile(new URL("device-fixture-state.json", cache), "utf8"),
);
if (
  !fixture.ready ||
  fixture.origin !== "http://127.0.0.1:3300" ||
  fixture.data !== "invented only"
)
  throw new Error("Start the isolated owner-notes fixture first.");
const browser = await chromium.launch({
  headless: true,
  ...(process.platform === "win32" ? { channel: "msedge" } : {}),
});
try {
  const desktop = await browser.newContext({ baseURL: fixture.origin });
  const phone = await browser.newContext({
    baseURL: fixture.origin,
    viewport: { width: 412, height: 915 },
    reducedMotion: "reduce",
  });
  const headers = { Origin: fixture.origin };
  const login = await desktop.request.post("/api/backend/auth/login", {
    headers,
    data: { password: "mobile-fixture-password-123" },
  });
  expect(login.ok()).toBeTruthy();
  const { csrf } = await login.json();
  const native = await phone.request.post("/api/backend/mobile/auth/login", {
    headers,
    data: { password: "mobile-fixture-password-123" },
  });
  expect(native.ok()).toBeTruthy();
  const bridge = await phone.request.post("/api/mobile-session?view=notes", {
    headers,
    form: { token: (await native.json()).token },
  });
  expect(bridge.ok()).toBeTruthy();
  const read = async (context, path) => {
    const response = await context.request.get("/api/backend/" + path);
    expect(response.ok()).toBeTruthy();
    return response.json();
  };
  expect(await read(phone, "notes/search?q=")).toEqual(
    await read(desktop, "notes/search?q="),
  );
  const initial = (await read(phone, "notes/search?q=")).notes.length;
  const page = await phone.newPage();
  await page.route("https://api.open-meteo.com/**", (route) => route.abort());
  await page.goto("/notes?note=fixture-private");
  await expect(page.locator(".notes-page-heading h1")).toContainText(
    String(initial),
  );
  const show = page
    .locator(".notes-writing-panel")
    .getByRole("button", { name: "Show", exact: true });
  await expect(show).toBeVisible();
  await expect(page.locator(".bn-editor")).toHaveCount(0);
  const navigation = page.getByRole("button", {
    name: "Toggle notes navigation",
  });
  if ((await navigation.getAttribute("aria-expanded")) === "false")
    await navigation.click();
  await page
    .getByLabel("Search Brain notes")
    .fill("Private invented fixture text");
  await expect(page.locator(".note-search-results")).toContainText(
    "Private invented fixture",
  );
  await expect(page.locator(".note-search-results")).not.toContainText(
    "Private invented fixture text",
  );
  await expect(page.locator(".notes-page-heading h1")).toContainText(
    String(initial),
  );
  await navigation.click();
  await page.getByRole("button", { name: "Toggle note context" }).click();
  await expect(
    page.getByRole("complementary", { name: "Note context" }),
  ).toHaveCount(0);
  await show.click();
  await page.getByRole("button", { name: "Toggle note context" }).click();
  await expect(page.locator(".bn-editor")).toContainText(
    "Private invented fixture text",
  );
  const content = page.getByLabel("Content", { exact: true });
  await content
    .locator('[data-content-type="bulletListItem"] .bn-inline-content')
    .first()
    .fill("Unsaved invented draft");
  const refreshSlug = "refresh-fixture-" + Date.now();
  const created = await desktop.request.post("/api/backend/notes/create", {
    headers: { ...headers, "X-Yggdress-CSRF": csrf },
    data: {
      slug: refreshSlug,
      text: `---\nslug: ${refreshSlug}\nname: Refresh fixture\n---\n## Facts\n- Invented refresh check\n`,
    },
  });
  expect(created.ok()).toBeTruthy();
  await navigation.click();
  await page.getByLabel("Search Brain notes").fill("");
  await page.evaluate(() =>
    window.dispatchEvent(new Event("yggdras:foreground")),
  );
  await expect(page.locator(".notes-page-heading h1")).toContainText(
    String(initial + 1),
  );
  await navigation.click();
  await expect(content).toContainText("Unsaved invented draft");
  // Reload restores the local draft but never skips the explicit sensitive Show gate.
  page.once("dialog", (dialog) => dialog.accept());
  await page.reload();
  await expect(
    page
      .locator(".notes-writing-panel")
      .getByRole("button", { name: "Show", exact: true }),
  ).toBeVisible();
  await expect(page.locator(".bn-editor")).toHaveCount(0);
  expect(await read(phone, "graph/status")).toEqual(
    await read(desktop, "graph/status"),
  );
  const graph = await phone.request.get("/api/graph-viewer/graph.html");
  expect(graph.ok()).toBeTruthy();
  expect(await graph.text()).toContain("fixture-private");
  const report = {
    same_catalogue: true,
    same_graph: true,
    sensitive_preview_hidden: true,
    explicit_show: true,
    concealed_again_after_reload: true,
    stable_search_total: true,
    refresh_preserves_draft: true,
    paid_calls: 0,
    real_brain_writes: 0,
  };
  await writeFile(
    new URL("mobile-parity-browser-verification.json", cache),
    JSON.stringify(report, null, 2),
  );
  console.log(JSON.stringify(report));
} finally {
  await browser.close();
}
