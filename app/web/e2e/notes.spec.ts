import { expect, test, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";

async function auth(page: Page) {
  await page.route("https://api.open-meteo.com/**", (r) => r.abort());
  await page.goto("/login");
  await page
    .getByLabel("Personal password")
    .fill(
      JSON.parse(readFileSync("../api/runtime/browser-session.json", "utf8"))
        .password,
    );
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).toHaveURL(/\/today$/);
  await page.goto("/notes");
  await expect(page.locator(".bn-editor")).toBeVisible({ timeout: 60000 });
  await page
    .locator(".note-tree-item")
    .filter({ hasText: /^Sample/ })
    .first()
    .click();
  await expect(page.getByLabel("Title", { exact: true })).toHaveValue("Sample");
}
async function newDraft(page: Page, title: string) {
  await page.getByRole("button", { name: "New note", exact: true }).click();
  await expect(page.getByLabel("Title", { exact: true })).toHaveValue("");
  await save(page);
  await expect(
    page.getByRole("alert").filter({ hasText: "A note needs a title" }).first(),
  ).toBeVisible();
  await page.getByLabel("Title", { exact: true }).fill(title);
}
async function save(page: Page) {
  await page.getByRole("button", { name: "Save now", exact: true }).click();
}

test("Notes opens while an unrelated application task request is still pending", async ({
  page,
}) => {
  await auth(page);
  let release!: () => void;
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  let requested = false;
  await page.route("**/api/backend/application/tasks", async (route) => {
    requested = true;
    await gate;
    await route.continue();
  });
  try {
    await page.goto("/notes");
    await expect.poll(() => requested).toBe(true);
    await expect(page.locator(".bn-editor")).toBeVisible({ timeout: 60000 });
    await expect(page.getByLabel("Title", { exact: true })).toHaveValue(
      "Sample",
    );
    await expect(page.locator(".loading-workspace")).toHaveCount(0);
  } finally {
    release();
  }
});

test("capture responds to press, restores focus, and honours reduced motion", async ({
  page,
}) => {
  await auth(page);
  await page.goto("/today");
  const capture = page.getByRole("button", { name: "New task", exact: true });
  await expect(capture).toBeEnabled();
  await capture.hover();
  await page.mouse.down();
  await expect
    .poll(() => capture.evaluate((element) => getComputedStyle(element).scale))
    .toBe("0.98");
  await page.mouse.up();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(capture).toBeFocused();
  await page.emulateMedia({ reducedMotion: "reduce" });
  await capture.click();
  await expect(page.getByRole("dialog")).toBeVisible();
  expect(
    await page
      .getByRole("dialog")
      .evaluate((element) => getComputedStyle(element).animationName),
  ).toBe("none");
  await page.keyboard.press("Escape");
  await expect(capture).toBeFocused();
});

test("a delayed note-open response cannot replace a newer blank draft", async ({
  page,
}) => {
  await auth(page);
  let release!: () => void;
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  let requested = false;
  await page.route("**/api/backend/notes/items/sample", async (route) => {
    requested = true;
    await gate;
    await route.continue();
  });
  await page
    .locator(".note-tree-item")
    .filter({ hasText: /^Sample/ })
    .first()
    .click();
  await expect.poll(() => requested).toBe(true);
  await page.getByRole("button", { name: "New note", exact: true }).click();
  await expect(page.getByLabel("Title", { exact: true })).toHaveValue("");
  const response = page.waitForResponse((r) =>
    r.url().endsWith("/notes/items/sample"),
  );
  release();
  await response;
  await expect(page.getByLabel("Title", { exact: true })).toHaveValue("");
});

test("authenticated list, blank editor, explicit create, found links, search and reload", async ({
  page,
}) => {
  await auth(page);
  await expect(page.locator(".notes-navigation")).toContainText(
    "First (src: self",
  );
  await expect(page.locator(".notes-navigation")).toContainText("04-learning");
  let creations = 0;
  page.on("request", (request) => {
    if (request.url().endsWith("/notes/create")) creations++;
  });
  await newDraft(page, "Invented notebook");
  const content = page.getByLabel("Content", { exact: true });
  await page
    .getByLabel("Summary", { exact: true })
    .fill("An invented thought.");
  await content.getByRole("heading", { name: "Facts", exact: true }).click();
  await content
    .getByRole("heading", { name: "Facts", exact: true })
    .evaluate((element) => {
      const range = document.createRange();
      range.selectNodeContents(element);
      range.collapse(false);
      const selection = window.getSelection();
      selection?.removeAllRanges();
      selection?.addRange(range);
    });
  await page.keyboard.press("Enter");
  await page.keyboard.type(
    "- An invented fact [[linked]] (src: self, 2030-01-01)",
  );
  await expect(content).toContainText("An invented fact");
  await expect(
    content.getByRole("heading", { name: "Facts", exact: true }),
  ).toBeVisible();
  await page.waitForTimeout(1100);
  expect(creations).toBe(0);
  await save(page);
  await expect(page.locator(".save-state")).toHaveAttribute(
    "data-save-state",
    "saved",
  );
  await expect(
    page.getByRole("status").filter({ hasText: "Found links:" }),
  ).toBeVisible();
  expect(creations).toBe(1);
  await page.reload();
  await expect(page.getByLabel("Title", { exact: true })).toHaveValue(
    "Invented notebook",
  );
  await expect(page.getByLabel("Content", { exact: true })).toContainText(
    "An invented fact",
  );
  await page.getByLabel("Search Brain notes").fill("invented fact");
  await expect(page.locator(".note-search-results")).toContainText(
    "An invented fact",
  );
  await page.screenshot({
    path: "verification/notes-brain-desktop.png",
    fullPage: true,
  });
});

test("fact edit reviews one combined preview, Cancel preserves draft, Confirm refreshes, Undo reloads", async ({
  page,
}) => {
  await auth(page);
  const content = page.getByLabel("Content", { exact: true });
  const first = content
    .locator('[data-content-type="bulletListItem"] .bn-inline-content')
    .first();
  await first.fill("Changed first (src: self, 2030-01-01)");
  await save(page);
  let modal = page.getByRole("dialog", { name: "Review note changes" });
  await expect(modal).toContainText("First (src: self");
  await expect(modal).toContainText("Changed first");
  await modal.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(content).toContainText("Changed first");
  await expect(page.locator(".save-state")).toHaveAttribute(
    "data-save-state",
    "failed",
  );
  await save(page);
  await modal
    .getByRole("button", { name: "Confirm changes", exact: true })
    .click();
  await expect(page.locator(".save-state")).toHaveAttribute(
    "data-save-state",
    "saved",
  );
  await expect(content).toContainText("Changed first");
  await page
    .getByRole("button", { name: "Undo last saved change", exact: true })
    .first()
    .click();
  await expect(content).not.toContainText("Changed first");
  await expect(
    page.getByRole("button", { name: "Undo last saved change" }).first(),
  ).toBeDisabled();
});

test("Markdown write refusal is visible and preserves the full new-note draft", async ({
  page,
}) => {
  await auth(page);
  await newDraft(page, "Keep my draft");
  await page
    .getByLabel("Content", { exact: true })
    .fill("Keep this entered sentence.");
  await page.route("**/api/backend/notes/create", (route) =>
    route.fulfill({
      status: 409,
      contentType: "application/json",
      body: JSON.stringify({
        detail: "Writes are not live yet — the brain is still on markdown.",
        code: "brain_markdown",
      }),
    }),
  );
  await save(page);
  await expect(
    page
      .getByRole("alert")
      .filter({ hasText: "Writes are not live yet" })
      .first(),
  ).toBeVisible();
  await expect(page.getByLabel("Title", { exact: true })).toHaveValue(
    "Keep my draft",
  );
  await expect(page.getByLabel("Content", { exact: true })).toContainText(
    "Keep this entered sentence.",
  );
  await expect(page.locator(".save-state")).toHaveAttribute(
    "data-save-state",
    "failed",
  );
  await page.reload();
  await expect(page.getByLabel("Title", { exact: true })).toHaveValue(
    "Keep my draft",
  );
  await expect(page.getByLabel("Content", { exact: true })).toContainText(
    "Keep this entered sentence.",
  );
});

test("stale confirmation stops, preserves edited content, and offers explicit refresh", async ({
  page,
}) => {
  await auth(page);
  const content = page.getByLabel("Content", { exact: true });
  await content
    .locator('[data-content-type="bulletListItem"] .bn-inline-content')
    .first()
    .fill("Stale draft (src: self, 2030-01-01)");
  await save(page);
  await page.route("**/api/backend/notes/previews/*/confirm", (route) =>
    route.fulfill({
      status: 409,
      contentType: "application/json",
      body: JSON.stringify({
        detail:
          "another change was saved while you were editing — please refresh.",
        code: "brain_stale",
        completed: 0,
      }),
    }),
  );
  await page.getByRole("button", { name: "Confirm changes" }).click();
  await expect(page.locator(".save-state")).toHaveAttribute(
    "data-save-state",
    "conflict",
  );
  await expect(content).toContainText("Stale draft");
  await expect(
    page
      .getByRole("alert")
      .filter({ hasText: "another change was saved" })
      .first(),
  ).toBeVisible();
  await page.getByRole("button", { name: "Reload latest note" }).click();
  await expect(content).not.toContainText("Stale draft");
});

test("deletion preview warns about permanence, and mobile retains the existing notebook layout", async ({
  page,
}) => {
  await auth(page);
  const content = page.getByLabel("Content", { exact: true });
  const first = content
    .locator('[data-content-type="bulletListItem"] .bn-inline-content')
    .first();
  await first.click();
  await page.getByRole("button", { name: "Remove block", exact: true }).click();
  await save(page);
  await expect(page.getByRole("dialog")).toContainText(
    "This deletion cannot be undone.",
  );
  await page.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(page.getByRole("dialog")).toBeHidden();
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(
    page.getByRole("complementary", { name: "Notes navigation" }),
  ).toHaveCount(0);
  await expect(content).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "verification/notes-brain-phone.png",
    fullPage: true,
  });
});
