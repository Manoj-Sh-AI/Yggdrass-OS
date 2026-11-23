"use client";
/**
 * What the agent can see of the page (Phase E). Every screen registers a GETTER with
 * useRegisterPageContext(key, () => contribution); nothing is computed until a message is
 * sent, when the side panel calls collect(). The schema is the brief's PROPOSAL (its own
 * words: not an observed product payload).
 *
 * Safety rules [derived, brief E]: IDs plus a small projection, never whole records; a
 * sensitive entity is sent as an id with a placeholder label and `sensitivity:
 * "restricted"`, never its body; at most VISIBLE_CAP visible items. The server re-checks
 * all of this (conductor/page.py); the client is never the authority.
 */
import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
} from "react";

export type ContextRef = {
  kind: "task" | "doc" | "view" | "selection" | "file" | "event";
  id: string;
  label: string;
  url?: string;
  origin: "ambient" | "mention" | "selection";
  sensitivity?: "normal" | "restricted";
  fields?: Record<string, string | number | boolean>;
};

export type PageContext = {
  route: string;
  surface: string;
  focus?: ContextRef;
  visible: ContextRef[];
  selection?: { text: string; refs: ContextRef[] };
  capabilities: string[];
  capturedAt: string;
};

export type Contribution = Partial<
  Omit<PageContext, "capturedAt" | "route">
> & { surface?: string };

export const VISIBLE_CAP = 25;
const RESTRICTED_LABEL = "Sensitive note";

/** A sensitive ref keeps only its id and kind: label replaced, fields dropped. */
export function safeRef(ref: ContextRef): ContextRef {
  if (ref.sensitivity !== "restricted") return ref;
  return {
    kind: ref.kind,
    id: ref.id,
    label: RESTRICTED_LABEL,
    origin: ref.origin,
    sensitivity: "restricted",
  };
}

/** Merge contributions in registration order; later surfaces/focus win. */
export function mergeContributions(
  route: string,
  parts: Contribution[],
  now = new Date(),
): PageContext {
  const merged: PageContext = {
    route,
    surface: "page",
    visible: [],
    capabilities: [],
    capturedAt: now.toISOString(),
  };
  for (const part of parts) {
    if (part.surface) merged.surface = part.surface;
    if (part.focus) merged.focus = safeRef(part.focus);
    if (part.selection)
      merged.selection = {
        text: part.selection.refs.some((r) => r.sensitivity === "restricted")
          ? ""
          : part.selection.text.slice(0, 2000),
        refs: part.selection.refs.map(safeRef),
      };
    merged.visible.push(...(part.visible ?? []).map(safeRef));
    merged.capabilities.push(...(part.capabilities ?? []));
  }
  merged.visible = merged.visible.slice(0, VISIBLE_CAP);
  merged.capabilities = [...new Set(merged.capabilities)];
  return merged;
}

/** The chip's text: count and kind, never a dump ("Note · Invented plan + 12 visible"). */
export function chipLabel(page: PageContext): string {
  const kind = (r?: ContextRef) =>
    r?.kind === "doc" ? "Note" : r?.kind === "view" ? "" : (r?.kind ?? "");
  const head = page.focus
    ? [kind(page.focus), page.focus.label].filter(Boolean).join(" · ")
    : page.surface.replace(/-/g, " ");
  const others = page.visible.filter((r) => r.id !== page.focus?.id).length;
  return others ? `${head} + ${others} visible` : head;
}

type Registry = {
  register: (key: string, getter: () => Contribution) => () => void;
  collect: () => PageContext;
  version: () => number;
};

const PageContextReact = createContext<Registry | null>(null);

export function PageContextProvider({ children }: { children: ReactNode }) {
  const getters = useRef(new Map<string, () => Contribution>());
  const changes = useRef(0);
  const register = useCallback((key: string, getter: () => Contribution) => {
    getters.current.set(key, getter);
    changes.current += 1;
    return () => {
      if (getters.current.get(key) === getter) getters.current.delete(key);
      changes.current += 1;
    };
  }, []);
  const collect = useCallback(() => {
    const parts: Contribution[] = [];
    for (const getter of getters.current.values()) {
      try {
        parts.push(getter());
      } catch {
        /* a broken contributor never blocks sending */
      }
    }
    return mergeContributions(
      typeof window === "undefined" ? "" : window.location.pathname,
      parts,
    );
  }, []);
  const value = useMemo(
    () => ({ register, collect, version: () => changes.current }),
    [register, collect],
  );
  return (
    <PageContextReact.Provider value={value}>
      {children}
    </PageContextReact.Provider>
  );
}

export function usePageContext(): Registry | null {
  return useContext(PageContextReact);
}

/** A screen says what it shows. The getter runs only when a message is sent. */
export function useRegisterPageContext(
  key: string,
  getter: () => Contribution,
) {
  const registry = useContext(PageContextReact);
  const latest = useRef(getter);
  latest.current = getter;
  useEffect(
    () => registry?.register(key, () => latest.current()),
    [registry, key],
  );
}
