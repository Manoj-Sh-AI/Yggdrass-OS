/**
 * Thread state (the conductor's wire shape) -> assistant-ui thread messages.
 *
 * An assistant turn becomes, in order: one `data` part named "run" (the single progress
 * surface: plan, workers, tool cards, approvals), a `reasoning` part, then the `text`.
 * Optimistic user messages come from pendingCommands, so a sent message shows at once.
 */
import type {
  AssistantTransportConnectionMetadata,
  ThreadMessageLike,
} from "@assistant-ui/react";
import type { AssistantMessage, RunState, ThreadState, UserMessage } from "./types";
import { TERMINAL } from "./types";

type Part = Exclude<ThreadMessageLike["content"], string>[number];

export function assistantParts(message: AssistantMessage): Part[] {
  const run = message.run;
  if (!run) return message.text ? [{ type: "text", text: message.text }] : [];
  const parts: Part[] = [{ type: "data", name: "run", data: run } as Part];
  if (run.reasoning) parts.push({ type: "reasoning", text: run.reasoning });
  if (run.text) parts.push({ type: "text", text: run.text });
  return parts;
}

export function runStatus(run: RunState | null | undefined): ThreadMessageLike["status"] {
  if (!run) return { type: "complete", reason: "unknown" };
  if (run.status === "failed") return { type: "incomplete", reason: "error", error: run.error };
  if (run.status === "cancelled") return { type: "incomplete", reason: "cancelled" };
  if (TERMINAL.has(run.status) || run.status === "interrupted")
    return { type: "complete", reason: "unknown" };
  if (run.status === "waiting") return { type: "requires-action", reason: "interrupt" };
  return { type: "running" };
}

function userMessage(message: UserMessage): ThreadMessageLike {
  return { id: message.id, role: "user", content: [{ type: "text", text: message.text }] };
}

export function toMessages(
  state: ThreadState,
  metadata: Pick<AssistantTransportConnectionMetadata, "pendingCommands">,
): ThreadMessageLike[] {
  const messages: ThreadMessageLike[] = state.messages.map((message) =>
    message.role === "user"
      ? userMessage(message)
      : {
          id: message.id,
          role: "assistant",
          content: assistantParts(message),
          status: runStatus(message.run),
        },
  );
  for (const command of metadata.pendingCommands) {
    if (command.type !== "add-message" || command.message.role !== "user") continue;
    const text = command.message.parts
      .map((p) => (p.type === "text" ? p.text : ""))
      .join("\n");
    messages.push({
      id: command.message.id,
      role: "user",
      content: [{ type: "text", text }],
    });
  }
  return messages;
}

/** The run that is still working, if any (for cancel and the composer's state). */
export function liveRun(state: ThreadState): RunState | null {
  for (let i = state.messages.length - 1; i >= 0; i--) {
    const message = state.messages[i];
    if (message.role === "assistant" && message.run)
      return TERMINAL.has(message.run.status) || message.run.status === "interrupted"
        ? null
        : message.run;
  }
  return null;
}
