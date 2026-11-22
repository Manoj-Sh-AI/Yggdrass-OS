/** Rendering rules for message parts, as pure functions (tests/chat-parts.test.ts). */
import type { Step, ToolCall, ToolState } from "../runtime/types";

/** Badge per tool state: exactly the seven strings both card libraries expect [cited]. */
export const TOOL_BADGE: Record<ToolState, string> = {
  "input-streaming": "Pending",
  "input-available": "Running",
  "approval-requested": "Awaiting Approval",
  "approval-responded": "Responded",
  "output-available": "Completed",
  "output-error": "Error",
  "output-denied": "Denied",
};

/**
 * The clutter budget: successes collapse; errors and approvals expand.
 * The brief's table also lists output-available as auto-opening, which contradicts its
 * own rule ("successes collapse"); the rule wins here (flagged in DESIGN-DECISIONS.md).
 */
export function toolOpensByDefault(state: ToolState): boolean {
  return state === "approval-requested" || state === "output-error";
}

/**
 * Reasoning is "streaming" only when ALL THREE hold: it is the last message, the thread
 * is running, and the last part is the reasoning part [cited]. Otherwise older reasoning
 * blocks would reopen on every re-render.
 */
export function reasoningIsStreaming(o: {
  isLastMessage: boolean;
  threadRunning: boolean;
  lastPartIsReasoning: boolean;
}): boolean {
  return o.isLastMessage && o.threadRunning && o.lastPartIsReasoning;
}

export type StepView = {
  tone: "pending" | "active" | "done" | "failed" | "retrying";
  label: string;
  detail: string;
};

/**
 * A failed step inside a Plan [own design; no source documents it]: the step keeps the
 * three-value status; `verdict: failed` with a reason is shown with a danger glyph.
 * While another attempt is coming it reads "Retrying (n/3)"; after the last, "Gave up";
 * a step skipped because a dependency failed says which.
 */
export function stepView(step: Step, maxAttempts = 3): StepView {
  if (step.status === "completed" && step.verdict === "passed")
    return { tone: "done", label: step.title, detail: "" };
  if (step.status === "completed" && step.verdict === "failed")
    return { tone: "failed", label: step.title, detail: step.reason };
  if (step.verdict === "failed")
    return {
      tone: "retrying",
      label: step.title,
      detail: `Retrying (${Math.min(step.attempts + 1, maxAttempts)}/${maxAttempts}): ${step.reason}`,
    };
  if (step.status === "in_progress")
    return { tone: "active", label: step.title, detail: "" };
  return { tone: "pending", label: step.title, detail: "" };
}

/** Approval cards still waiting for Manoj. */
export function openApprovals(tools: ToolCall[]): ToolCall[] {
  return tools.filter((t) => t.state === "approval-requested");
}

/** The `< 2/3 >` picker: which answer shows. A new answer arriving jumps to it. */
export function branchIndex(
  current: number | null,
  count: number,
  previousCount: number,
): number {
  if (count <= 0) return 0;
  if (current === null || count > previousCount) return count - 1;
  return Math.min(Math.max(current, 0), count - 1);
}

export function branchLabel(index: number, count: number): string {
  return `${index + 1}/${count}`;
}

export function formatSeconds(ms: number): string {
  const s = Math.max(1, Math.round(ms / 1000));
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${s % 60}s`;
}

export type DiffLine = {
  kind: "add" | "remove" | "hunk" | "file" | "context";
  text: string;
};

/** A unified diff as lines to colour. Header lines (diff/index/---/+++) are files. */
export function parseDiff(diff: string): DiffLine[] {
  return diff
    .replace(/\n$/, "")
    .split("\n")
    .map((line): DiffLine => {
      if (/^(diff --git|index |--- |\+\+\+ )/.test(line))
        return { kind: "file", text: line };
      if (line.startsWith("@@")) return { kind: "hunk", text: line };
      if (line.startsWith("+")) return { kind: "add", text: line.slice(1) };
      if (line.startsWith("-")) return { kind: "remove", text: line.slice(1) };
      return {
        kind: "context",
        text: line.startsWith(" ") ? line.slice(1) : line,
      };
    });
}

// eslint-disable-next-line no-control-regex
const ANSI = /\u001b\[[0-9;?]*[ -/]*[@-~]|\u001b\][^\u0007]*\u0007/g;

/** Terminal output without colour codes (the plain fallback and screen readers). */
export function stripAnsi(text: string): string {
  return text.replace(ANSI, "");
}

export type ToolOutputView =
  | { kind: "diff"; diff: string }
  | { kind: "terminal"; output: string; exitCode: number | null }
  | { kind: "json" };

/** Which renderer a tool's output gets: `{diff}` or `{terminal, exit_code?}`, else JSON. */
export function outputView(output: unknown): ToolOutputView {
  if (output && typeof output === "object" && !Array.isArray(output)) {
    const o = output as Record<string, unknown>;
    if (typeof o.diff === "string") return { kind: "diff", diff: o.diff };
    if (typeof o.terminal === "string")
      return {
        kind: "terminal",
        output: o.terminal,
        exitCode: typeof o.exit_code === "number" ? o.exit_code : null,
      };
  }
  return { kind: "json" };
}
