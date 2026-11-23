import { test, expect, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import { randomUUID } from "node:crypto";

test.skip(
  !process.env.YGGDRESS_SYNTHETIC_AGENTS,
  "Uses only the dedicated synthetic-agent harness.",
);

async function login(page: Page) {
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
  await page.goto("/chat");
}

async function headers(page: Page) {
  const session = await (
    await page.request.get("/api/backend/auth/session")
  ).json();
  return { Origin: "http://127.0.0.1:3100", "X-Yggdress-CSRF": session.csrf };
}

test("Yggdras delegates, Chat preserves its destination, and owner approves the exact task", async ({
  page,
}) => {
  await login(page);
  await page
    .getByLabel("Message", { exact: true })
    .fill("Create the synthetic agent task due 2 January 2030.");
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await expect(
    page.getByRole("article", { name: "Yggdras message", exact: true }),
  ).toContainText("synthetic proposal", { timeout: 30000 });
  await page.getByRole("button", { name: /Review changes \(/ }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText("Keep the original synthetic goal.");
  await page.screenshot({
    path: "../api/runtime/agents-chat-review.png",
    fullPage: true,
  });
  await dialog
    .getByRole("button", { name: "Apply reviewed change", exact: true })
    .click();
  await expect(dialog).toContainText("Nothing needs your decision.");
  await page.reload();
  const tasks = await (
    await page.request.get("/api/backend/application/tasks")
  ).json();
  expect(
    tasks.tasks.filter(
      (task: { title: string }) => task.title === "Synthetic agent task",
    ),
  ).toHaveLength(1);
  const status = await (
    await page.request.get("/api/backend/application/agents/status")
  ).json();
  expect(
    status.runs.some((run: { state: string }) => run.state === "completed"),
  ).toBe(true);
  if (process.env.YGGDRESS_TEMPORAL_AGENTS === "1") {
    expect(status.execution.provider).toBe("temporal");
    expect(status.execution.ready).toBe(true);
    const executions = await (
      await page.request.get("/api/backend/application/agents/executions")
    ).json();
    const trace = await (
      await page.request.get(
        `/api/backend/application/agents/executions/${executions.executions[0].id}`,
      )
    ).json();
    expect(trace.steps.length).toBeGreaterThan(2);
    expect(trace.timings.pickup_ms).toBeGreaterThanOrEqual(0);
    expect(trace.steps.every((step: object) => !("result" in step))).toBe(true);
  }
});

test("a saved-only message does not run, and private agent interfaces stay inaccessible", async ({
  page,
}) => {
  await login(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByLabel("Message", { exact: true })).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  const created = await page.request.post("/api/backend/chat/commands", {
    headers: await headers(page),
    data: {
      key: randomUUID(),
      operation: "conversation.create",
      data: { title: "Held synthetic history" },
    },
  });
  const conversation = (await created.json()).conversation;
  const saved = await page.request.post("/api/backend/chat/commands", {
    headers: await headers(page),
    data: {
      key: randomUUID(),
      operation: "message.send",
      id: conversation.id,
      data: {
        content: "Do not process this saved-only message",
        deliver: false,
      },
    },
  });
  const request = (await saved.json()).request;
  await page.waitForTimeout(2500);
  const history = await (
    await page.request.get(`/api/backend/chat/conversations/${conversation.id}`)
  ).json();
  expect(
    history.requests.find((item: { id: string }) => item.id === request.id)
      .state,
  ).toBe("held");
  expect(history.messages).toHaveLength(1);
  expect(
    (await page.request.get("/api/backend/receivers/chat/pending")).status(),
  ).toBe(404);
});
