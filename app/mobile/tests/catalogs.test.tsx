import { fireEvent, render, screen } from "@testing-library/react-native";
import {
  Connectors,
  Skills,
  connectorState,
  groupConnectors,
  unlockedBy,
} from "../src/catalogs";

const mockRequest = jest.fn();
jest.mock("../src/api", () => ({
  request: (...args: unknown[]) => mockRequest(...args),
}));

const gmail = {
  name: "gmail",
  title: "Gmail",
  domain: "email",
  group: "Google",
  description: "Search and read mail.",
  status: "connected" as const,
  enabled: true,
  missing_env: [],
  tools: ["gmail__search"],
  tool_count: 3,
};
const notion = {
  ...gmail,
  name: "notion",
  title: "Notion",
  domain: "documents",
  group: "Notes & docs",
  status: "available" as const,
  enabled: false,
};
const skills = [
  { name: "send-email", description: "Draft and send.", domains: ["email"] },
];

beforeEach(() => {
  mockRequest.mockReset();
  mockRequest.mockImplementation(async (path: string) => {
    if (path === "yggdras/connectors") return [notion, gmail];
    if (path === "yggdras/skills") return skills;
    if (path === "yggdras/skills/send-email")
      return { ...skills[0], instructions: "Tone: short, warm and direct." };
    throw new Error(`unexpected ${path}`);
  });
});

test("helpers group apps and say where each stands", () => {
  expect(unlockedBy(gmail, skills)).toEqual(["send-email"]);
  expect(connectorState(gmail)).toBe("Connected · 3 tools");
  expect(connectorState(notion)).toBe("Not connected");
  expect(groupConnectors([notion, gmail]).map((g) => g.group)).toEqual([
    "Notes & docs",
    "Google",
  ]);
});

test("the phone lists the app directory read-only and never connects", async () => {
  render(<Connectors active />);
  expect(await screen.findByText("Gmail")).toBeTruthy();
  expect(screen.getByText("Used by Send email")).toBeTruthy();
  expect(screen.queryByText("Connect")).toBeNull();
  fireEvent.changeText(screen.getByLabelText(/Find an app/), "noti");
  expect(screen.queryByText("Gmail")).toBeNull();
  expect(screen.getByText("Notion")).toBeTruthy();
  expect(
    mockRequest.mock.calls.every(
      ([, init]) => !init || (init as RequestInit).method === undefined,
    ),
  ).toBe(true);
});

test("a skill opens to show its instructions", async () => {
  render(<Skills active />);
  fireEvent.press(await screen.findByLabelText("Open Send email"));
  expect(await screen.findByText("Tone: short, warm and direct.")).toBeTruthy();
});
