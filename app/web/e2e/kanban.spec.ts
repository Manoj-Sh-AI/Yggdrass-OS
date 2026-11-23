import { expect, test, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import {
  addDays,
  dateInZone,
  taskInput,
  type PlanningSnapshot,
  type PlanningTask,
} from "../src/lib/planning";

const origin = "http://127.0.0.1:3100";
const today = () => dateInZone(new Date(), "Europe/Berlin");
async function auth(page: Page) {
  await page.route("https://api.open-meteo.com/**", (route) => route.abort());
  const password = JSON.parse(
    readFileSync("../api/runtime/browser-session.json", "utf8"),
  ).password;
  const response = await page.request.post("/api/backend/auth/login", {
    data: { password },
    headers: { Origin: origin },
  });
  expect(response.ok()).toBe(true);
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
  const response = await page.request.post(
    "/api/backend/application/planning/commands",
    {
      headers: { Origin: origin, "X-Yggdress-CSRF": session.csrf },
      data: { key: crypto.randomUUID(), op, data, id, version },
    },
  );
  expect(response.ok(), await response.text()).toBe(true);
  return response.json();
}
async function snapshot(page: Page): Promise<PlanningSnapshot> {
  const response = await page.request.get(
    `/api/backend/application/planning?start=${today()}&end=${addDays(today(), 6)}&timezone=Europe%2FBerlin`,
  );
  expect(response.ok()).toBe(true);
  return response.json();
}
async function seedTask(page: Page, title: string) {
  const result = await command(page, "task.create", {
    title,
    objective: "Keep the original outcome exactly.",
    estimated_minutes: 25,
    due_date: today(),
    area: "work",
    tags: ["synthetic"],
  });
  return (await snapshot(page)).tasks.find((task) => task.id === result.id)!;
}
async function openBoard(page: Page, query = "") {
  await page.goto("/tasks");
  await expect(
    page.getByRole("button", { name: "Board", exact: true }),
  ).toBeVisible({ timeout: 60000 });
  await page.getByRole("button", { name: "Board", exact: true }).click();
  if (query) {
    await page.getByLabel("Search tasks").fill(query);
    await expect(page.locator(".kanban-card")).toHaveCount(1);
  }
}
const card = (page: Page, title: string) =>
  page
    .locator(".kanban-card")
    .filter({
      has: page.getByRole("button", { name: `Open ${title}`, exact: true }),
    });
const column = (page: Page, title: string) =>
  page.getByRole("region", { name: `${title} column`, exact: true });
async function expectState(
  page: Page,
  id: string,
  state: PlanningTask["state"],
) {
  await expect
    .poll(
      async () =>
        (await snapshot(page)).tasks.find((task) => task.id === id)?.state,
      { timeout: 60000 },
    )
    .toBe(state);
}

test("create, confirm/cancel timer moves, pause, complete, reload and reopen keep the outcome", async ({
  page,
}) => {
  await auth(page);
  await openBoard(page);
  const title = "Synthetic Kanban outcome";
  await page.getByRole("button", { name: "New task", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Task title", { exact: true }).fill(title);
  await dialog
    .getByLabel("Required outcome")
    .fill("Keep the original outcome exactly.");
  await dialog.getByLabel("Estimate (minutes)", { exact: true }).fill("25");
  await dialog.getByLabel("Due date", { exact: true }).fill(today());
  await dialog
    .getByRole("button", { name: "Create task", exact: true })
    .click();
  await expect(dialog).toBeHidden();
  await page.getByLabel("Search tasks").fill(title);
  await expect(card(page, title)).toBeVisible();
  const task = (await snapshot(page)).tasks.find(
    (task) => task.title === title,
  )!;
  await page
    .getByLabel(`Move ${title}`, { exact: true })
    .selectOption("in_progress");
  await expect(
    dialog.getByRole("heading", { name: "Start the focus timer?" }),
  ).toBeVisible();
  let current = await snapshot(page);
  expect(current.tasks.find((t) => t.id === task.id)!.state).toBe("todo");
  expect(
    current.sessions.filter((s) => s.task_id === task.id && !s.ended_at),
  ).toHaveLength(0);
  await dialog
    .getByRole("button", { name: "Cancel move", exact: true })
    .click();
  await expect(page.getByLabel(`Move ${title}`, { exact: true })).toBeFocused();
  await expect(column(page, "To do").locator(".kanban-card")).toContainText(
    title,
  );
  await page
    .getByLabel(`Move ${title}`, { exact: true })
    .selectOption("in_progress");
  await dialog
    .getByRole("button", { name: "Start timer", exact: true })
    .click();
  await expectState(page, task.id, "in_progress");
  await expect(
    column(page, "In progress").locator(".kanban-card"),
  ).toContainText(title);
  await page
    .getByLabel(`Move ${title}`, { exact: true })
    .selectOption("paused");
  await expectState(page, task.id, "paused");
  await page
    .getByLabel(`Move ${title}`, { exact: true })
    .selectOption("in_progress");
  await expect(
    dialog.getByRole("heading", { name: "Resume the focus timer?" }),
  ).toBeVisible();
  await dialog
    .getByRole("button", { name: "Resume timer", exact: true })
    .click();
  await expectState(page, task.id, "in_progress");
  await page
    .getByLabel(`Move ${title}`, { exact: true })
    .selectOption("completed");
  await expectState(page, task.id, "completed");
  await page.reload();
  await expect(
    column(page, "Done").locator(".kanban-card").filter({ hasText: title }),
  ).toBeVisible();
  await page.getByLabel(`Move ${title}`, { exact: true }).selectOption("todo");
  await expect(dialog).toContainText("resets progress");
  await dialog
    .getByRole("button", { name: "Cancel move", exact: true })
    .click();
  await expectState(page, task.id, "completed");
  await page.getByLabel(`Move ${title}`, { exact: true }).selectOption("todo");
  await dialog
    .getByRole("button", { name: "Return to To do", exact: true })
    .click();
  await expectState(page, task.id, "todo");
  current = await snapshot(page);
  expect(current.tasks.find((t) => t.id === task.id)!.objective).toBe(
    task.objective,
  );
  expect(current.tasks.find((t) => t.id === task.id)!.progress).toBe(0);
  expect(
    current.sessions.filter((s) => s.task_id === task.id && !s.ended_at),
  ).toHaveLength(0);
  await page.getByRole("button", { name: "List", exact: true }).click();
  await expect(
    page.getByRole("button", { name: `Open ${title}`, exact: true }),
  ).toBeVisible();
  await page.reload();
  await expect(
    page.getByRole("button", { name: "List", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
});

test("a failed move rolls back and an explicit retry saves once", async ({
  page,
}) => {
  await auth(page);
  const task = await seedTask(page, "Synthetic Kanban retry");
  await openBoard(page, task.title);
  let release!: () => void;
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  let failures = 0;
  await page.route(
    "**/api/backend/application/planning/commands",
    async (route) => {
      const body = route.request().postDataJSON();
      if (
        body.op === "task.execute" &&
        body.id === task.id &&
        failures++ === 0
      ) {
        await gate;
        await route.fulfill({
          status: 503,
          json: { detail: "Invented offline test. Try the move again." },
        });
      } else await route.continue();
    },
  );
  await page
    .getByLabel(`Move ${task.title}`, { exact: true })
    .selectOption("completed");
  try {
    await expect(column(page, "Done").locator(".kanban-card")).toContainText(
      task.title,
    );
  } finally {
    release();
  }
  await expect(page.locator(".kanban-error")).toContainText(
    "Invented offline test",
  );
  await expect(column(page, "To do").locator(".kanban-card")).toContainText(
    task.title,
  );
  await expectState(page, task.id, "todo");
  await page
    .getByLabel(`Move ${task.title}`, { exact: true })
    .selectOption("completed");
  await expectState(page, task.id, "completed");
  const saved = (await snapshot(page)).tasks.find((t) => t.id === task.id)!;
  expect(saved.version).toBe(task.version + 1);
  expect(saved.objective).toBe(task.objective);
});

test("a stale card cannot overwrite a newer task", async ({ page }) => {
  await auth(page);
  const task = await seedTask(page, "Synthetic Kanban stale version");
  await openBoard(page, task.title);
  await expect(card(page, task.title)).toBeVisible();
  const frozen = await snapshot(page);
  await page.route("**/api/backend/application/planning?**", (route) =>
    route.fulfill({ json: frozen }),
  );
  await command(
    page,
    "task.update",
    { ...taskInput(task, []), priority: 1 },
    task.id,
    task.version,
  );
  await page
    .getByLabel(`Move ${task.title}`, { exact: true })
    .selectOption("completed");
  await expect(page.locator(".kanban-error")).toBeVisible();
  await expect(column(page, "To do").locator(".kanban-card")).toContainText(
    task.title,
  );
  const current = (await snapshot(page)).tasks.find((t) => t.id === task.id)!;
  expect(current.done).toBe(false);
  expect(current.priority).toBe(1);
  expect(current.objective).toBe(task.objective);
});

test("pointer drag uses the same save path and moves into an empty column", async ({
  page,
}) => {
  await auth(page);
  const task = await seedTask(page, "Synthetic pointer move");
  await openBoard(page, task.title);
  const handle = await page
    .getByRole("button", { name: `Drag ${task.title}`, exact: true })
    .boundingBox();
  const target = await column(page, "Done").boundingBox();
  expect(handle).not.toBeNull();
  expect(target).not.toBeNull();
  await page.mouse.move(
    handle!.x + handle!.width / 2,
    handle!.y + handle!.height / 2,
  );
  await page.mouse.down();
  await expect(page.locator(".kanban-drag-preview")).toBeVisible();
  await page.mouse.move(
    handle!.x + handle!.width / 2 + 12,
    handle!.y + handle!.height / 2 + 6,
    { steps: 3 },
  );
  await page.mouse.move(target!.x + target!.width / 2, target!.y + 100, {
    steps: 18,
  });
  await expect(column(page, "Done")).toHaveClass(/drop-target/);
  await page.mouse.up();
  await expectState(page, task.id, "completed");
  await expect(column(page, "Done").locator(".kanban-card")).toContainText(
    task.title,
  );
});

test("10,000 synthetic tasks have accurate counts and a bounded initial DOM", async ({
  page,
}) => {
  await auth(page);
  const template = await seedTask(page, "Synthetic stress template");
  const base = await snapshot(page);
  const states = ["todo", "in_progress", "paused", "completed"] as const;
  const tasks = Array.from({ length: 10000 }, (_, i) => ({
    ...template,
    id: `stress-${i}`,
    title: `Invented card ${i}`,
    state: states[i % 4],
    done: i % 4 === 3,
  }));
  await page.route("**/api/backend/application/planning?**", (route) =>
    route.fulfill({ json: { ...base, tasks } }),
  );
  await openBoard(page);
  await expect(page.locator(".kanban-card")).toHaveCount(160, {
    timeout: 60000,
  });
  for (const title of ["To do", "In progress", "Paused", "Done"])
    await expect(column(page, title).locator("header>span")).toHaveText("2500");
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth > innerWidth,
    ),
  ).toBe(false);
});

test("phone keyboard-accessible moves keep the board inside the page", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await auth(page);
  const task = await seedTask(page, "Synthetic phone card");
  await openBoard(page, task.title);
  await expect(card(page, task.title)).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth > innerWidth,
    ),
  ).toBe(false);
  const move = page.getByLabel(`Move ${task.title}`, { exact: true });
  await move.focus();
  await move.selectOption("in_progress");
  await expect(page.getByRole("dialog")).toBeVisible();
  expect(
    await page
      .getByRole("dialog")
      .evaluate((e) => getComputedStyle(e).animationName),
  ).toBe("none");
  await page.getByRole("button", { name: "Cancel move", exact: true }).click();
  await expect(move).toBeFocused();
  await expectState(page, task.id, "todo");
});
