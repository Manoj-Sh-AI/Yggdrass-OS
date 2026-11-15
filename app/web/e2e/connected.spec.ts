import { test, expect, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import { randomUUID } from "node:crypto";
import { dateInZone, addDays } from "../src/lib/planning";

const fixture = () =>
  JSON.parse(readFileSync("../api/runtime/browser-receivers.json", "utf8")) as {
    url: string;
    tokens: Record<string, string>;
  };
async function signIn(page: Page) {
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
}
async function receive(page: Page, path: string, scope: string, data: unknown) {
  const config = fixture();
  const response = await page.request.post(
    config.url + "/v1/receivers/" + path,
    { headers: { Authorization: "Bearer " + config.tokens[scope] }, data },
  );
  expect(response.ok(), await response.text()).toBeTruthy();
  return response.json();
}
async function command(
  page: Page,
  op: string,
  data: unknown,
  id?: string,
  version?: number,
) {
  const session = await (
    await page.request.get("/api/backend/auth/session")
  ).json();
  const response = await page.request.post(
    "/api/backend/application/planning/commands",
    {
      headers: {
        Origin: "http://127.0.0.1:3100",
        "X-Yggdress-CSRF": session.csrf,
      },
      data: { key: randomUUID(), op, data, id, version },
    },
  );
  expect(response.ok(), await response.text()).toBeTruthy();
  return response.json();
}

test("Lia handoff waits for an agent; linked updates, review and work graph stay connected", async ({
  page,
}) => {
  await signIn(page);
  const identity = randomUUID();
  const today = dateInZone(new Date(), "Europe/Berlin");
  const handoff = {
    id: randomUUID(),
    producer: "synthetic-lia",
    namespace: "synthetic-browser",
    external_identity: identity,
    sequence: 0,
    revision: "1",
    slug: "sample",
    context: "Synthetic deadline context",
    dates: [{ meaning: "deadline", precision: "date", value: { date: today } }],
  };
  await receive(page, "note-signals", "note_signals", handoff);
  const root =
    "application/work-graph/roots?query=" +
    encodeURIComponent("Receiving flow " + identity);
  expect(
    (await (await page.request.get("/api/backend/" + root)).json()).roots,
  ).toHaveLength(0);
  const title = "Receiving flow " + identity;
  const proposal = {
    commitment_identity: "finish",
    meaning: "deadline",
    precision: "date",
    disposition: "clear",
    entity_type: "task",
    data: { title, objective: "Keep this exact goal.", due_date: today },
  };
  const payload = {
    change_id: randomUUID(),
    handoff_id: handoff.id,
    producer: "synthetic-task-agent",
    producer_version: "test-v1",
    namespace: handoff.namespace,
    external_identity: identity,
    sequence: 0,
    revision: "1",
    slug: "sample",
    interpretations: [proposal],
  };
  const result = await receive(page, "workflow/changes", "workflow", payload);
  const task = result.results[0];
  expect(task.state).toBe("applied");
  await page.reload();
  await expect(page.locator(".today-due")).toContainText(title);
  await page.goto("/graph");
  await page
    .getByRole("button", { name: "Work connections", exact: true })
    .click();
  await page.getByLabel("Find a starting item").fill(title);
  await expect(
    page.getByRole("option", { name: new RegExp("Receiving flow") }),
  ).toHaveCount(1);
  await page
    .getByLabel("Work graph starting item")
    .selectOption("task:" + task.id);
  const graph = page.getByRole("group", { name: /Linked application work/ });
  await expect(graph.locator("[data-work-node]")).toHaveCount(2);
  await page.getByRole("button", { name: "Zoom work graph in" }).click();
  await graph.locator('[data-work-node^="note:"] circle').click();
  await page.getByRole("link", { name: "Open note", exact: true }).click();
  await expect(page).toHaveURL(/\/notes\?note=sample/);
  await expect(page.locator(".bn-editor")).toBeVisible({ timeout: 60000 });
  const changed = await command(
    page,
    "task.update",
    {
      title: "Owner changed receiving work",
      objective: "Keep this exact goal.",
      due_date: today,
    },
    task.id,
    task.version,
  );
  expect(changed.version).toBeGreaterThan(task.version);
  await receive(page, "workflow/changes", "workflow", {
    ...payload,
    change_id: randomUUID(),
    sequence: 1,
    previous_revision: "1",
    interpretations: [
      { ...proposal, data: { ...proposal.data, due_date: addDays(today, 1) } },
    ],
  });
  await page.reload();
  await page.getByRole("button", { name: /Review changes/ }).click();
  await expect(page.getByText(/edited independently/)).toBeVisible();
  await page.getByRole("button", { name: "Apply reviewed change" }).click();
  await expect(page.getByText("Nothing needs your decision.")).toBeVisible();
  await page.getByRole("button", { name: "Close dialog" }).click();
  await page.goto("/calendar");
  await expect(
    page.getByRole("heading", { name: "Calendar", exact: true }),
  ).toBeVisible();
  const dateTitle = "Synthetic agent review date";
  await receive(page, "workflow/changes", "workflow", {
    ...payload,
    change_id: randomUUID(),
    producer: "synthetic-calendar-agent",
    sequence: 2,
    previous_revision: "1",
    interpretations: [
      {
        commitment_identity: "review-date",
        meaning: "review",
        precision: "date",
        disposition: "clear",
        entity_type: "date_item",
        data: {
          title: dateTitle,
          kind: "review",
          starts_on: today,
          ends_before: addDays(today, 1),
        },
      },
    ],
  });
  await expect(
    page.getByRole("button", { name: new RegExp(dateTitle) }).first(),
  ).toBeVisible({ timeout: 45000 });

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/graph");
  await page
    .getByRole("button", { name: "Work connections", exact: true })
    .click();
  await expect
    .poll(() =>
      page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
    )
    .toBeTruthy();
  await expect(page.locator(".work-graph-canvas [data-work-node]")).toHaveCount(
    2,
  );
  await page.screenshot({
    path: "../api/runtime/connected-work-graph-phone.png",
    fullPage: true,
  });
  const privateAttempt = await page.request.post(
    "/api/backend/receivers/workflow/changes",
    { data: payload },
  );
  expect(privateAttempt.status()).toBe(404);
});

test("background state requests cancellation without completing work or stealing focus", async ({
  page,
}) => {
  await signIn(page);
  const runKey = randomUUID();
  const data = {
    event_key: randomUUID(),
    provider: "synthetic-browser-job",
    external_run_id: runKey,
    sequence: 0,
    label: "Synthetic background pipeline",
    state: "running",
  };
  const created = (await receive(page, "background/events", "background", data))
    .run;
  await page.reload();
  await page.getByText("Background activity", { exact: false }).first().click();
  await expect(
    page.getByText("Synthetic background pipeline", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Request cancellation", exact: true })
    .click();
  const dialog = page.getByRole("dialog");
  let failCancellation = true;
  await page.route(
    "**/api/backend/application/background/cancel",
    async (route) => {
      if (failCancellation) {
        failCancellation = false;
        await route.fulfill({
          status: 503,
          contentType: "application/json",
          body: JSON.stringify({
            detail: "Synthetic cancellation unavailable; retry your request.",
          }),
        });
      } else await route.continue();
    },
  );
  await dialog
    .getByRole("button", { name: "Request cancellation", exact: true })
    .click();
  await expect(dialog.getByRole("alert")).toContainText(
    "Synthetic cancellation unavailable",
  );
  await expect(dialog).toBeVisible();
  await dialog
    .getByRole("button", { name: "Request cancellation", exact: true })
    .click();
  await expect(dialog).toBeHidden();
  const states = await (
    await page.request.get("/api/backend/application/background")
  ).json();
  const run = states.runs.find((r: { id: string }) => r.id === created.id);
  expect(run.state).toBe("running");
  expect(run.cancellation_requested_at).toBeTruthy();
  await receive(page, "background/events", "background", {
    ...data,
    event_key: randomUUID(),
    sequence: 1,
    state: "cancelled",
  });
  await page.reload();
  await page.getByText("Background activity", { exact: false }).first().click();
  await expect(page.getByText(/cancelled ·/)).toBeVisible();
});

test("chat agent and model choices survive reload and do not rewrite sent destinations", async ({
  page,
}) => {
  await signIn(page);
  await page.goto("/chat");
  await page.getByRole("button", { name: "New chat", exact: true }).click();
  const compose = page.getByLabel("Message", { exact: true });
  await compose.fill("Synthetic selector message");
  await page.getByLabel("Chat agent", { exact: true }).selectOption("lia");
  await expect(page.getByLabel("Chat agent", { exact: true })).toHaveValue(
    "lia",
  );
  await page
    .getByLabel("Chat model", { exact: true })
    .selectOption("synthetic-alpha");
  await expect(page.getByLabel("Chat model", { exact: true })).toHaveValue(
    "synthetic-alpha",
  );
  await page.reload();
  await expect(page.getByLabel("Chat agent", { exact: true })).toHaveValue(
    "lia",
  );
  await expect(page.getByLabel("Chat model", { exact: true })).toHaveValue(
    "synthetic-alpha",
  );
  await expect(compose).toHaveValue("Synthetic selector message");
  await page.getByRole("button", { name: "Save message", exact: true }).click();
  await expect(
    page
      .getByRole("article", { name: "Your message" })
      .getByText("Lia · Synthetic Alpha", { exact: true }),
  ).toBeVisible();
  await page.getByLabel("Chat agent", { exact: true }).selectOption("yggdras");
  await page
    .getByLabel("Chat model", { exact: true })
    .selectOption("synthetic-beta");
  await expect(page.getByLabel("Chat model", { exact: true })).toHaveValue(
    "synthetic-beta",
  );
  await expect(
    page.getByRole("button", { name: "Save message", exact: true }),
  ).toBeVisible();
  await expect(
    page
      .getByRole("article", { name: "Your message" })
      .getByText("Lia · Synthetic Alpha", { exact: true }),
  ).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await expect
    .poll(() =>
      page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
    )
    .toBeTruthy();
  await page.screenshot({
    path: "../api/runtime/connected-chat-selectors-phone.png",
    fullPage: true,
  });
});
