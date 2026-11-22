/**
 * The conductor's run state, mirrored from app/api/src/yggdress_app/conductor/state.py.
 * tests/chat-contract.test.ts checks these against a fixture the API tests write, so
 * the two sides cannot drift silently.
 */

export const MODES = ["answering", "planning", "executing"] as const;
export type Mode = (typeof MODES)[number];

export const RUN_STATUSES = [
  "running",
  "waiting",
  "completed",
  "failed",
  "cancelled",
  "interrupted",
] as const;
export type RunStatus = (typeof RUN_STATUSES)[number];

export const STEP_STATUSES = ["pending", "in_progress", "completed"] as const;
export type StepStatus = (typeof STEP_STATUSES)[number];

/** Exactly the seven tool-part states shadcn's and assistant-ui's cards expect. */
export const TOOL_STATES = [
  "input-streaming",
  "input-available",
  "approval-requested",
  "approval-responded",
  "output-available",
  "output-error",
  "output-denied",
] as const;
export type ToolState = (typeof TOOL_STATES)[number];

export type Stakes =
  | "low-reversible"
  | "low-irreversible"
  | "high-reversible"
  | "high-irreversible";

export type Step = {
  id: string;
  title: string;
  status: StepStatus;
  depends_on: string[];
  check: string;
  verdict: "passed" | "failed" | null;
  reason: string;
  attempts: number;
  model: string;
  result: string;
};

export type Plan = { title: string; steps: Step[] };

export type ToolCall = {
  id: string;
  name: string;
  state: ToolState;
  step_id: string | null;
  input: Record<string, unknown>;
  output: unknown;
  error: string;
  stakes: Stakes | null;
  decided_by: "rule" | "classifier" | "user" | null;
  intent: string;
  approval: { approved: boolean; reason: string } | null;
};

export type Usage = {
  role: string;
  model: string;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
};

export type RunState = {
  run_id: string;
  conversation_id: string | null;
  status: RunStatus;
  mode: Mode;
  plan: Plan | null;
  tools: ToolCall[];
  reasoning: string;
  text: string;
  model: string;
  usage: Usage[];
  error: string;
  branch_of: string | null;
  user_message: string | null;
};

/** One answer of a request answered more than once ("Try again"), first answer first. */
export type Branch = { id: string; seq?: number; run: RunState | null };

export type UserMessage = { id: string; role: "user"; text: string };
export type AssistantMessage = {
  id: string;
  role: "assistant";
  text: string;
  seq?: number;
  run?: RunState | null;
  branches?: Branch[];
};
export type ThreadState = {
  conversationId: string | null;
  messages: (UserMessage | AssistantMessage)[];
};

export const EMPTY_THREAD: ThreadState = { conversationId: null, messages: [] };

export const TERMINAL: ReadonlySet<RunStatus> = new Set(["completed", "failed", "cancelled"]);

/** Runtime check for state that crosses the network (contract test + defensive load). */
export function isRunState(value: unknown): value is RunState {
  if (!value || typeof value !== "object") return false;
  const run = value as Record<string, unknown>;
  return (
    typeof run.run_id === "string" &&
    RUN_STATUSES.includes(run.status as RunStatus) &&
    MODES.includes(run.mode as Mode) &&
    Array.isArray(run.tools) &&
    (run.tools as ToolCall[]).every((t) => TOOL_STATES.includes(t.state)) &&
    typeof run.text === "string" &&
    typeof run.reasoning === "string" &&
    (run.plan === null ||
      (typeof run.plan === "object" &&
        (run.plan as Plan).steps.every((s) => STEP_STATUSES.includes(s.status))))
  );
}

export function sumCost(run: RunState): number {
  return run.usage.reduce((total, u) => total + u.cost_usd, 0);
}
