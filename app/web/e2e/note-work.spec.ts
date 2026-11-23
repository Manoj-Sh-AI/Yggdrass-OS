import { expect, test, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import { dateInZone } from "../src/lib/planning";

const today = () => dateInZone(new Date(), "Europe/Berlin");
const created: { kind: "task" | "event"; id: string }[] = [];
async function headers(page: Page) {
  const { csrf } = await (
    await page.request.get("/api/backend/auth/session")
  ).json();
  return { Origin: "http://127.0.0.1:3100", "X-Yggdress-CSRF": csrf };
}
async function open(page: Page) {
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
  await openNote(page);
}
async function openNote(page: Page) {
  await page.goto("/notes?note=sample");
  await expect(page.locator(".bn-editor")).toBeVisible({ timeout: 60000 });
  const context = page.getByRole("button", { name: "Toggle note context" });
  if ((await context.getAttribute("aria-expanded")) !== "true")
    await context.click();
  await expect(
    page
      .getByRole("region", { name: "Linked work", exact: true })
      .getByRole("button", { name: "Create task", exact: true }),
  ).toBeVisible();
}
async function fillTask(page: Page, title: string) {
  await page
    .getByRole("region", { name: "Linked work", exact: true })
    .getByRole("button", { name: "Create task", exact: true })
    .click();
  const modal = page.getByRole("dialog", { name: "Create task from note" });
  await modal.getByLabel("Task title", { exact: true }).fill(title);
  await modal
    .getByLabel("Required outcome")
    .fill("Keep the written outcome unchanged.");
  await modal.getByLabel("Due date", { exact: true }).fill(today());
  return modal;
}
async function track(
  page: Page,
  kind: "task" | "event",
  click: () => Promise<unknown>,
) {
  const response = page.waitForResponse(
    (response) =>
      response.url().endsWith("/application/connections/from-note") &&
      response.ok(),
  );
  await click();
  const saved = await (await response).json();
  created.push({ kind, id: saved.id });
  return saved;
}
test.afterEach(async ({ page }) => {
  const snapshot = await (
    await page.request.get(
      `/api/backend/application/planning?start=${today()}&end=${today()}&timezone=Europe%2FBerlin`,
    )
  ).json();
  for (const record of created.splice(0)) {
    const item = (
      record.kind === "task" ? snapshot.tasks : snapshot.events
    ).find((item: { id: string }) => item.id === record.id);
    if (!item || item.done || item.cancelled) continue;
    const response = await page.request.post(
      "/api/backend/application/planning/commands",
      {
        headers: await headers(page),
        data: {
          key: crypto.randomUUID(),
          op: record.kind === "task" ? "task.execute" : "event.remove",
          id: item.id,
          version: item.version,
          data: record.kind === "task" ? { action: "complete" } : {},
        },
      },
    );
    expect(response.ok()).toBe(true);
  }
});

test("saved note creates shared task and event, preserves context through completion and unlink", async ({
  page,
}) => {
  await open(page);
  const title = "Synthetic connected proposal";
  let modal = await fillTask(page, title);
  await track(page, "task", () =>
    modal.getByRole("button", { name: "Create task", exact: true }).click(),
  );
  await expect(modal).toBeHidden();
  let work = page.getByRole("region", { name: "Linked work", exact: true });
  await expect(work).toContainText(title);
  await work.getByRole("button", { name: "Create event", exact: true }).click();
  modal = page.getByRole("dialog", { name: "Create event from note" });
  await modal
    .getByLabel("Event title", { exact: true })
    .fill("Synthetic connected review");
  await modal.getByLabel("Start", { exact: true }).fill(today() + "T10:00");
  await modal.getByLabel("End", { exact: true }).fill(today() + "T11:00");
  await track(page, "event", () =>
    modal.getByRole("button", { name: "Create event", exact: true }).click(),
  );
  await expect(modal).toBeHidden();
  await expect(work).toContainText("Synthetic connected review");
  await page.screenshot({
    path: "../api/runtime/note-work-linked-context.png",
    fullPage: true,
  });
  await page.goto("/calendar");
  await page.getByRole("tab", { name: "Month", exact: true }).click();
  await expect(page.locator(".calendar-grid")).toContainText(title);
  await expect(page.locator(".calendar-grid")).toContainText(
    "Synthetic connected review",
  );
  await page.goto("/today");
  await expect(page.locator(".today-workspace")).toContainText(title);
  await page
    .getByRole("button", { name: new RegExp(title) })
    .first()
    .click();
  modal = page.getByRole("dialog");
  await modal.getByText("Linked context", { exact: true }).click();
  await expect(
    modal.getByRole("link", { name: "Sample", exact: true }),
  ).toHaveAttribute("href", "/notes?note=sample");
  await modal
    .getByRole("button", { name: "Complete task", exact: true })
    .click();
  await modal
    .getByRole("button", { name: "Close dialog", exact: true })
    .click();
  await openNote(page);
  work = page.getByRole("region", { name: "Linked work", exact: true });
  await expect(work).toContainText("completed");
  await work
    .getByRole("button", {
      name: `Unlink ${title} from this note`,
      exact: true,
    })
    .click();
  await expect(
    work.getByRole("button", { name: title, exact: true }),
  ).toHaveCount(0);
  await page.reload();
  await page.getByRole("button", { name: "Toggle note context" }).click();
  await expect(
    page
      .getByRole("region", { name: "Linked work", exact: true })
      .getByRole("button", { name: title, exact: true }),
  ).toHaveCount(0);
});

test("failed and lost-response saves retain input and retry one committed task", async ({
  page,
}) => {
  await open(page);
  let attempt = 0;
  const keys: string[] = [];
  await page.route(
    "**/api/backend/application/connections/from-note",
    async (route) => {
      keys.push(route.request().postDataJSON().key);
      attempt++;
      if (attempt === 1)
        return route.fulfill({
          status: 503,
          contentType: "application/json",
          body: JSON.stringify({ detail: "Synthetic temporary outage" }),
        });
      if (attempt === 2) {
        await route.fetch();
        return route.abort("failed");
      }
      return route.continue();
    },
  );
  const title = "Synthetic recoverable bridge request";
  const modal = await fillTask(page, title);
  const save = modal.getByRole("button", { name: "Create task", exact: true });
  await save.click();
  await expect(modal.getByRole("alert")).toContainText(
    "Synthetic temporary outage",
  );
  await expect(modal.getByLabel("Task title", { exact: true })).toHaveValue(
    title,
  );
  await save.click();
  await expect(modal.getByRole("alert")).not.toContainText(
    "Synthetic temporary outage",
  );
  await expect(save).toBeEnabled();
  await track(page, "task", () => save.click());
  await expect(modal).toBeHidden();
  expect(new Set(keys).size).toBe(1);
  const context = await (
    await page.request.get("/api/backend/application/connections/notes/sample")
  ).json();
  expect(
    context.tasks.filter((task: { title: string }) => task.title === title),
  ).toHaveLength(1);
});

test("saved note revision changes retain task outcome and expose review context on phone", async ({
  page,
}) => {
  await open(page);
  const title = "Synthetic source revision check";
  const modal = await fillTask(page, title);
  await track(page, "task", () =>
    modal.getByRole("button", { name: "Create task", exact: true }).click(),
  );
  await expect(modal).toBeHidden();
  await page
    .locator('[data-content-type="bulletListItem"] .bn-inline-content')
    .first()
    .fill("Synthetic context changed (src: self, 2030-01-01)");
  await page.getByRole("button", { name: "Save now", exact: true }).click();
  const review = page.getByRole("dialog", { name: "Review note changes" });
  await review
    .getByRole("button", { name: "Confirm changes", exact: true })
    .click();
  await expect(
    page.getByRole("region", { name: "Linked work", exact: true }),
  ).toContainText("Source note changed — review this task.");
  const context = await (
    await page.request.get("/api/backend/application/connections/notes/sample")
  ).json();
  expect(
    context.tasks.find((task: { title: string }) => task.title === title)
      .objective,
  ).toBe("Keep the written outcome unchanged.");
  await page.setViewportSize({ width: 390, height: 844 });
  const toggle = page.getByRole("button", { name: "Toggle note context" });
  if ((await toggle.getAttribute("aria-expanded")) !== "true")
    await toggle.click();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "../api/runtime/note-work-phone.png",
    fullPage: true,
  });
  const undo = await page.request.post("/api/backend/notes/undo", {
    headers: await headers(page),
    data: {},
  });
  expect(undo.ok()).toBe(true);
});

test("existing work links without duplication and stale unlink offers a safe refresh", async ({
  page,
}) => {
  await open(page);
  const response = await page.request.post(
    "/api/backend/application/planning/commands",
    {
      headers: await headers(page),
      data: {
        key: crypto.randomUUID(),
        op: "task.create",
        data: {
          title: "Synthetic existing context",
          objective: "Preserve this existing outcome.",
        },
      },
    },
  );
  expect(response.ok()).toBe(true);
  const original = await response.json();
  created.push({ kind: "task", id: original.id });
  await openNote(page);
  const work = page.getByRole("region", { name: "Linked work", exact: true });
  await work.getByText("Link existing work", { exact: true }).click();
  await work
    .getByLabel("Find work", { exact: true })
    .fill("Synthetic existing context");
  await work
    .getByRole("combobox", { name: "Existing work", exact: true })
    .selectOption(original.id);
  await work.getByRole("button", { name: "Link to note", exact: true }).click();
  await expect(
    work.getByRole("button", {
      name: "Synthetic existing context",
      exact: true,
    }),
  ).toBeVisible();
  const context = await (
    await page.request.get("/api/backend/application/connections/notes/sample")
  ).json();
  const linked = context.tasks.find(
    (task: { id: string }) => task.id === original.id,
  );
  const progress = await page.request.post(
    "/api/backend/application/planning/commands",
    {
      headers: await headers(page),
      data: {
        key: crypto.randomUUID(),
        op: "task.execute",
        id: original.id,
        version: linked.version,
        data: { action: "progress", percent: 10 },
      },
    },
  );
  expect(progress.ok()).toBe(true);
  const unlink = work.getByRole("button", {
    name: "Unlink Synthetic existing context from this note",
    exact: true,
  });
  await unlink.click();
  await expect(work.getByRole("alert")).toContainText(
    "Refresh before changing its connections",
  );
  const refreshed = page.waitForResponse(
    (response) =>
      response.url().includes("/application/connections/notes/sample") &&
      response.ok(),
  );
  await work
    .getByRole("button", { name: "Refresh linked work", exact: true })
    .click();
  await refreshed;
  await unlink.click();
  await expect(
    work.getByRole("button", {
      name: "Synthetic existing context",
      exact: true,
    }),
  ).toHaveCount(0);
  const snapshot = await (
    await page.request.get(
      `/api/backend/application/planning?start=${today()}&end=${today()}&timezone=Europe%2FBerlin`,
    )
  ).json();
  expect(
    snapshot.tasks.filter((task: { id: string }) => task.id === original.id),
  ).toHaveLength(1);
});
