import { describe, expect, it } from "vitest";
import {
  connectorState,
  connectorsFor,
  groupConnectors,
  humanize,
  statusOf,
  unlockedBy,
  type Connector,
  type Skill,
} from "@/lib/catalog";

const gmail: Connector = {
  name: "gmail",
  title: "Gmail",
  domain: "email",
  group: "Google",
  description: "Search and read mail.",
  enabled: true,
  status: "connected",
  missing_env: [],
  tools: ["gmail__search"],
  tool_count: 2,
};
const notion: Connector = {
  ...gmail,
  name: "notion",
  title: "Notion",
  domain: "documents",
  group: "Notes & docs",
  status: "available",
  enabled: false,
};
const calendar: Connector = {
  ...gmail,
  name: "google-calendar",
  title: "Google Calendar",
  domain: "calendar",
  status: "needs_setup",
  enabled: false,
  missing_env: ["YGGDRAS_GOOGLE_CLIENT_ID"],
};
const outlook: Connector = {
  ...gmail,
  name: "microsoft-365",
  title: "Microsoft 365",
  group: "Microsoft",
  status: "unavailable",
  enabled: false,
};
const skills: Skill[] = [
  { name: "send-email", description: "Draft and send", domains: ["email"] },
  { name: "plan-week", description: "Plan", domains: ["tasks", "calendar"] },
];

describe("connector directory helpers", () => {
  it("links connected apps and skills through their shared domain", () => {
    expect(unlockedBy(gmail, skills)).toEqual(["send-email"]);
    expect(connectorsFor(skills[0], [gmail, notion])).toEqual(["Gmail"]);
    expect(connectorsFor(skills[1], [calendar])).toEqual([]); // not connected yet
  });
  it("says plainly where each app stands", () => {
    expect(connectorState(gmail)).toBe("Connected · 2 tools");
    expect(connectorState({ ...gmail, enabled: false })).toBe("Connected · switched off");
    expect(connectorState(notion)).toBe("Not connected");
    expect(connectorState(calendar)).toBe("Needs YGGDRAS_GOOGLE_CLIENT_ID in .env");
    expect(connectorState(outlook)).toBe("Not available yet");
  });
  it("treats an older file entry by its env and switch", () => {
    const own = { ...notion, status: undefined, group: undefined };
    expect(statusOf(own)).toBe("available");
    expect(statusOf({ ...own, missing_env: ["X"] })).toBe("needs_setup");
  });
  it("groups apps in order, connected first, and filters by name", () => {
    const groups = groupConnectors([calendar, outlook, gmail, notion]);
    expect(groups.map((g) => g.group)).toEqual(["Google", "Microsoft", "Notes & docs"]);
    expect(groups[0].items.map((c) => c.name)).toEqual(["gmail", "google-calendar"]);
    expect(groupConnectors([gmail, notion], "notio")).toEqual([
      { group: "Notes & docs", items: [notion] },
    ]);
  });
  it("turns skill names into titles", () => {
    expect(humanize("send-email")).toBe("Send email");
  });
});
