"use client";
/**
 * The chat column (B3): one grid, `1fr auto`. Empty: the 1fr row holds the greeting and
 * three starter pills, centered. Active: the 1fr row is the scrolling transcript. The
 * composer never moves in the DOM, so focus, draft and attachments survive the first send.
 * When the composer grows its top edge rises; the transcript's scroll offset is
 * compensated in the same frame so the reader's place is kept.
 */
import { MessagePrimitive, ThreadPrimitive, useAui, useAuiState } from "@assistant-ui/react";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { Composer } from "./composer/composer";
import { AnswerText, BranchesPart, ReasoningBlock, RunPart, TryAgain } from "./parts/parts";

/** Jobs Yggdras can actually do from the chat (it reads calendar, tasks and notes). */
export const STARTERS = [
  "What does my week look like?",
  "Plan Saturday around my open tasks",
  "What do my notes say about my goals?",
] as const;

function useOnline(): boolean {
  const [online, setOnline] = useState(true);
  useEffect(() => {
    const update = () => setOnline(navigator.onLine);
    update();
    window.addEventListener("online", update);
    window.addEventListener("offline", update);
    return () => {
      window.removeEventListener("online", update);
      window.removeEventListener("offline", update);
    };
  }, []);
  return online;
}

function UserBubble() {
  return (
    <MessagePrimitive.Root className="ml-auto max-w-[80%] rounded-xl bg-surface-2 px-3 py-2 text-sm text-text-1">
      <MessagePrimitive.Parts />
    </MessagePrimitive.Root>
  );
}

function AssistantTurn() {
  // Only a conductor run can be answered again (its id is the run id); plain history
  // messages from the old chat or the phone have no run.
  const retry = useAuiState((s) => {
    const m = s.message;
    const ran = m.content.some((p) => p.type === "data");
    return m.isLast && !s.thread.isRunning && m.status?.type !== "running" && ran ? m.id : "";
  });
  return (
    <MessagePrimitive.Root className="flex flex-col gap-2">
      <MessagePrimitive.Parts
        components={{
          Text: AnswerText,
          Reasoning: ReasoningBlock,
          data: { by_name: { run: RunPart, branches: BranchesPart } },
        }}
      />
      {retry ? <TryAgain runId={retry} /> : null}
    </MessagePrimitive.Root>
  );
}

type Props = { model: string; onModel: (id: string) => void };

export function Thread({ model, onModel }: Props) {
  const aui = useAui();
  const empty = useAuiState((s) => s.thread.messages.length === 0);
  const lastRequest = useAuiState((s) => {
    const user = [...s.thread.messages].reverse().find((m) => m.role === "user");
    const part = user?.content.find((p) => p.type === "text");
    return part && part.type === "text" ? part.text : "";
  });
  const lastError = useAuiState((s) => {
    const last = s.thread.messages.at(-1);
    return last?.role === "assistant" && last.status?.type === "incomplete" && last.status.reason === "error"
      ? String(last.status.error ?? "The answer failed.")
      : "";
  });
  const online = useOnline();
  const viewport = useRef<HTMLDivElement>(null);
  const composer = useRef<HTMLDivElement>(null);
  const lastHeight = useRef(0);

  useLayoutEffect(() => {
    const box = composer.current;
    if (!box) return;
    const observer = new ResizeObserver(() => {
      const height = box.offsetHeight;
      const delta = height - lastHeight.current;
      lastHeight.current = height;
      if (delta > 0 && viewport.current) viewport.current.scrollTop += delta;
    });
    observer.observe(box);
    return () => observer.disconnect();
  }, []);

  const start = (text: string) => {
    aui.composer().setText(text);
    aui.composer().send();
  };

  return (
    <ThreadPrimitive.Root className="grid h-full min-h-0 grid-rows-[1fr_auto] gap-2">
      <ThreadPrimitive.Viewport
        ref={viewport}
        className={`min-h-0 overflow-y-auto px-4 ${empty ? "grid place-items-center" : ""}`}
      >
        {empty ? (
          <div className="flex flex-col items-center gap-4 text-center">
            <p className="text-lg text-text-1">What should we work on?</p>
            <div className="flex flex-wrap justify-center gap-2">
              {STARTERS.map((starter) => (
                <button
                  key={starter}
                  type="button"
                  onClick={() => start(starter)}
                  className="rounded-full bg-surface-2 px-3 py-1.5 text-sm text-text-2 hover:bg-surface-3 hover:text-text-1"
                >
                  {starter}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="mx-auto flex w-full max-w-3xl flex-col gap-4 py-4">
            <ThreadPrimitive.Messages components={{ UserMessage: UserBubble, AssistantMessage: AssistantTurn }} />
          </div>
        )}
      </ThreadPrimitive.Viewport>
      <div ref={composer} className="mx-auto w-full max-w-3xl px-4 pb-4">
        <Composer
          blockedReason={online ? "" : "You're offline. Your draft is kept."}
          lastError={lastError}
          lastRequest={lastRequest}
          model={model}
          onModel={onModel}
          placeholder={empty ? "Ask Yggdras, or give it a job" : "Reply, or give it the next job"}
        />
      </div>
    </ThreadPrimitive.Root>
  );
}
