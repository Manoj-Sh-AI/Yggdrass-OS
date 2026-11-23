import { expect, test, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import { addDays, dateInZone } from "../src/lib/planning";
const today = () => dateInZone(new Date(), "Europe/Berlin");
async function signIn(page: Page) {
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
  const dismiss = page.getByRole("button", {
    name: "Dismiss location suggestion",
  });
  if (await dismiss.isVisible()) await dismiss.click();
}
async function headers(page: Page) {
  return {
    Origin: "http://127.0.0.1:3100",
    "X-Yggdress-CSRF": (
      await (await page.request.get("/api/backend/auth/session")).json()
    ).csrf,
  };
}
async function command(
  page: Page,
  op: string,
  data: Record<string, unknown>,
  id?: string,
  version?: number,
) {
  const response = await page.request.post(
    "/api/backend/application/planning/commands",
    {
      headers: await headers(page),
      data: { key: crypto.randomUUID(), op, data, id, version },
    },
  );
  expect(response.ok(), await response.text()).toBe(true);
  return response.json();
}
async function snapshot(page: Page) {
  return (
    await page.request.get(
      `/api/backend/application/planning?start=${today()}&end=${addDays(today(), 6)}&timezone=Europe%2FBerlin`,
    )
  ).json();
}
async function create(page: Page, title: string) {
  await page.goto("/tasks");
  await expect(page.locator(".planning-tasks-panel")).toBeVisible();
  await page.getByRole("button", { name: "New task", exact: true }).click();
  const modal = page.getByRole("dialog");
  await modal.getByLabel("Task title", { exact: true }).fill(title);
  await modal
    .getByLabel("Required outcome")
    .fill("Keep this exact objective through every schedule adjustment.");
  await modal.getByLabel("Due date", { exact: true }).fill(today());
  await modal.getByLabel("Estimate (minutes)", { exact: true }).fill("60");
  await modal
    .getByLabel("Tags (comma separated)", { exact: true })
    .fill("synthetic, planning");
  await modal.getByRole("button", { name: "Create task", exact: true }).click();
  await expect(modal).toBeHidden();
  await page.getByLabel("Search tasks").fill(title);
  await page
    .getByRole("button", { name: `Open ${title}`, exact: true })
    .click();
  await expect(page.getByRole("dialog")).toBeVisible();
}

test("task → schedule → drag → resize → split → focus → complete stays synchronized", async ({
  page,
}) => {
  await signIn(page);
  const title = "Synthetic Phase 2 crossing";
  await create(page, title);
  let modal = page.getByRole("dialog");
  await modal
    .getByRole("button", { name: "Schedule / reschedule", exact: true })
    .click();
  await modal.getByLabel("Start", { exact: true }).fill(today() + "T09:00");
  await modal.getByLabel("End", { exact: true }).fill(today() + "T10:00");
  await modal
    .getByRole("button", { name: "Schedule block", exact: true })
    .click();
  await expect(modal.locator(".planning-block-detail")).toContainText("09:00");
  await modal.getByRole("button", { name: "Close dialog" }).click();
  await page.goto("/calendar");
  await page.getByRole("tab", { name: "Day", exact: true }).click();
  const block = page.locator(".planning-time-item").filter({ hasText: title });
  await expect(block).toBeVisible();
  const slot = page.locator(
    `.planning-time-slot[aria-label="${today()} 11:00"]`,
  );
  await block
    .getByRole("button", { name: `Move time block ${title}`, exact: true })
    .dragTo(slot);
  await expect(block).toContainText("11:00–12:00");
  const resize = block.getByRole("button", { name: /^Resize/ });
  await resize.focus();
  await resize.press("ArrowDown");
  await expect(block).toContainText("11:00–12:15");
  const edge = await resize.boundingBox();
  expect(edge).not.toBeNull();
  await page.mouse.move(edge!.x + edge!.width / 2, edge!.y + edge!.height / 2);
  await page.mouse.down();
  await page.mouse.move(
    edge!.x + edge!.width / 2,
    edge!.y + edge!.height / 2 + 14,
    { steps: 8 },
  );
  await page.mouse.up();
  await expect(block).toContainText("11:00–12:30");
  const state = await snapshot(page);
  const task = state.tasks.find((t: { title: string }) => t.title === title);
  expect(task.due_date).toBe(today());
  expect(task.tags).toEqual(["synthetic", "planning"]);
  expect(task.objective).toBe(
    "Keep this exact objective through every schedule adjustment.",
  );
  await block.locator(".planning-time-content").click();
  modal = page.getByRole("dialog");
  await modal
    .getByRole("button", { name: "Split in two", exact: true })
    .click();
  await expect(modal.locator(".planning-block-detail")).toHaveCount(2);
  await modal.getByRole("button", { name: "Start focus", exact: true }).click();
  await expect(
    modal.getByRole("button", { name: "Pause", exact: true }),
  ).toBeVisible();
  await expect
    .poll(async () =>
      modal
        .getByRole("timer", { name: "Elapsed execution time", exact: true })
        .innerText(),
    )
    .not.toBe("00:00:00");
  await page.reload();
  await expect(
    page.locator(".planning-time-item").filter({ hasText: title }),
  ).toHaveCount(2);
  await page
    .locator(".planning-time-item")
    .filter({ hasText: title })
    .first()
    .locator(".planning-time-content")
    .click();
  modal = page.getByRole("dialog");
  await modal.getByRole("button", { name: "Pause", exact: true }).click();
  await expect(
    modal.getByRole("button", { name: "Resume", exact: true }),
  ).toBeVisible();
  await modal.getByRole("button", { name: "Resume", exact: true }).click();
  await modal
    .getByRole("button", { name: "Complete task", exact: true })
    .click();
  await expect(
    modal.getByRole("button", { name: "Reopen task", exact: true }),
  ).toBeVisible();
  await modal.getByRole("button", { name: "Close dialog" }).click();
  await expect(
    page.locator(".planning-time-item.done").filter({ hasText: title }),
  ).toHaveCount(2);
  await page.goto("/tasks");
  await page.getByRole("button", { name: "Completed", exact: true }).click();
  await page.getByLabel("Search tasks").fill(title);
  await expect(page.locator(".kanban-card")).toHaveCount(1);
  await page.getByRole("button", { name: "List", exact: true }).click();
  await expect(page.locator(".planning-task-row")).toHaveCount(1);
});

test("routine generation, single occurrence edits and explicit future-series edits", async ({
  page,
}) => {
  await signIn(page);
  await page.goto("/tasks");
  await page.getByRole("tab", { name: "Routines", exact: true }).click();
  await page.getByRole("button", { name: "New routine", exact: true }).click();
  let modal = page.getByRole("dialog");
  await modal
    .getByLabel("Routine title", { exact: true })
    .fill("Synthetic daily steady care");
  await modal
    .getByLabel("Routine goal / required outcome", { exact: true })
    .fill("Preserve the same care commitment.");
  await modal
    .getByRole("checkbox", { name: "Health / essential routine" })
    .check();
  await modal
    .getByRole("button", { name: "Create recurring routine", exact: true })
    .click();
  await expect(modal).toBeHidden();
  const state = await snapshot(page),
    template = state.routines.find(
      (r: { title: string }) => r.title === "Synthetic daily steady care",
    );
  expect(
    state.tasks.filter(
      (t: { template_id: string }) => t.template_id === template.id,
    ).length,
  ).toBeGreaterThanOrEqual(7);
  await page.getByRole("tab", { name: "Tasks", exact: true }).click();
  await page
    .locator(".planning-scopes")
    .getByRole("button", { name: "Today", exact: true })
    .click();
  await page.getByLabel("Search tasks").fill("Synthetic daily steady care");
  await page
    .getByRole("button", {
      name: "Open Synthetic daily steady care",
      exact: true,
    })
    .click();
  modal = page.getByRole("dialog");
  await modal
    .getByRole("button", {
      name: "Edit task / objective / deadline",
      exact: true,
    })
    .click();
  await modal
    .getByLabel("Task title", { exact: true })
    .fill("Synthetic care only today");
  await modal
    .getByRole("button", { name: "Save task changes", exact: true })
    .click();
  await expect(
    modal.getByRole("button", {
      name: "Edit task / objective / deadline",
      exact: true,
    }),
  ).toBeVisible();
  await expect(modal).toContainText("Preserve the same care commitment.");
  await modal.getByRole("button", { name: "Close dialog" }).click();
  await page.getByRole("tab", { name: "Routines", exact: true }).click();
  await page
    .locator(".planning-group")
    .filter({ hasText: "Synthetic daily steady care" })
    .getByRole("button", { name: "Edit future series", exact: true })
    .click();
  modal = page.getByRole("dialog");
  await modal
    .getByLabel("Routine title", { exact: true })
    .fill("Synthetic future steady care");
  await modal
    .getByRole("button", { name: "Apply to future untouched occurrences" })
    .click();
  await expect(modal).toBeHidden();
  await page.goto("/today");
  await page
    .getByRole("button", {
      name: "Focus on Synthetic care only today",
      exact: true,
    })
    .click();
  await expect(page.locator(".current-task")).toContainText(
    "Preserve the same care commitment.",
  );
  await page.reload();
  await expect(page.locator(".current-task")).toContainText(
    "Preserve the same care commitment.",
  );
});

test("daily planning, conflicts and evening review preserve every commitment", async ({
  page,
}) => {
  await signIn(page);
  const first = await command(page, "task.create", {
    title: "Synthetic capacity task",
    objective: "A preserved planned outcome",
    due_date: today(),
  });
  await command(page, "block.create", {
    task_id: first.id,
    start: today() + "T13:00",
    end: today() + "T14:00",
  });
  await command(page, "event.create", {
    title: "Synthetic fixed appointment",
    start: today() + "T13:30",
    end: today() + "T14:30",
  });
  await page.goto("/tasks?tab=plan");
  await page.getByLabel("Available time (minutes)").fill("30");
  await page.getByLabel("Energy · optional").selectOption("Low");
  await page
    .getByRole("button", { name: "Confirm daily plan", exact: true })
    .click();
  await expect(page.locator(".planning-warning")).toContainText(
    "over your capacity",
  );
  await page.getByRole("tab", { name: "Evening review", exact: true }).click();
  await page
    .getByLabel("Evening reflection")
    .fill("Move unfinished work deliberately tomorrow.");
  await page
    .getByRole("button", { name: "Save evening review", exact: true })
    .click();
  await page.reload();
  await page.getByRole("tab", { name: "Evening review", exact: true }).click();
  await expect(page.getByLabel("Evening reflection")).toHaveValue(
    "Move unfinished work deliberately tomorrow.",
  );
  await page.goto("/calendar");
  await expect(
    page.locator(".planning-calendar-page .planning-warning"),
  ).toContainText("overlapping items");
  await page.getByRole("tab", { name: "Month", exact: true }).click();
  await expect(page.locator(".calendar-grid")).toBeVisible();
  await page.getByRole("tab", { name: "Agenda", exact: true }).click();
  await expect(page.locator(".planning-agenda")).toContainText(
    "Synthetic fixed appointment",
  );
  const state = await snapshot(page);
  expect(
    state.tasks.find((t: { id: string }) => t.id === first.id).objective,
  ).toBe("A preserved planned outcome");
  expect(
    state.events.some(
      (e: { title: string }) => e.title === "Synthetic fixed appointment",
    ),
  ).toBe(true);
});

test("failed saves and stale edits keep entered content and keyboard focus", async ({
  page,
}) => {
  await signIn(page);
  await page.goto("/tasks");
  await page.getByRole("button", { name: "New task", exact: true }).click();
  const modal = page.getByRole("dialog");
  await modal
    .getByLabel("Task title", { exact: true })
    .fill("Synthetic retry UI");
  await modal
    .getByLabel("Required outcome")
    .fill("Keep the typed objective when a save fails.");
  await page.route(
    "**/api/backend/application/planning/commands",
    async (r) => {
      if (r.request().postDataJSON().op === "task.create")
        await r.fulfill({
          status: 503,
          json: { detail: "Synthetic service interruption. Try again." },
        });
      else await r.continue();
    },
  );
  await modal.getByRole("button", { name: "Create task", exact: true }).click();
  await expect(modal.getByRole("alert")).toContainText("interruption");
  await expect(modal.getByLabel("Required outcome")).toHaveValue(
    "Keep the typed objective when a save fails.",
  );
  await page.unroute("**/api/backend/application/planning/commands");
  await modal.getByRole("button", { name: "Create task", exact: true }).click();
  await expect(modal).toBeHidden();
  await page.getByRole("button", { name: "Inbox", exact: true }).click();
  await page.getByLabel("Search tasks").fill("Synthetic retry UI");
  await page
    .getByRole("button", { name: "Open Synthetic retry UI", exact: true })
    .click();
  await modal
    .getByRole("button", {
      name: "Edit task / objective / deadline",
      exact: true,
    })
    .click();
  await modal
    .getByLabel("Task title", { exact: true })
    .fill("Unsaved local title");
  const state = await snapshot(page),
    task = state.tasks.find(
      (t: { title: string }) => t.title === "Synthetic retry UI",
    );
  await command(
    page,
    "task.execute",
    { action: "progress", percent: 20 },
    task.id,
    task.version,
  );
  await modal
    .getByRole("button", { name: "Save task changes", exact: true })
    .click();
  await expect(modal.getByLabel("Task title", { exact: true })).toHaveValue(
    "Unsaved local title",
  );
  await expect(modal).toContainText("changed in another view");
  await page.keyboard.press("Escape");
  await expect(modal).toBeHidden();
});

test("desktop and phone planning layouts remain readable without page overflow", async ({
  page,
}) => {
  await signIn(page);
  await page.goto("/calendar");
  await page.getByRole("tab", { name: "Week", exact: true }).click();
  await expect(page.locator(".planning-time-body")).toBeVisible();
  await expect(page.getByText("Loading your shared calendar…")).toBeHidden();
  await page.screenshot({
    path: "verification/phase2-calendar-desktop.png",
    fullPage: true,
  });
  await page.goto("/tasks");
  await page.getByRole("button", { name: "All", exact: true }).click();
  await page.getByRole("button", { name: "Board", exact: true }).click();
  await expect(page.locator(".kanban-card").first()).toBeVisible();
  await page.screenshot({
    path: "verification/phase2-tasks-desktop.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  for (const route of ["/tasks", "/calendar", "/today", "/notes"]) {
    await page.goto(route);
    await expect(page.locator("main")).toBeVisible();
    if (route === "/tasks")
      await expect(page.locator(".planning-tasks-panel")).toBeVisible();
    if (route === "/calendar")
      await expect(page.locator(".planning-time-body")).toBeVisible();
    if (route === "/today")
      await expect(page.locator(".today-schedule")).toBeVisible();
    if (route === "/notes")
      await expect(page.locator(".bn-editor")).toBeVisible();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    if (route === "/calendar") {
      await page.getByRole("tab", { name: "Day", exact: true }).click();
      await page.screenshot({
        path: "verification/phase2-calendar-phone.png",
        fullPage: true,
      });
    }
  }
});

test("pointer scheduling from the rail and keyboard calendar navigation", async ({
  page,
}) => {
  await signIn(page);
  await command(page, "task.create", {
    title: "Synthetic pointer rail",
    objective: "Keep the inbox objective intact.",
    estimated_minutes: 45,
  });
  await page.goto("/calendar");
  const week = page.getByRole("tab", { name: "Week", exact: true });
  await week.focus();
  await week.press("Home");
  await expect(
    page.getByRole("tab", { name: "Day", exact: true }),
  ).toHaveAttribute("aria-selected", "true");
  await page
    .getByRole("button", { name: "Schedule tasks", exact: true })
    .click();
  const source = page.getByRole("button", {
    name: "Drag to schedule Synthetic pointer rail",
    exact: true,
  });
  await expect(source).toBeVisible();
  await source.dragTo(
    page.locator(`.planning-time-slot[aria-label="${today()} 10:00"]`),
  );
  const scheduled = page
    .locator(".planning-time-item")
    .filter({ hasText: "Synthetic pointer rail" });
  await expect(scheduled).toContainText("10:00–10:45");
  const state = await snapshot(page);
  expect(
    state.tasks.find(
      (t: { title: string }) => t.title === "Synthetic pointer rail",
    ).due_date,
  ).toBeNull();
});
