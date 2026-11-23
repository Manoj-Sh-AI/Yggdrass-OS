"use client";
/**
 * The chat's components in every state they can be in, with invented content only (the
 * repo is public). Used for the screenshot of each component; not a product page.
 */
import { EyeOff } from "lucide-react";
import { ListGroupLabel, ListRow } from "@/components/primitives";
import { MiniMonth } from "../calendar/mini-month";
import { NowLine } from "../calendar/now-line";
import { VoiceOrb } from "../voice/orb";
import { Composer } from "./composer/composer";
import { DiffCard, TerminalCard } from "./parts/cards";
import { ApprovalCard, Branches, PlanCard, ToolCard } from "./parts/parts";
import { ConductorProvider } from "./runtime/provider";
import { type RunState, TOOL_STATES, type ToolCall } from "./runtime/types";

const run = (over: Partial<RunState>): RunState => ({
  run_id: "00000000-0000-4000-8000-000000000001",
  conversation_id: null,
  status: "completed",
  mode: "answering",
  plan: null,
  tools: [],
  reasoning: "",
  text: "",
  model: "claude-sonnet-5-5",
  usage: [],
  error: "",
  branch_of: null,
  user_message: null,
  ...over,
});
const tool = (
  state: ToolCall["state"],
  over: Partial<ToolCall> = {},
): ToolCall => ({
  id: `t-${state}`,
  name: "read_calendar",
  state,
  step_id: null,
  input: { day: "2026-11-28" },
  output:
    state === "output-available"
      ? { events: ["Invented picnic, 12:00"] }
      : null,
  error:
    state === "output-error" ? "The invented calendar did not answer." : "",
  stakes: "low-reversible",
  decided_by: "rule",
  intent: "",
  approval: null,
  ...over,
});
const step = (
  id: string,
  title: string,
  status: "pending" | "in_progress" | "completed",
  verdict: "passed" | "failed" | null = null,
  attempts = 1,
  reason = "",
) => ({
  id,
  title,
  status,
  depends_on: [],
  check: "the result names a day",
  verdict,
  reason,
  attempts,
  model: "claude-haiku-5-5",
  result: "",
});

const PLANNED = run({
  status: "running",
  mode: "executing",
  plan: {
    title: "Plan Saturday around open tasks",
    steps: [
      step("s1", "Read Saturday's calendar", "completed", "passed"),
      step("s2", "List open tasks due this week", "in_progress"),
      step(
        "s3",
        "Check the invented weather note",
        "in_progress",
        "failed",
        1,
        "No forecast found",
      ),
      step(
        "s4",
        "Find a free slot for the picnic",
        "completed",
        "failed",
        3,
        "No slot over 2 hours",
      ),
      step("s5", "Draft the day", "pending"),
    ],
  },
  tools: [
    tool("output-available", { step_id: "s1" }),
    tool("input-available", { id: "t2", name: "list_tasks", step_id: "s2" }),
  ],
});

const DIFF = `--- a/invented-garden.md
+++ b/invented-garden.md
@@ -1,4 +1,4 @@
 # Invented garden
-Water the tomatoes on Monday
+Water the tomatoes on Tuesday
 Buy seeds
+Ask the neighbour about compost
`;

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section
      aria-label={title}
      data-gallery={title}
      className="flex min-w-0 flex-col gap-2 rounded-lg p-4"
    >
      <h2 className="text-sm font-semibold text-text-2">{title}</h2>
      {children}
    </section>
  );
}

export function ComponentGallery() {
  return (
    <ConductorProvider conversationId={null} model="claude-sonnet-5-5">
      <div className="mx-auto grid w-full max-w-3xl grid-cols-1 gap-4 py-6">
        <Section title="Plan and task cards">
          <PlanCard run={PLANNED} />
        </Section>
        <Section title="Tool cards (seven states)">
          {TOOL_STATES.map((s) => (
            <ToolCard key={s} tool={tool(s)} />
          ))}
        </Section>
        <Section title="Approve or reject">
          <ApprovalCard
            runId={PLANNED.run_id}
            tool={tool("approval-requested", {
              name: "create_event",
              stakes: "high-irreversible",
              intent:
                "Add 'Invented picnic' to Saturday 12:00 and invite two people.",
            })}
          />
        </Section>
        <Section title="Message branching">
          <Branches
            branches={[
              {
                id: "b1",
                run: run({
                  text: "Saturday: picnic at noon, then the invented market.",
                }),
              },
              {
                id: "b2",
                run: run({
                  text: "Saturday: market in the morning, picnic at 2 pm.",
                }),
              },
              {
                id: "b3",
                run: run({
                  reasoning: "Weighing the two plans against the weather note.",
                  text: "Saturday: **picnic at noon**; the market moves to Sunday.",
                }),
              },
            ]}
          />
        </Section>
        <Section title="Streaming answer with reasoning">
          <Branches
            branches={[
              {
                id: "x",
                run: run({
                  status: "running",
                  reasoning: "Reading the invented notes…",
                  text: "",
                }),
              },
              {
                id: "y",
                run: run({
                  status: "running",
                  text: "Here is the plan so far: lunch at",
                }),
              },
            ]}
          />
        </Section>
        <Section title="Diff card">
          <DiffCard diff={DIFF} />
        </Section>
        <Section title="Terminal card">
          <TerminalCard
            output={
              "$ uv run pytest -q tests/test_invented.py\n\u001b[32m12 passed\u001b[0m, \u001b[31m1 failed\u001b[0m in 0.42s\n"
            }
            exitCode={1}
          />
        </Section>
        <Section title="Voice orb (four states)">
          <div className="flex flex-wrap gap-6">
            <VoiceOrb state="idle" />
            <VoiceOrb state="listening" />
            <VoiceOrb state="thinking" />
            <VoiceOrb state="speaking" />
          </div>
        </Section>
        <Section title="Notes list rows">
          <div className="w-64">
            <ListGroupLabel count={4}>Health</ListGroupLabel>
            <ListRow title="Invented running plan for the spring half marathon" />
            <ListRow title="Invented physio exercises" active />
            <ListRow
              title="Invented diary"
              status={
                <span role="img" aria-label="Sensitive note">
                  <EyeOff className="size-3.5" />
                </span>
              }
            />
            <ListRow title="Invented sleep notes" depth={1} />
          </div>
        </Section>
        <Section title="Mini month and now line">
          <div className="flex flex-wrap items-start gap-6">
            <div className="w-56">
              <MiniMonth
                day="2026-11-18"
                today="2026-11-22"
                busy={new Set(["2026-11-17", "2026-11-20", "2026-11-25"])}
                onPick={() => {}}
              />
            </div>
            <div className="relative h-32 w-40 border-l-hairline">
              <NowLine minute={30} hourPx={120} />
            </div>
          </div>
        </Section>
        <Section title="Composer">
          <Composer
            blockedReason=""
            lastError=""
            lastRequest=""
            model="claude-sonnet-5-5"
            onModel={() => {}}
            placeholder="Ask Yggdras, or give it a job"
          />
        </Section>
      </div>
    </ConductorProvider>
  );
}
