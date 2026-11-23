"use client";
/**
 * The side chat (Phase E): non-modal and always mounted in the workspace shell, so it
 * survives navigation and keeps its transcript and draft when closed (it is translated
 * out, inert and aria-hidden, not unmounted). Not a Radix Sheet: no overlay, no focus
 * trap, no scroll lock; the page stays usable, which is the point ("move this to Friday").
 *
 * - Mod+J toggles. Esc closes only when focus is inside. Clicking the page never closes.
 * - Width 360-480px, resizable (drag or arrow keys on the edge), persisted with the
 *   open state. Pushes the page at >= 1280px (xl), overlays below.
 * - The page context goes with each message as a dismissible chip; dismissing it is the
 *   only way to say "don't look at my page", and lasts until the page changes.
 */
import { Eye, MessagesSquare, PanelRightClose, X } from "lucide-react";
import { usePathname } from "next/navigation";
import {
  type PointerEvent as ReactPointerEvent,
  useCallback,
  useEffect,
  useState,
} from "react";
import { Button } from "@/components/primitives";
import { DEFAULT_MODEL } from "../chat/composer/model-picker";
import { ConductorProvider } from "../chat/runtime/provider";
import { Thread } from "../chat/thread";
import { chipLabel, type PageContext, usePageContext } from "./page-context";

export const MIN_WIDTH = 360;
export const MAX_WIDTH = 480;
const KEY = "yggdras.side-chat.v1";

export function clampWidth(width: number): number {
  return Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, Math.round(width)));
}

/** Mod+J (Ctrl on Windows/Linux, Cmd on macOS), without Shift or Alt. */
export function isToggle(
  event: Pick<
    KeyboardEvent,
    "key" | "metaKey" | "ctrlKey" | "shiftKey" | "altKey"
  >,
): boolean {
  return (
    (event.metaKey || event.ctrlKey) &&
    !event.shiftKey &&
    !event.altKey &&
    event.key.toLowerCase() === "j"
  );
}

function load(): { open: boolean; width: number } {
  try {
    const saved = JSON.parse(window.localStorage.getItem(KEY) || "{}");
    return {
      open: saved.open === true,
      width: clampWidth(Number(saved.width) || 400),
    };
  } catch {
    return { open: false, width: 400 };
  }
}

export function SideChat() {
  const registry = usePageContext();
  const path = usePathname();
  const [open, setOpen] = useState(false);
  const [width, setWidth] = useState(400);
  const [include, setInclude] = useState(true);
  const [preview, setPreview] = useState<PageContext | null>(null);
  const [panel, setPanel] = useState<HTMLElement | null>(null);

  useEffect(() => {
    const saved = load();
    setOpen(saved.open);
    setWidth(saved.width);
  }, []);
  useEffect(() => {
    try {
      window.localStorage.setItem(KEY, JSON.stringify({ open, width }));
    } catch {
      /* the panel works without remembering */
    }
    const root = document.documentElement;
    root.style.setProperty("--side-chat-push", open ? `${width}px` : "0px");
    return () => {
      root.style.removeProperty("--side-chat-push");
    };
  }, [open, width]);
  // A new page is a new context: the chip comes back.
  useEffect(() => setInclude(true), [path]);
  // The chip shows what would be sent now; refreshed on open and on navigation.
  useEffect(() => {
    if (open && registry) setPreview(registry.collect());
  }, [open, path, registry]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (isToggle(event)) {
        event.preventDefault();
        setOpen((o) => !o);
      } else if (
        event.key === "Escape" &&
        panel?.contains(document.activeElement)
      ) {
        setOpen(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [panel]);

  const extraBody = useCallback(
    () => (include && registry ? { pageContext: registry.collect() } : {}),
    [include, registry],
  );

  const startResize = (event: ReactPointerEvent) => {
    event.preventDefault();
    const move = (e: PointerEvent) =>
      setWidth(clampWidth(window.innerWidth - e.clientX));
    const up = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  };

  const chip =
    include && preview ? (
      <span className="flex items-center gap-1 rounded-md border-hairline border-hairline-strong py-0.5 pr-0.5 pl-2 text-xs text-text-2">
        <Eye className="size-3" aria-hidden />
        <span
          className="max-w-56 truncate"
          title="What Yggdras can see of this page"
        >
          {chipLabel(preview)}
        </span>
        <button
          type="button"
          aria-label="Don't share this page"
          onClick={() => setInclude(false)}
          className="grid size-5 place-items-center rounded-sm text-text-3 hover:bg-surface-3"
        >
          <X className="size-3" />
        </button>
      </span>
    ) : null;

  return (
    <aside
      ref={setPanel}
      aria-label="Side chat"
      aria-hidden={!open}
      inert={!open}
      style={{ width }}
      className={`fixed inset-y-0 right-0 z-40 flex max-w-full flex-col border-l-hairline bg-surface-1 shadow-lg motion-medium transition-transform ${
        open ? "translate-x-0" : "translate-x-full"
      }`}
    >
      <div
        role="separator"
        aria-orientation="vertical"
        aria-label="Resize side chat"
        aria-valuemin={MIN_WIDTH}
        aria-valuemax={MAX_WIDTH}
        aria-valuenow={width}
        tabIndex={0}
        onPointerDown={startResize}
        onKeyDown={(e) => {
          if (e.key === "ArrowLeft") setWidth((w) => clampWidth(w + 16));
          if (e.key === "ArrowRight") setWidth((w) => clampWidth(w - 16));
        }}
        className="absolute inset-y-0 left-0 w-1 cursor-col-resize hover:bg-(--state-hover) focus-visible:bg-(--state-active) focus-visible:outline-none"
      />
      <header className="flex h-11 items-center justify-between px-3">
        <h2 className="text-sm font-semibold text-text-1">Yggdras</h2>
        <Button
          size="icon"
          variant="ghost"
          aria-label="Close side chat (Ctrl+J)"
          onClick={() => setOpen(false)}
        >
          <PanelRightClose className="size-4" />
        </Button>
      </header>
      <div className="min-h-0 flex-1">
        <ConductorProvider
          conversationId={null}
          model={DEFAULT_MODEL}
          extraBody={extraBody}
        >
          <Thread
            model={DEFAULT_MODEL}
            onModel={() => {}}
            contextChip={chip}
            compact
          />
        </ConductorProvider>
      </div>
    </aside>
  );
}

/** The topbar button (the shortcut's discoverable twin). */
export function SideChatToggle() {
  return (
    <button
      type="button"
      className="icon-button"
      aria-label="Open side chat (Ctrl+J)"
      onClick={() =>
        window.dispatchEvent(
          new KeyboardEvent("keydown", { key: "j", ctrlKey: true }),
        )
      }
    >
      <MessagesSquare className="size-4.5" aria-hidden />
    </button>
  );
}
