"use client";
/**
 * One composer, one DOM position (B3). Whether it sits centered (empty thread) or at the
 * bottom is a property of its container (thread.tsx), so focus, draft and attachments
 * survive the first send with no remount.
 */
import {
  AttachmentPrimitive,
  ComposerPrimitive,
  useAui,
  useAuiState,
} from "@assistant-ui/react";
import { ArrowUp, Plus, RotateCcw, Square, X } from "lucide-react";
import { useEffect, useState } from "react";
import { Popover, PopoverContent, PopoverItem, PopoverTrigger } from "@/components/primitives";
import { ModelPicker } from "./model-picker";
import {
  ACCEPTED_ATTACHMENTS,
  heldHeight,
  type SendState,
  sendState,
  showNewlineHint,
  submitModeFor,
} from "./logic";

const HINT_KEY = "yggdras.chat.newline-hint-seen";
// text-base (16px) at line-height 1.4, plus py-1.5 (6px top and bottom).
const LINE_PX = 22.4;
const PADDING_PX = 12;

/** The held height as a minimum row count (the autosizing textarea owns its height). */
export function rowsFor(heightPx: number): number {
  return heightPx <= 0 ? 1 : Math.max(1, Math.round((heightPx - PADDING_PX) / LINE_PX));
}

function useCoarsePointer(): boolean {
  const [coarse, setCoarse] = useState(false);
  useEffect(() => {
    const query = window.matchMedia("(pointer: coarse)");
    setCoarse(query.matches);
    const change = () => setCoarse(query.matches);
    query.addEventListener("change", change);
    return () => query.removeEventListener("change", change);
  }, []);
  return coarse;
}

type Props = {
  blockedReason: string;
  lastError: string;
  lastRequest: string;
  model: string;
  onModel: (model: string) => void;
  placeholder: string;
};

export function Composer({ blockedReason, lastError, lastRequest, model, onModel, placeholder }: Props) {
  const aui = useAui();
  const text = useAuiState((s) => s.composer.text);
  const empty = useAuiState((s) => s.composer.isEmpty);
  const isRunning = useAuiState((s) => s.thread.isRunning);
  const streaming = useAuiState((s) => {
    const last = s.thread.messages.at(-1);
    return last?.role === "assistant" && last.status?.type === "running" && last.content.length > 0;
  });
  const firstRun = useAuiState((s) => s.thread.messages.length === 0);
  const coarse = useCoarsePointer();
  const [held, setHeld] = useState(0);
  const [measured, setMeasured] = useState(0);
  const [hintSeen, setHintSeen] = useState(true);
  useEffect(() => {
    try {
      setHintSeen(window.localStorage.getItem(HINT_KEY) === "1");
    } catch {
      setHintSeen(false);
    }
  }, []);
  useEffect(() => setHeld((h) => heldHeight(h, measured, text)), [measured, text]);
  const wrapped = held > 0 && measured > 30;
  const hint = showNewlineHint(hintSeen, coarse, wrapped, firstRun);
  useEffect(() => {
    if (!hint || !wrapped) return;
    try {
      window.localStorage.setItem(HINT_KEY, "1");
    } catch {
      // Storage unavailable: the hint simply shows again next time.
    }
  }, [hint, wrapped]);

  const state: SendState = sendState({
    empty,
    blockedReason,
    isSending: isRunning && !streaming,
    isRunning: isRunning && streaming,
    lastError,
  });
  const retry = () => {
    aui.composer().setText(lastRequest);
    aui.composer().send();
  };

  return (
    <ComposerPrimitive.AttachmentDropzone className="group/dropzone">
      <ComposerPrimitive.Root
        className="flex flex-col gap-1 rounded-xl border-t-hairline border-hairline-strong bg-surface-2 p-2 shadow-sm group-data-[dragging=true]/dropzone:ring-2 group-data-[dragging=true]/dropzone:ring-ring"
        style={{ boxShadow: "var(--panel-highlight)" }}
      >
        <div className="flex flex-wrap gap-2 empty:hidden">
          <ComposerPrimitive.Attachments>
            {({ attachment }) => (
              <AttachmentPrimitive.Root className="flex items-center gap-2 rounded-md bg-surface-3 py-1 pr-1 pl-2 text-xs text-text-2">
                {attachment.type === "image" && attachment.file ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={URL.createObjectURL(attachment.file)}
                    alt=""
                    className="size-8 rounded-sm object-cover"
                  />
                ) : null}
                <AttachmentPrimitive.Name />
                <AttachmentPrimitive.Remove
                  aria-label={`Remove ${attachment.name}`}
                  className="grid size-5 place-items-center rounded-sm text-text-3 hover:bg-surface-2"
                >
                  <X className="size-3" />
                </AttachmentPrimitive.Remove>
              </AttachmentPrimitive.Root>
            )}
          </ComposerPrimitive.Attachments>
        </div>
        <ComposerPrimitive.Input
          rows={1}
          autoFocus={false}
          placeholder={placeholder}
          submitMode={submitModeFor(coarse)}
          cancelOnEscape
          addAttachmentOnPaste
          onHeightChange={(height) => setMeasured(height)}
          minRows={rowsFor(held)}
          className="max-h-[40vh] w-full resize-none overflow-y-auto bg-transparent px-2 py-1.5 text-base text-text-1 outline-none placeholder:text-text-3"
        />
        <div className="flex items-center gap-1">
          <Popover>
            <PopoverTrigger asChild>
              <button
                type="button"
                aria-label="Add"
                className="grid size-8 place-items-center rounded-md text-text-2 hover:bg-surface-3"
              >
                <Plus className="size-4" />
              </button>
            </PopoverTrigger>
            <PopoverContent>
              <ComposerPrimitive.AddAttachment asChild multiple>
                <PopoverItem>Add images or text files</PopoverItem>
              </ComposerPrimitive.AddAttachment>
              <p className="px-2 py-1 text-xs text-text-2">
                PDFs are not supported yet. Accepted: {ACCEPTED_ATTACHMENTS.split(",").length} kinds.
              </p>
            </PopoverContent>
          </Popover>
          <ModelPicker model={model} onModel={onModel} />
          <span className="ml-auto" />
          {hint ? <span className="text-xs text-text-2">Shift + Enter for a new line</span> : null}
          <SendControl state={state} onRetry={retry} />
        </div>
        {state === "blocked" ? (
          <p role="status" className="px-2 text-xs text-warning">{blockedReason}</p>
        ) : null}
        {state === "error" ? (
          <p role="alert" className="px-2 text-xs text-danger">{lastError}</p>
        ) : null}
      </ComposerPrimitive.Root>
    </ComposerPrimitive.AttachmentDropzone>
  );
}

const SLOT = "grid size-8 place-items-center rounded-full";

export function SendControl({ state, onRetry }: { state: SendState; onRetry: () => void }) {
  if (state === "sending" || state === "generating")
    return (
      <ComposerPrimitive.Cancel
        aria-label="Stop"
        data-state={state}
        className={`${SLOT} bg-primary text-primary-foreground`}
      >
        <Square className="size-3 fill-current" />
      </ComposerPrimitive.Cancel>
    );
  if (state === "error")
    return (
      <button
        type="button"
        aria-label="Retry"
        data-state={state}
        onClick={onRetry}
        className={`${SLOT} bg-primary text-primary-foreground`}
      >
        <RotateCcw className="size-4" />
      </button>
    );
  // idle and blocked are inert but never a grey "disabled" fill: a low-contrast glyph on
  // the overlay surface; blocked also shows its reason as a line of copy.
  const inert = state !== "ready";
  return (
    <ComposerPrimitive.Send
      aria-label="Send"
      data-state={state}
      className={
        inert
          ? `${SLOT} bg-surface-3 text-text-3`
          : `${SLOT} bg-primary text-primary-foreground hover:opacity-90`
      }
    >
      <ArrowUp className="size-4" />
    </ComposerPrimitive.Send>
  );
}
