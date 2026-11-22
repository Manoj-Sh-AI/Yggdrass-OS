// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { DiffCard, TerminalCard } from "@/features/chat/parts/cards";
import { outputView, parseDiff, stripAnsi } from "@/features/chat/parts/logic";

afterEach(cleanup);

const DIFF = `--- a/invented-note.md
+++ b/invented-note.md
@@ -1,3 +1,3 @@
 # Invented garden
-Water on Monday
+Water on Tuesday
 Buy seeds
`;

describe("diff card", () => {
  it("classifies every line of a unified diff", () => {
    expect(parseDiff(DIFF).map((l) => l.kind)).toEqual([
      "file", "file", "hunk", "context", "remove", "add", "context",
    ]);
    expect(parseDiff(DIFF)[5]).toEqual({ kind: "add", text: "Water on Tuesday" });
  });
  it("shows counts and colours added and removed lines with tokens", () => {
    const { container } = render(<DiffCard diff={DIFF} />);
    expect(screen.getByText("+1")).toBeTruthy();
    expect(screen.getByText("-1")).toBeTruthy();
    expect(container.querySelector('[data-kind="add"]')!.className).toContain("bg-success-surface");
    expect(container.querySelector('[data-kind="remove"]')!.className).toContain("bg-danger-surface");
  });
});

describe("terminal card", () => {
  it("strips ANSI codes for the plain fallback", () => {
    expect(stripAnsi("\u001b[31mfailed\u001b[0m 2 tests")).toBe("failed 2 tests");
  });
  it("renders readable output and the exit code even without a canvas", () => {
    render(<TerminalCard output={"\u001b[32m3 passed\u001b[0m"} exitCode={1} />);
    expect(screen.getByText("3 passed")).toBeTruthy();
    expect(screen.getByText("exit 1").className).toContain("text-danger");
  });
});

describe("which card a tool output gets", () => {
  it.each([
    [{ diff: DIFF }, "diff"],
    [{ terminal: "ok", exit_code: 0 }, "terminal"],
    [{ events: [] }, "json"],
    [["a"], "json"],
    [null, "json"],
  ])("%j -> %s", (output, kind) => expect(outputView(output).kind).toBe(kind));
});
