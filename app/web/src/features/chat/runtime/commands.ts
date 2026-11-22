/** The conductor's own commands, alongside assistant-ui's add-message. */
import { csrfToken } from "@/lib/api";

export type AnswerApprovalCommand = {
  type: "answer-approval";
  runId: string;
  toolCallId: string;
  approved: boolean;
  reason?: string;
};
export type CancelRunCommand = { type: "cancel-run"; runId: string };
/** "Try again": another answer to the same request, kept as a sibling branch. */
export type RegenerateCommand = { type: "regenerate"; runId: string };

declare module "@assistant-ui/react" {
  namespace Assistant {
    interface Commands {
      answerApproval: AnswerApprovalCommand;
      cancelRun: CancelRunCommand;
      regenerate: RegenerateCommand;
    }
  }
}

export const ASSISTANT_API = "/api/backend/assistant";

/** Stop a run on the server. Aborting the stream alone would leave it running. */
export async function cancelRun(runId: string): Promise<void> {
  await fetch(ASSISTANT_API, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", "X-Yggdress-CSRF": await csrfToken() },
    body: JSON.stringify({ commands: [{ type: "cancel-run", runId }] }),
  });
}
