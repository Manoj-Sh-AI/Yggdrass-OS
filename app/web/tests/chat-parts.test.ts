import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { assistantParts, liveRun, runStatus, toMessages } from "@/features/chat/runtime/converter";
import {
  isRunState,
  type RunState,
  type Step,
  TOOL_STATES,
  type ToolCall,
} from "@/features/chat/runtime/types";
import {
  reasoningIsStreaming,
  stepView,
  TOOL_BADGE,
  toolOpensByDefault,
} from "@/features/chat/parts/logic";

const fixture: RunState = JSON.parse(
  readFileSync(new URL("./fixtures/run-state.json", import.meta.url), "utf8"),
);

describe("contract with the API (fixture written by app/api tests)", () => {
  it("validates as a RunState", () => expect(isRunState(fixture)).toBe(true));
  it("has exactly the keys the web types declare", () => {
    const runKeys: Record<keyof RunState, true> = {
      run_id: true, conversation_id: true, status: true, mode: true, plan: true, tools: true,
      reasoning: true, text: true, model: true, usage: true, error: true, branch_of: true,
      user_message: true,
    };
    const stepKeys: Record<keyof Step, true> = {
      id: true, title: true, status: true, depends_on: true, check: true, verdict: true,
      reason: true, attempts: true, model: true, result: true,
    };
    const toolKeys: Record<keyof ToolCall, true> = {
      id: true, name: true, state: true, step_id: true, input: true, output: true, error: true,
      stakes: true, decided_by: true, intent: true, approval: true,
    };
    expect(Object.keys(fixture).sort()).toEqual(Object.keys(runKeys).sort());
    expect(Object.keys(fixture.plan!.steps[0]).sort()).toEqual(Object.keys(stepKeys).sort());
    expect(Object.keys(fixture.tools[0]).sort()).toEqual(Object.keys(toolKeys).sort());
  });
});

describe("tool cards (B9)", () => {
  it("label exactly the seven states", () => {
    expect(Object.keys(TOOL_BADGE)).toEqual([...TOOL_STATES]);
    expect(TOOL_BADGE["approval-requested"]).toBe("Awaiting Approval");
  });
  it("collapse successes and expand errors and approvals", () => {
    const open = TOOL_STATES.filter(toolOpensByDefault);
    expect(open).toEqual(["approval-requested", "output-error"]);
  });
});

describe("reasoning opens only when all three hold", () => {
  it.each([
    [true, true, true, true],
    [false, true, true, false],
    [true, false, true, false],
    [true, true, false, false],
  ])("last=%s running=%s lastPartReasoning=%s -> %s", (last, running, part, expected) => {
    expect(
      reasoningIsStreaming({ isLastMessage: last, threadRunning: running, lastPartIsReasoning: part }),
    ).toBe(expected);
  });
});

describe("failed steps in a plan (own design)", () => {
  const step = (over: Partial<Step>): Step => ({
    id: "s1", title: "Find slots", status: "pending", depends_on: [], check: "ok",
    verdict: null, reason: "", attempts: 0, model: "", result: "", ...over,
  });
  it("shows retrying with the attempt count, then gave up, then skipped", () => {
    expect(stepView(step({ verdict: "failed", attempts: 1, reason: "No times." })).detail).toBe(
      "Retrying (2/3): No times.",
    );
    const gaveUp = stepView(step({ status: "completed", verdict: "failed", reason: "Gave up after 3 attempts: x" }));
    expect(gaveUp.tone).toBe("failed");
    expect(stepView(step({ status: "completed", verdict: "passed" })).tone).toBe("done");
  });
});

describe("converter", () => {
  it("renders the run as one data part, then reasoning, then the answer", () => {
    const parts = assistantParts({ id: fixture.run_id, role: "assistant", text: "", run: fixture });
    expect(parts.map((p) => p.type)).toEqual(["data", "reasoning", "text"]);
  });
  it("maps run status and finds the live run", () => {
    expect(runStatus(fixture)).toEqual({ type: "requires-action", reason: "interrupt" });
    expect(runStatus({ ...fixture, status: "failed", error: "x" })).toMatchObject({ type: "incomplete" });
    const thread = { conversationId: "c", messages: [{ id: fixture.run_id, role: "assistant" as const, text: "", run: fixture }] };
    expect(liveRun(thread)?.run_id).toBe(fixture.run_id);
    expect(liveRun({ ...thread, messages: [{ ...thread.messages[0], run: { ...fixture, status: "completed" } }] })).toBeNull();
  });
  it("shows a just-sent message before the server answers", () => {
    const messages = toMessages({ conversationId: null, messages: [] }, {
      pendingCommands: [{ type: "add-message", parentId: null, sourceId: null,
        message: { role: "user", id: "u1", parts: [{ type: "text", text: "Hi" }] } }],
    });
    expect(messages).toEqual([{ id: "u1", role: "user", content: [{ type: "text", text: "Hi" }] }]);
  });
});
