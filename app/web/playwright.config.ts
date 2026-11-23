import { defineConfig, devices } from "@playwright/test";
export default defineConfig({
  testDir: "./e2e",
  testMatch: [
    "phase1.spec.ts",
    "notes.spec.ts",
    "phase2.spec.ts",
    "graph.spec.ts",
    "nature-glass.spec.ts",
    "kanban.spec.ts",
    "signal-workspace.spec.ts",
    "calendar-design.spec.ts",
    "note-work.spec.ts",
    "chat.spec.ts",
    "temporal.spec.ts",
    "connected.spec.ts",
    "agents.spec.ts",
  ],
  fullyParallel: false,
  workers: 1,
  timeout: 120000,
  expect: { timeout: 15000 },
  use: {
    actionTimeout: 15000,
    baseURL: "http://127.0.0.1:3100",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "desktop",
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 1344, height: 896 },
        channel: process.env.PLAYWRIGHT_CHANNEL || "msedge",
      },
    },
  ],
});
