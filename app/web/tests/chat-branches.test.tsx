// @vitest-environment jsdom
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { assistantParts, currentRun, liveRun, runStatus } from "@/features/chat/runtime/converter";
import type { AssistantMessage, Branch, RunState } from "@/features/chat/runtime/types";
import { branchIndex, branchLabel } from "@/features/chat/parts/logic";

vi.mock("@assistant-ui/react", async (real) => ({
  ...(await real<typeof import("@assistant-ui/react")>()),
  useAssistantTransportSendCommand: () => vi.fn(),
}));
const { Branches } = await import("@/features/chat/parts/parts");

afterEach(cleanup);

const base: RunState = JSON.parse(
  readFileSync(join(process.cwd(), "tests/fixtures/run-state.json"), "utf8"),
);
const run = (id: string, text: string, status: RunState["status"] = "completed"): RunState => ({
  ...base, run_id: id, status, text, plan: null, tools: [], reasoning: "", mode: "answering",
});
const branch = (id: string, text: string, status?: RunState["status"]): Branch => ({
  id, seq: 1, run: run(id, text, status),
});

describe("branch picker logic", () => {
  it("shows the newest answer first and jumps to a new one", () => {
    expect(branchIndex(null, 3, 0)).toBe(2);
    expect(branchIndex(0, 3, 3)).toBe(0); // the reader's choice is kept
    expect(branchIndex(0, 4, 3)).toBe(3); // a new answer arrived
    expect(branchIndex(9, 2, 2)).toBe(1);
  });
  it("labels as n/m", () => expect(branchLabel(1, 3)).toBe("2/3"));
});

describe("converter with branches", () => {
  const message: AssistantMessage = {
    id: "r1", role: "assistant", text: "", run: run("r1", "First"),
    branches: [branch("r1", "First"), branch("r2", "Second", "running")],
  };
  it("emits one branches part and takes status from the newest answer", () => {
    expect(assistantParts(message)).toEqual([
      { type: "data", name: "branches", data: { branches: message.branches } },
    ]);
    expect(currentRun(message)?.run_id).toBe("r2");
    expect(runStatus(currentRun(message))).toEqual({ type: "running" });
  });
  it("finds the live run inside the branches (for cancel)", () => {
    expect(liveRun({ conversationId: "c", messages: [message] })?.run_id).toBe("r2");
  });
  it("a single answer stays a plain run", () => {
    expect(assistantParts({ ...message, branches: [branch("r1", "First")] })[0]).toMatchObject({
      type: "data", name: "run",
    });
  });
});

describe("Branches", () => {
  it("pages between answers with < 2/3 >", () => {
    render(<Branches branches={[branch("a", "Answer one"), branch("b", "Answer two"), branch("c", "Answer three")]} />);
    expect(screen.getByText("3/3")).toBeTruthy();
    expect(screen.getByText("Answer three")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Previous answer" }));
    expect(screen.getByText("2/3")).toBeTruthy();
    expect(screen.getByText("Answer two")).toBeTruthy();
    expect((screen.getByRole("button", { name: "Next answer" }) as HTMLButtonElement).disabled).toBe(false);
  });
  it("disables the ends", () => {
    render(<Branches branches={[branch("a", "One"), branch("b", "Two")]} />);
    expect((screen.getByRole("button", { name: "Next answer" }) as HTMLButtonElement).disabled).toBe(true);
  });
});
