import { expect, test, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import {
  addDays,
  dateInZone,
  type PlanningSnapshot,
} from "../src/lib/planning";
const origin = "http://127.0.0.1:3100";
const day = () => dateInZone(new Date(), "Europe/Berlin");
async function auth(page: Page) {
  await page.route("https://api.open-meteo.com/**", (route) => route.abort());
  const { password } = JSON.parse(
    readFileSync("../api/runtime/browser-session.json", "utf8"),
  );
  expect(
    (
      await page.request.post("/api/backend/auth/login", {
        data: { password },
        headers: { Origin: origin },
      })
    ).ok(),
  ).toBe(true);
}
async function command(
  page: Page,
  op: string,
  data: Record<string, unknown>,
  id?: string,
  version?: number,
) {
  const session = await (
    await page.request.get("/api/backend/auth/session")
  ).json();
  const result = await page.request.post(
    "/api/backend/application/planning/commands",
    {
      headers: { Origin: origin, "X-Yggdress-CSRF": session.csrf },
      data: { key: crypto.randomUUID(), op, data, id, version },
    },
  );
  expect(result.ok(), await result.text()).toBe(true);
  return result.json();
}
async function snapshot(page: Page): Promise<PlanningSnapshot> {
  return (
    await page.request.get(
      `/api/backend/application/planning?start=${day()}&end=${addDays(day(), 6)}&timezone=Europe%2FBerlin`,
    )
  ).json();
}

test("empty Today has no demo cards, synthetic requests, or fake AI actions", async ({
  page,
}) => {
  await auth(page);
  let syntheticReads = 0;
  page.on("request", (request) => {
    if (request.url().includes("/api/backend/brain/")) syntheticReads++;
  });
  await page.route("**/api/backend/application/planning?**", async (route) => {
    const response = await route.fetch();
    const data = await response.json();
    await route.fulfill({
      response,
      json: {
        ...data,
        tasks: [],
        blocks: [],
        events: [],
        routines: [],
        sessions: [],
        summaries: [],
      },
    });
  });
  await page.goto("/today");
  await expect(
    page.getByText("Nothing scheduled today.", { exact: true }),
  ).toBeVisible();
  await expect(
    page.locator(
      ".insights-panel,.quote-banner,.today-bottom,.floating-capture,.integration-banner,.routine-execution-card",
    ),
  ).toHaveCount(0);
  await expect(
    page.getByRole("navigation", { name: "Main navigation" }).getByRole("link"),
  ).toHaveText(["Today", "Calendar", "Tasks", "Notes", "Graph"]);
  await expect(page.getByText("Ask Brain", { exact: true })).toHaveCount(0);
  expect(syntheticReads).toBe(0);
  await page.screenshot({
    path: "../api/runtime/signal-today-empty-desktop.png",
  });
  await page.goto("/dashboard");
  await expect(page).toHaveURL(/\/today$/);
  await page.goto("/areas/work");
  await expect(page).toHaveURL(/\/notes$/);
});

test("a chosen task survives reload and execution saves preserve its goal", async ({
  page,
}) => {
  await auth(page);
  const title = "Synthetic · Outline the garden plan";
  const created = await command(page, "task.create", {
    title,
    objective: "Write the three planting decisions.",
    due_date: day(),
    area: "work",
    estimated_minutes: 20,
  });
  await page.goto("/today");
  await page
    .getByRole("button", { name: `Focus on ${title}`, exact: true })
    .click();
  const current = page.locator(".current-task");
  await expect(
    page.getByRole("heading", { name: title, exact: true }),
  ).toBeFocused();
  await expect(current).toContainText("Write the three planting decisions.");
  await page.reload();
  await expect(current).toContainText(title);
  await current
    .getByRole("button", { name: "Start timer", exact: true })
    .click();
  await expect(
    current.getByRole("button", { name: "Pause timer" }),
  ).toBeVisible();
  await current.getByRole("button", { name: "Pause timer" }).click();
  await expect(
    current.getByRole("button", { name: "Resume timer" }),
  ).toBeVisible();
  await page.reload();
  await expect(
    current.getByRole("button", { name: "Resume timer" }),
  ).toBeVisible();
  await page.screenshot({
    path: "../api/runtime/signal-today-synthetic-desktop.png",
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({
    path: "../api/runtime/signal-today-synthetic-mobile.png",
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  let fail = true;
  await page.route("**/api/backend/application/planning/commands", (route) => {
    if (fail && route.request().postDataJSON()?.op === "task.execute")
      return route.fulfill({
        status: 503,
        json: { detail: "Could not save task. Try again." },
      });
    return route.continue();
  });
  await current.getByRole("button", { name: "Complete", exact: true }).click();
  await expect(page.locator(".planning-error")).toContainText(
    "Could not save task",
  );
  await expect(current).toContainText(title);
  expect(
    (await snapshot(page)).tasks.find((task) => task.id === created.id)?.state,
  ).toBe("paused");
  fail = false;
  await current.getByRole("button", { name: "Complete", exact: true }).click();
  await expect(
    page.getByRole("status").filter({ hasText: /^Saved$/ }),
  ).toBeVisible();
  const saved = (await snapshot(page)).tasks.find(
    (task) => task.id === created.id,
  )!;
  expect(saved.state).toBe("completed");
  expect(saved.objective).toBe("Write the three planting decisions.");
});

test("global search opens connected Notes and failures do not show demo results", async ({
  page,
}) => {
  await auth(page);
  await page.goto("/today");
  const search = page.getByRole("combobox", {
    name: "Search notes",
    exact: true,
  });
  await search.fill("Sample");
  await expect(
    page.getByRole("option").filter({ hasText: "Sample" }),
  ).toBeVisible();
  await search.press("ArrowDown");
  await search.press("Enter");
  await expect(page).toHaveURL(/\/notes\?note=sample$/);
  await expect(page.getByLabel("Title", { exact: true })).toHaveValue(
    "Sample",
    { timeout: 60000 },
  );
  await expect(page.getByLabel("Toggle note context")).toHaveAttribute(
    "aria-expanded",
    "false",
  );
  await page.route("**/api/backend/notes/search?q=missing-service", (route) =>
    route.fulfill({
      status: 503,
      json: { detail: "Notes search unavailable" },
    }),
  );
  await search.fill("missing-service");
  await expect(
    page.getByRole("alert").filter({ hasText: "Notes search unavailable" }),
  ).toBeVisible();
  await expect(page.getByRole("option")).toHaveCount(0);
  await search.press("Escape");
  await expect(
    page.getByRole("listbox", { name: "Search results" }),
  ).toHaveCount(0);
  await page.goto("/today");
  await page.keyboard.press("Control+Shift+N");
  await expect(page).toHaveURL(/\/notes\?new=1$/);
  await expect(page.getByLabel("Title", { exact: true })).toHaveValue("", {
    timeout: 60000,
  });
  await expect(page.locator(".bn-editor")).toBeVisible();
});

test("Calendar scheduling and task filters remain available on request", async ({
  page,
}) => {
  await auth(page);
  await page.goto("/calendar");
  await expect(
    page.getByRole("heading", { name: "Calendar", exact: true }),
  ).toBeVisible();
  await expect(page.locator(".planning-calendar-rail")).toHaveCount(0);
  await page
    .getByRole("button", { name: "Schedule tasks", exact: true })
    .click();
  await expect(page.getByLabel("Find unscheduled tasks")).toBeVisible();
  await page
    .getByRole("button", { name: "Schedule tasks", exact: true })
    .click();
  await expect(page.locator(".planning-calendar-rail")).toHaveCount(0);
  await page.goto("/tasks");
  await expect(page.getByLabel("Filter priority")).toBeHidden();
  await page.getByText("Filters & sort", { exact: true }).click();
  await expect(page.getByLabel("Filter priority")).toBeVisible();
  await page.getByLabel("Filter priority").selectOption("1");
  await expect(
    page.getByText("Filters & sort · applied", { exact: true }),
  ).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.goto("/settings");
  await expect(
    page.getByRole("heading", { name: "Settings", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("switch", { name: "Enable demo reminders" }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("switch", { name: "Reduce transparency", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("switch", { name: "Reduce transparency", exact: true })
    .click();
  await expect(page.locator("html")).toHaveAttribute(
    "data-transparency",
    "reduced",
  );
});
