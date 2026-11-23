import { expect, test, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import { dateInZone } from "../src/lib/planning";

async function auth(page: Page) {
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
async function headers(page: Page) {
  const session = await (
    await page.request.get("/api/backend/auth/session")
  ).json();
  return { Origin: "http://127.0.0.1:3100", "X-Yggdress-CSRF": session.csrf };
}
async function menu(page: Page) {
  const options = page.locator(".chat-options");
  if ((await options.getAttribute("open")) === null)
    await options.locator("summary").click();
}
test.afterEach(async ({ page }) => {
  for (const archived of [false, true]) {
    const response = await page.request.get(
      `/api/backend/chat/conversations?archived=${archived}`,
    );
    if (!response.ok()) continue;
    for (const conversation of (await response.json()).conversations) {
      const deleted = await page.request.post("/api/backend/chat/commands", {
        headers: await headers(page),
        data: {
          key: crypto.randomUUID(),
          operation: "conversation.delete",
          id: conversation.id,
          version: conversation.version,
          data: {},
        },
      });
      expect(deleted.ok()).toBe(true);
    }
  }
});

test("local chat saves history, edits, renames, searches, exports, archives, and deletes without fake replies", async ({
  page,
}) => {
  await auth(page);
  await page.goto("/chat");
  const navigation = await page
    .getByRole("navigation", { name: "Main navigation", exact: true })
    .getByRole("link")
    .allTextContents();
  expect(navigation.indexOf("Chat")).toBe(navigation.indexOf("Graph") + 1);
  const input = page.getByLabel("Message", { exact: true });
  await input.fill("Synthetic daily conversation");
  await page.getByRole("button", { name: "Save message", exact: true }).click();
  await expect(
    page.getByRole("article", { name: "Your message", exact: true }),
  ).toContainText("Synthetic daily conversation");
  await expect(
    page.getByRole("article", { name: "Yggdras message", exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByText("Saved · not submitted for processing", { exact: true }),
  ).toBeVisible();
  await input.fill("Unsent synthetic draft");
  await page.reload();
  await expect(input).toHaveValue("Unsent synthetic draft");
  await input.fill("");
  await page
    .getByRole("article", { name: "Your message", exact: true })
    .getByRole("button", { name: "Edit", exact: true })
    .click();
  await page
    .getByLabel("Edit message", { exact: true })
    .fill("Updated synthetic message");
  await page.getByRole("button", { name: "Save edit", exact: true }).click();
  await expect(
    page.getByRole("article", { name: "Your message", exact: true }),
  ).toContainText("Updated synthetic message");
  await menu(page);
  await page.getByRole("button", { name: "Rename", exact: true }).click();
  await page
    .getByLabel("Conversation title", { exact: true })
    .fill("Synthetic garden discussion");
  await page.getByRole("button", { name: "Save title", exact: true }).click();
  await expect(page.locator(".chat-heading h1")).toHaveText(
    "Synthetic garden discussion",
  );
  await page.getByLabel("Search conversations", { exact: true }).fill("garden");
  await expect(
    page.getByRole("navigation", { name: "Conversation history" }),
  ).toContainText("Synthetic garden discussion");
  await menu(page);
  const download = page.waitForEvent("download");
  await page
    .getByRole("button", { name: "Export conversation", exact: true })
    .click();
  const exported = JSON.parse(
    readFileSync((await (await download).path())!, "utf8"),
  );
  expect(exported.messages[0].content).toBe("Updated synthetic message");
  await page.screenshot({
    path: "../api/runtime/foundations-chat-desktop.png",
    fullPage: true,
  });
  await menu(page);
  await page.getByRole("button", { name: "Archive", exact: true }).click();
  await page.getByLabel("Archived", { exact: true }).check();
  await page
    .getByRole("navigation", { name: "Conversation history" })
    .getByRole("button", { name: /Synthetic garden discussion/ })
    .click();
  await expect(input).toBeDisabled();
  await menu(page);
  await page.getByRole("button", { name: "Restore", exact: true }).click();
  await expect(input).toBeEnabled();
  await menu(page);
  await page
    .getByRole("button", { name: "Delete conversation", exact: true })
    .click();
  await page
    .getByRole("dialog", { name: "Delete conversation?" })
    .getByRole("button", { name: "Delete permanently", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Start a conversation", exact: true }),
  ).toBeVisible();
});

test("attachments, failure recovery, safe Markdown, keyboard sending and phone layouts", async ({
  page,
}) => {
  await auth(page);
  await page.goto("/chat");
  const input = page.getByLabel("Message", { exact: true });
  let failed = false;
  await page.route("**/api/backend/chat/commands", async (route) => {
    if (
      route.request().postDataJSON().operation === "message.send" &&
      !failed
    ) {
      failed = true;
      return route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Synthetic save interruption" }),
      });
    }
    return route.continue();
  });
  await input.fill(
    "Synthetic Markdown **message**\n\n```text\nlong code line\n```\n\n<script>window.chatUnsafe=true</script>\n\n![External image](https://example.invalid/tracker.png)",
  );
  await input.press("Enter");
  await expect(page.locator(".chat-page").getByRole("alert")).toContainText(
    "Synthetic save interruption",
  );
  await expect(input).toHaveValue(/Synthetic Markdown/);
  await page.getByRole("button", { name: "Save message", exact: true }).click();
  const message = page.getByRole("article", {
    name: "Your message",
    exact: true,
  });
  await expect(message.locator("strong")).toHaveText("message");
  expect(await page.evaluate(() => "chatUnsafe" in window)).toBe(false);
  await expect(message.locator("img")).toHaveCount(0);
  await page
    .getByLabel("Choose chat attachments", { exact: true })
    .setInputFiles({
      name: "synthetic-context.txt",
      mimeType: "text/plain",
      buffer: Buffer.from("Synthetic attachment content"),
    });
  await expect(page.locator(".chat-draft-attachments")).toContainText(
    "synthetic-context.txt",
  );
  await page.getByRole("button", { name: "Save message", exact: true }).click();
  await expect(page.locator(".chat-draft-attachments")).toHaveCount(0);
  await expect(
    page.getByRole("article", { name: "Your message", exact: true }),
  ).toHaveCount(2);
  for (const [name, width, height] of [
    ["tablet", 820, 1180],
    ["phone", 390, 844],
    ["small-phone", 320, 740],
  ] as const) {
    await page.setViewportSize({ width, height });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await expect(input).toBeVisible();
    if (name === "phone")
      await page.screenshot({
        path: "../api/runtime/foundations-chat-phone.png",
        fullPage: true,
      });
  }
  await page
    .getByRole("button", { name: "Open conversation history", exact: true })
    .click();
  await expect(
    page.getByRole("dialog", { name: "Conversations", exact: true }),
  ).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(
    page.getByRole("button", {
      name: "Open conversation history",
      exact: true,
    }),
  ).toBeFocused();
});

test("explicit focus transfers one timer while inspection leaves it alone", async ({
  page,
}) => {
  await auth(page);
  const day = dateInZone(new Date(), "Europe/Berlin");
  async function plan(
    op: string,
    data: object,
    item?: { id: string; version: number },
  ) {
    const response = await page.request.post(
      "/api/backend/application/planning/commands",
      {
        headers: await headers(page),
        data: {
          key: crypto.randomUUID(),
          op,
          data,
          id: item?.id,
          version: item?.version,
        },
      },
    );
    expect(response.ok()).toBe(true);
    return response.json();
  }
  const first = await plan("task.create", {
    title: "Synthetic focus first",
    objective: "Keep first goal",
    due_date: day,
  });
  const second = await plan("task.create", {
    title: "Synthetic focus second",
    objective: "Keep second goal",
    due_date: day,
  });
  await plan("task.execute", { action: "start" }, first);
  await page.goto("/today");
  await expect(page.locator(".current-task h2")).toHaveText(
    "Synthetic focus first",
  );
  await page
    .getByRole("button", {
      name: "Focus on Synthetic focus second",
      exact: true,
    })
    .click();
  await expect(page.locator(".current-task h2")).toHaveText(
    "Synthetic focus second",
  );
  await expect(
    page
      .locator(".current-task")
      .getByRole("button", { name: "Pause timer", exact: true }),
  ).toBeVisible();
  await page
    .locator(".quiet-agenda-title")
    .filter({ hasText: "Synthetic focus first" })
    .click();
  await expect(page.getByRole("dialog")).toBeVisible();
  const state = await (
    await page.request.get(
      `/api/backend/application/planning?start=${day}&end=${day}&timezone=Europe%2FBerlin`,
    )
  ).json();
  expect(
    state.sessions.filter(
      (session: { ended_at: string | null }) => !session.ended_at,
    ),
  ).toHaveLength(1);
  expect(
    state.sessions.find(
      (session: { ended_at: string | null }) => !session.ended_at,
    ).task_id,
  ).toBe(second.id);
  await page.keyboard.press("Escape");
  await page.reload();
  await expect(page.locator(".current-task h2")).toHaveText(
    "Synthetic focus second",
  );
  for (const id of [first.id, second.id]) {
    const task = state.tasks.find((task: { id: string }) => task.id === id);
    await plan("task.execute", { action: "complete" }, task);
  }
});
