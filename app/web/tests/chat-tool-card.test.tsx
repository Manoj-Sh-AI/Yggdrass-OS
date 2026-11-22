// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { ToolCard } from "@/features/chat/parts/parts";
import type { ToolCall } from "@/features/chat/runtime/types";

afterEach(cleanup);

const tool = (over: Partial<ToolCall>): ToolCall => ({
  id: "0-u1", name: "read_calendar", state: "output-available", step_id: "s1",
  input: { start: "2026-11-23" }, output: { events: ["Invented lunch"] }, error: "",
  stakes: "low-reversible", decided_by: "rule", intent: "", approval: null, ...over,
});

describe("ToolCard", () => {
  it("collapses a success and opens on demand", () => {
    render(<ToolCard tool={tool({})} />);
    expect(screen.getByText("Completed")).toBeTruthy();
    expect(screen.queryByText(/Invented lunch/)).toBeNull();
    fireEvent.click(screen.getByRole("button", { expanded: false }));
    expect(screen.getByText(/Invented lunch/)).toBeTruthy();
  });
  it("opens an error by itself", () => {
    render(<ToolCard tool={tool({ state: "output-error", output: null, error: "Invented failure" })} />);
    expect(screen.getByText("Error")).toBeTruthy();
    expect(screen.getByText("Invented failure")).toBeTruthy();
  });
});
