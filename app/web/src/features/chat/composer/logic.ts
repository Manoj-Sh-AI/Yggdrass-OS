/**
 * The composer's rules as pure functions (tested in tests/chat-composer.test.ts).
 *
 * Send button, six states [brief B5]. A send control may be inert, but it is never the
 * only signal: either the draft is empty (self-evident) or the reason is on screen.
 *   idle       ready + empty draft   inert, low-contrast glyph, never a "disabled" grey fill
 *   ready      ready + draft         primary fill; Enter submits
 *   blocked    cannot send           inert + an inline line saying why
 *   sending    submitted             Stop, same slot
 *   generating streaming             Stop, aborts the run
 *   error      last run failed       Retry + the error inline
 */
export type SendState = "idle" | "ready" | "blocked" | "sending" | "generating" | "error";

export type SendInputs = {
  empty: boolean;
  blockedReason: string;
  isSending: boolean;
  isRunning: boolean;
  lastError: string;
};

export function sendState(s: SendInputs): SendState {
  if (s.isSending && !s.isRunning) return "sending";
  if (s.isRunning) return "generating";
  if (s.blockedReason) return "blocked";
  if (s.empty && s.lastError) return "error";
  return s.empty ? "idle" : "ready";
}

/**
 * Shrink hysteresis [cited]: grow freely; shrink only when the value is empty. Once text
 * wraps the composer stays expanded until cleared, so it never flickers between one
 * and two rows mid-sentence. Returns the min-height to hold, in px.
 */
export function heldHeight(held: number, measured: number, value: string): number {
  return value === "" ? 0 : Math.max(held, measured);
}

/** Touch keyboards: Enter inserts a newline and the Send button submits [cited]. */
export function submitModeFor(coarsePointer: boolean): "enter" | "none" {
  return coarsePointer ? "none" : "enter";
}

/** Show the Shift+Enter hint on the first-run empty composer, or the first time a draft
 * wraps; then remember it was seen [proposal]. */
export function showNewlineHint(seen: boolean, coarsePointer: boolean, wrapped: boolean,
                                firstRun: boolean): boolean {
  return !seen && !coarsePointer && (firstRun || wrapped);
}

export const ACCEPTED_ATTACHMENTS = "image/png,image/jpeg,image/webp,image/gif,text/*,.md,.csv,.json";
