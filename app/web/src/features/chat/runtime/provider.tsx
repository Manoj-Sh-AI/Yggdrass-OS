"use client";
/**
 * The chat's runtime: assistant-ui's Assistant Transport against the conductor
 * (/v1/assistant through the proxy). One provider per conversation; it starts from the
 * server's thread state and resumes a run that is still going (closed tab, reload).
 */
import {
  AssistantRuntimeProvider,
  CompositeAttachmentAdapter,
  SimpleImageAttachmentAdapter,
  SimpleTextAttachmentAdapter,
  type ThreadMessageLike,
  unstable_createMessageConverter as createMessageConverter,
  useAssistantTransportRuntime,
} from "@assistant-ui/react";
import { type ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { csrfToken } from "@/lib/api";
import { ASSISTANT_API, cancelRun } from "./commands";
import { liveRun, toMessages } from "./converter";
import { EMPTY_THREAD, type ThreadState } from "./types";

const converter = createMessageConverter((message: ThreadMessageLike) => message);

type Props = {
  conversationId: string | null;
  model: string;
  onConversation?: (id: string) => void;
  children: ReactNode;
};

/** `conversationId` is read once, at mount: the page remounts to switch conversations. */
export function ConductorProvider({ conversationId: initialId, ...rest }: Props) {
  const [conversationId] = useState(initialId);
  const [initial, setInitial] = useState<ThreadState | null>(
    conversationId ? null : EMPTY_THREAD,
  );
  const [error, setError] = useState("");
  useEffect(() => {
    if (!conversationId) return;
    let live = true;
    fetch(`${ASSISTANT_API}/threads/${conversationId}`, { credentials: "same-origin" })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((thread: ThreadState) => live && setInitial(thread))
      .catch(() => live && setError("This conversation could not be loaded."));
    return () => {
      live = false;
    };
  }, [conversationId]);
  if (error) return <p className="text-sm text-danger">{error}</p>;
  if (!initial) return null;
  return <Runtime initial={initial} {...rest} />;
}

function Runtime({
  initial,
  model,
  onConversation,
  children,
}: Omit<Props, "conversationId"> & { initial: ThreadState }) {
  const latest = useRef<ThreadState>(initial);
  const attachments = useMemo(
    () =>
      new CompositeAttachmentAdapter([
        new SimpleImageAttachmentAdapter(),
        new SimpleTextAttachmentAdapter(),
      ]),
    [],
  );
  const conversation = initial.conversationId;
  const runtime = useAssistantTransportRuntime<ThreadState>({
    initialState: initial,
    api: ASSISTANT_API,
    protocol: "assistant-transport",
    resumeApi: `${ASSISTANT_API}/resume`,
    resumeStateApi: conversation
      ? `${ASSISTANT_API}/resume-state?conversation=${conversation}`
      : undefined,
    canResume: Boolean(conversation && liveRun(initial)),
    headers: async () => ({ "X-Yggdress-CSRF": await csrfToken() }),
    body: () =>
      Promise.resolve({ conversationId: latest.current.conversationId, model }),
    converter: (state, metadata) => {
      latest.current = state;
      if (state.conversationId && state.conversationId !== conversation)
        onConversation?.(state.conversationId);
      return {
        messages: converter.toThreadMessages(toMessages(state, metadata)),
        isRunning: metadata.isSending || liveRun(state)?.status === "running",
      };
    },
    onCancel: () => {
      const run = liveRun(latest.current);
      if (run) void cancelRun(run.run_id);
    },
    adapters: { attachments },
  });
  return <AssistantRuntimeProvider runtime={runtime}>{children}</AssistantRuntimeProvider>;
}
