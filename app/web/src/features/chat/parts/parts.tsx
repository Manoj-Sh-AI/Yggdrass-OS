"use client";
/**
 * How an assistant turn renders. One progress surface per turn (B10): the run card shows
 * the Plan when there is one, otherwise the tool list; never both. Successes collapse,
 * errors and approvals expand. Answers render through Streamdown (B8).
 */
import type {
  DataMessagePartProps,
  ReasoningMessagePartProps,
  TextMessagePartProps,
} from "@assistant-ui/react";
import {
  useAssistantTransportSendCommand,
  useAuiState,
} from "@assistant-ui/react";
import { code } from "@streamdown/code";
import { math } from "@streamdown/math";
import { mermaid } from "@streamdown/mermaid";
import {
  AlertTriangle,
  Check,
  ChevronLeft,
  ChevronRight,
  Circle,
  CircleDashed,
  Loader2,
  RotateCcw,
  ShieldQuestion,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Streamdown } from "streamdown";
import { Badge, Button } from "@/components/primitives";
import type { Branch, RunState, ToolCall } from "../runtime/types";
import { DiffCard, TerminalCard } from "./cards";
import {
  branchIndex,
  branchLabel,
  formatSeconds,
  openApprovals,
  outputView,
  reasoningIsStreaming,
  stepView,
  TOOL_BADGE,
  toolOpensByDefault,
} from "./logic";

const PLUGINS = { code, math, mermaid };

export function AnswerText({ text, status }: TextMessagePartProps) {
  const streaming = status.type === "running";
  return (
    <Streamdown
      className="text-sm leading-relaxed text-text-1"
      plugins={PLUGINS}
      isAnimating={streaming}
      caret={streaming ? "block" : undefined}
    >
      {text}
    </Streamdown>
  );
}

export function ReasoningBlock({ text }: ReasoningMessagePartProps) {
  const streaming = useAuiState((s) =>
    reasoningIsStreaming({
      isLastMessage: s.message.isLast,
      threadRunning: s.thread.isRunning,
      lastPartIsReasoning: s.message.parts.at(-1)?.type === "reasoning",
    }),
  );
  // The app owns the timer; nothing in the library ticks [cited].
  const started = useRef<number | null>(null);
  const [duration, setDuration] = useState<string | null>(null);
  const [open, setOpen] = useState(streaming);
  useEffect(() => {
    if (streaming) {
      started.current ??= Date.now();
      setOpen(true);
    } else if (started.current !== null) {
      setDuration(formatSeconds(Date.now() - started.current));
      started.current = null;
      setOpen(false); // auto-closes when the reasoning ends
    }
  }, [streaming]);
  return (
    <details open={open} className="group text-xs text-text-2">
      <summary
        onClick={(e) => {
          e.preventDefault();
          setOpen((o) => !o);
        }}
        className="flex cursor-pointer list-none items-center gap-1 py-1"
      >
        <ChevronRight className="size-3.5 transition-transform motion-short group-open:rotate-90" />
        {streaming
          ? "Thinking…"
          : duration
            ? `Thought for ${duration}`
            : "Reasoning"}
      </summary>
      <p className="whitespace-pre-wrap border-l-hairline border-hairline-strong pl-3 text-text-2">
        {text}
      </p>
    </details>
  );
}

export function RunPart({ data }: DataMessagePartProps<RunState>) {
  return <RunView run={data} />;
}

/**
 * A request answered more than once ("Try again"): a `< 2/3 >` picker and the chosen
 * answer. The newest shows by default, and a new one arriving is shown as it streams.
 */
export function BranchesPart({
  data,
}: DataMessagePartProps<{ branches: Branch[] }>) {
  return <Branches branches={data.branches} />;
}

export function Branches({ branches }: { branches: Branch[] }) {
  const count = branches.length;
  const seen = useRef(count);
  const [index, setIndex] = useState(count - 1);
  useEffect(() => {
    setIndex((current) => branchIndex(current, count, seen.current));
    seen.current = count;
  }, [count]);
  const run = branches[Math.min(index, count - 1)]?.run;
  const streaming = run?.status === "running";
  return (
    <div className="flex flex-col gap-2">
      <nav
        aria-label="Answers"
        className="flex items-center gap-1 text-xs text-text-2"
      >
        <Button
          size="icon"
          variant="ghost"
          aria-label="Previous answer"
          disabled={index <= 0}
          onClick={() => setIndex((i) => Math.max(0, i - 1))}
          className="size-6"
        >
          <ChevronLeft className="size-3.5" />
        </Button>
        <span aria-live="polite">{branchLabel(index, count)}</span>
        <Button
          size="icon"
          variant="ghost"
          aria-label="Next answer"
          disabled={index >= count - 1}
          onClick={() => setIndex((i) => Math.min(count - 1, i + 1))}
          className="size-6"
        >
          <ChevronRight className="size-3.5" />
        </Button>
      </nav>
      {run ? (
        <>
          <RunView run={run} />
          {run.reasoning ? (
            <details
              className="text-xs text-text-2"
              open={streaming && !run.text}
            >
              <summary className="cursor-pointer py-1">
                {streaming && !run.text ? "Thinking…" : "Reasoning"}
              </summary>
              <p className="whitespace-pre-wrap border-l-hairline border-hairline-strong pl-3">
                {run.reasoning}
              </p>
            </details>
          ) : null}
          {run.text ? (
            <Streamdown
              className="text-sm leading-relaxed text-text-1"
              plugins={PLUGINS}
              isAnimating={streaming}
              caret={streaming ? "block" : undefined}
            >
              {run.text}
            </Streamdown>
          ) : null}
        </>
      ) : null}
    </div>
  );
}

/** "Try again" under the last finished answer: a sibling answer, never a lost one. */
export function TryAgain({ runId }: { runId: string }) {
  const send = useAssistantTransportSendCommand();
  return (
    <Button
      size="sm"
      variant="ghost"
      className="self-start text-text-2"
      onClick={() => send({ type: "regenerate", runId })}
    >
      <RotateCcw className="size-3.5" /> Try again
    </Button>
  );
}

function RunView({ run }: { run: RunState }) {
  const approvals = openApprovals(run.tools);
  return (
    <div className="flex flex-col gap-2">
      {run.plan ? (
        <PlanCard run={run} />
      ) : (
        run.tools
          .filter((t: ToolCall) => t.state !== "approval-requested")
          .map((t: ToolCall) => <ToolCard key={t.id} tool={t} />)
      )}
      {approvals.map((t) => (
        <ApprovalCard key={t.id} runId={run.run_id} tool={t} />
      ))}
      <RunNotice run={run} />
    </div>
  );
}

function RunNotice({ run }: { run: RunState }) {
  if (run.status === "interrupted")
    return (
      <p className="flex items-center gap-1 text-xs text-warning">
        <AlertTriangle className="size-3.5" /> Interrupted: the server stopped
        while this was running. Send the request again to retry.
      </p>
    );
  if (run.status === "failed" && run.error)
    return (
      <p role="alert" className="flex items-center gap-1 text-xs text-danger">
        <AlertTriangle className="size-3.5" /> {run.error}
      </p>
    );
  if (run.status === "cancelled")
    return <p className="text-xs text-text-2">Stopped.</p>;
  return null;
}

const STEP_ICON = {
  pending: <Circle className="size-3.5 text-text-3" />,
  active: <Loader2 className="size-3.5 animate-spin text-text-1" />,
  done: <Check className="size-3.5 text-success" />,
  failed: <AlertTriangle className="size-3.5 text-danger" />,
  retrying: <RotateCcw className="size-3.5 text-warning" />,
};

export function PlanCard({ run }: { run: RunState }) {
  const plan = run.plan!;
  const done = plan.steps.filter((s) => s.status === "completed").length;
  const planning = run.mode === "planning";
  return (
    <section aria-label="Plan" className="rounded-lg bg-surface-1 p-3">
      <header className="mb-2 flex items-center gap-2">
        <CircleDashed className="size-4 text-text-2" />
        <h3 className="text-sm font-semibold text-text-1">{plan.title}</h3>
        <span className="ml-auto text-xs text-text-2">
          {planning ? "Planning…" : `${done} of ${plan.steps.length}`}
        </span>
      </header>
      <ol className="flex flex-col gap-1">
        {plan.steps.map((step) => {
          const view = stepView(step);
          const tools = run.tools.filter(
            (t) => t.step_id === step.id && t.state !== "approval-requested",
          );
          return (
            <li key={step.id} className="flex flex-col gap-1">
              <div
                className="flex items-center gap-2 text-sm"
                title={step.check}
              >
                {STEP_ICON[view.tone]}
                <span
                  className={
                    view.tone === "done" ? "text-text-2" : "text-text-1"
                  }
                >
                  {view.label}
                </span>
              </div>
              {view.detail ? (
                <p
                  className={`pl-6 text-xs ${view.tone === "failed" ? "text-danger" : "text-warning"}`}
                >
                  {view.detail}
                </p>
              ) : null}
              {tools.length ? (
                <div className="flex flex-col gap-1 pl-6">
                  {tools.map((t) => (
                    <ToolCard key={t.id} tool={t} />
                  ))}
                </div>
              ) : null}
            </li>
          );
        })}
      </ol>
    </section>
  );
}

const BADGE_TONE: Record<string, string> = {
  "output-error": "bg-danger-surface text-danger",
  "output-denied": "bg-danger-surface text-danger",
  "approval-requested": "bg-warning-surface text-warning",
  "output-available": "bg-success-surface text-success",
};

export function ToolCard({ tool }: { tool: ToolCall }) {
  const [open, setOpen] = useState(toolOpensByDefault(tool.state));
  useEffect(() => {
    if (toolOpensByDefault(tool.state)) setOpen(true);
  }, [tool.state]);
  return (
    <div className="rounded-md bg-surface-2 text-xs">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        className="flex h-7 w-full items-center gap-2 px-2 text-left text-text-1"
      >
        <ChevronRight
          className={`size-3.5 transition-transform motion-short ${open ? "rotate-90" : ""}`}
        />
        <span className="font-mono">{tool.name}</span>
        <Badge
          className={`ml-auto ${BADGE_TONE[tool.state] ?? "bg-surface-3 text-text-2"}`}
        >
          {TOOL_BADGE[tool.state]}
        </Badge>
      </button>
      {open ? (
        <div className="flex flex-col gap-1 px-2 pb-2">
          {tool.intent ? <p className="text-text-2">{tool.intent}</p> : null}
          <pre className="overflow-x-auto rounded-sm bg-surface-sunken p-2 text-text-2">
            {JSON.stringify(tool.input, null, 2)}
          </pre>
          {tool.error ? <p className="text-danger">{tool.error}</p> : null}
          {tool.state === "output-available" && tool.output !== null ? (
            <ToolOutput output={tool.output} />
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function ToolOutput({ output }: { output: unknown }) {
  const view = outputView(output);
  if (view.kind === "diff") return <DiffCard diff={view.diff} />;
  if (view.kind === "terminal")
    return <TerminalCard output={view.output} exitCode={view.exitCode} />;
  return (
    <pre className="max-h-48 overflow-auto rounded-sm bg-surface-sunken p-2 text-text-2">
      {JSON.stringify(output, null, 2)}
    </pre>
  );
}

/** Intent Preview + explicit permission (high stakes) or confirmation (low stakes). */
export function ApprovalCard({
  runId,
  tool,
}: {
  runId: string;
  tool: ToolCall;
}) {
  const send = useAssistantTransportSendCommand();
  const [sent, setSent] = useState(false);
  const answer = (approved: boolean) => {
    setSent(true);
    send({ type: "answer-approval", runId, toolCallId: tool.id, approved });
  };
  const irreversible = tool.stakes?.endsWith("irreversible");
  return (
    <section
      aria-label="Approval needed"
      className="flex flex-col gap-2 rounded-lg border-hairline border-warning bg-warning-surface p-3"
    >
      <header className="flex items-center gap-2 text-sm font-semibold text-text-1">
        <ShieldQuestion className="size-4 text-warning" /> Approve this action?
      </header>
      <p className="text-sm text-text-1">{tool.intent}</p>
      {irreversible ? (
        <p className="text-xs text-text-2">This cannot be undone.</p>
      ) : null}
      <div className="flex gap-2">
        <Button size="sm" disabled={sent} onClick={() => answer(true)}>
          Approve
        </Button>
        <Button
          size="sm"
          variant="secondary"
          disabled={sent}
          onClick={() => answer(false)}
        >
          Decline
        </Button>
      </div>
    </section>
  );
}
