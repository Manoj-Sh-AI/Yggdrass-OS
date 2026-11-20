"use client";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { ApiError } from "@/lib/api";
import { reconcileNoteCatalogue } from "@/lib/notes-catalogue";
import { draftRepository } from "@/lib/development-drafts";
import type { BrainNote } from "@/lib/brain-adapter";
import {
  blankNote,
  BRAIN_DRAFT_PREFIX,
  linkText,
  notesApi,
  type LiveNote,
  type NoteResult,
  type SavePreview,
} from "@/lib/notes-api";
import { useApp } from "./provider";
import { Modal } from "./ui";

type App = ReturnType<typeof useApp>;
type NotesContext = Omit<App, "brainMode"> & {
  brainMode: "lia" | "mock" | "unavailable";
  liveNotes: boolean;
  markdownBlocked: boolean;
  canUndo: boolean;
  undoBusy: boolean;
  undo: () => Promise<void>;
  searchBrain: (q: string) => Promise<void>;
  searchResultIds: string[] | null;
};
const Context = createContext<NotesContext | null>(null);
const nothing = async () => {};
export function useNotesApp(): NotesContext {
  const app = useApp();
  const notes = useContext(Context);
  return (
    notes || {
      ...app,
      liveNotes: false,
      markdownBlocked: false,
      canUndo: false,
      undoBusy: false,
      undo: nothing,
      searchBrain: nothing,
      searchResultIds: null,
    }
  );
}
export function NotesBrainProvider({
  children,
  initialNoteId,
}: {
  children: ReactNode;
  initialNoteId?: string;
}) {
  const app = useApp();
  const [notes, setNotes] = useState<LiveNote[]>([]),
    [noteId, setNoteId] = useState<string | null>(null),
    [ready, setReady] = useState(false),
    [brainError, setError] = useState(""),
    [available, setAvailable] = useState(false),
    [markdownBlocked, setMarkdownBlocked] = useState(false),
    [canUndo, setCanUndo] = useState(false),
    [undoBusy, setUndoBusy] = useState(false),
    [preview, setPreview] = useState<SavePreview | null>(null),
    [confirmBusy, setConfirmBusy] = useState(false);
  const guard = useRef<(() => Promise<boolean>) | null>(null);
  const pending = useRef<{
    resolve: (n: BrainNote) => void;
    reject: (e: unknown) => void;
  } | null>(null);
  const searchSequence = useRef(0);
  const latestQuery = useRef("");
  const initialNote = useRef(initialNoteId);
  const selectionSequence = useRef(0);
  const selected = useRef(noteId);
  selected.current = noteId;
  const [searchResultIds, setSearchResultIds] = useState<string[] | null>(null);
  const report = useCallback((e: unknown) => {
    if (e instanceof ApiError) {
      if (e.code === "brain_markdown") setMarkdownBlocked(true);
      if (e.extra?.canUndo !== undefined) setCanUndo(e.extra.canUndo);
    }
    const count = e instanceof ApiError ? e.extra?.completed : 0;
    const message =
      (e instanceof Error ? e.message : "The Brain request failed.") +
      (count
        ? ` ${count} change(s) were already saved; refresh before continuing.`
        : "");
    setError(message);
    return new Error(message);
  }, []);
  const accept = useCallback((result: NoteResult) => {
    setCanUndo(result.canUndo);
    setNotes((old) => [
      result.note,
      ...old.filter((n) => n.id !== result.note.id),
    ]);
    setError(result.reviewWarning || "");
    return result.note;
  }, []);
  const searchBrain = useCallback(
    async (q: string) => {
      latestQuery.current = q;
      const seq = ++searchSequence.current;
      let initialLoaded = false;
      try {
        // A graph deep link should not wait for every catalogue preview read.
        if (!q && initialNote.current) {
          const id = initialNote.current;
          initialNote.current = undefined;
          const opened = await notesApi.get(id);
          if (seq !== searchSequence.current) return;
          accept(opened);
          setNoteId(id);
          setAvailable(true);
          setReady(true);
          initialLoaded = true;
        }
        const result = await notesApi.search(q);
        if (seq !== searchSequence.current) return;
        if (!q && !selected.current) {
          try {
            const id = localStorage.getItem("yggdress.notes.active.v1");
            if (id && !result.notes.some((n) => n.id === id)) {
              const draft = draftRepository(
                localStorage,
                BRAIN_DRAFT_PREFIX,
              ).read(id);
              if (draft?.baseVersion === "new") {
                const restored = {
                  ...blankNote(),
                  id,
                  slug: id,
                  title: draft.title,
                  description: draft.description,
                };
                setNotes((old) => [restored, ...old]);
                setNoteId(id);
              }
            }
          } catch {
            /* The editor reports unreadable recovery data without replacing it. */
          }
        }
        setSearchResultIds(q ? result.notes.map((n) => n.id) : null);
        setNotes((old) =>
          reconcileNoteCatalogue(old, result.notes, q, selected.current),
        );
        setCanUndo(result.canUndo);
        setAvailable(true);
        setError("");
      } catch (e) {
        if (seq === searchSequence.current) {
          report(e);
          if (!initialLoaded) setAvailable(false);
        }
      } finally {
        if (seq === searchSequence.current) setReady(true);
      }
    },
    [report, accept],
  );
  useEffect(() => {
    const refresh = () => {
      if (document.visibilityState === "visible")
        void searchBrain(latestQuery.current);
    };
    window.addEventListener("yggdras:foreground", refresh);
    document.addEventListener("visibilitychange", refresh);
    return () => {
      window.removeEventListener("yggdras:foreground", refresh);
      document.removeEventListener("visibilitychange", refresh);
    };
  }, [searchBrain]);
  const reloadNote = useCallback(
    async (id: string) => {
      try {
        return accept(await notesApi.get(id));
      } catch (e) {
        report(e);
        throw e;
      }
    },
    [accept, report],
  );
  const openNote = useCallback(
    async (id: string) => {
      const sequence = ++selectionSequence.current;
      if (guard.current && !(await guard.current())) return false;
      if (sequence !== selectionSequence.current) return false;
      if (notes.find((n) => n.id === id)?.newNote) {
        setNoteId(id);
        return true;
      }
      try {
        const result = await notesApi.get(id);
        if (sequence !== selectionSequence.current) return false;
        accept(result);
        setNoteId(id);
        return true;
      } catch (e) {
        if (sequence === selectionSequence.current) report(e);
        return false;
      }
    },
    [accept, report, notes],
  );
  const createNote = useCallback(async () => {
    ++selectionSequence.current;
    if (guard.current && !(await guard.current())) return false;
    const note = blankNote();
    setNotes((old) => [note, ...old]);
    setNoteId(note.id);
    return true;
  }, []);
  const replaceNote = useCallback(
    async (edited: BrainNote) => {
      try {
        const note = edited as LiveNote;
        if (note.newNote) {
          const result = await notesApi.create(note);
          app.toast(
            `Saved. Found links: ${(result.links_added || []).map(linkText).join(", ") || "none"}`,
          );
          return accept(result);
        }
        const review = await notesApi.preview(note);
        if (!review.changes.length) return reloadNote(note.id);
        return await new Promise<BrainNote>((resolve, reject) => {
          pending.current = { resolve, reject };
          setPreview(review);
        });
      } catch (e) {
        report(e);
        throw e;
      }
    },
    [accept, app.toast, reloadNote, report],
  );
  const cancel = async () => {
    if (!preview || confirmBusy) return;
    try {
      await notesApi.cancel(preview.token);
    } catch (e) {
      report(e);
    }
    pending.current?.reject(
      new Error("Save cancelled. Your draft has been preserved."),
    );
    pending.current = null;
    setPreview(null);
  };
  const confirm = async () => {
    if (!preview || confirmBusy) return;
    setConfirmBusy(true);
    try {
      const result = await notesApi.confirm(preview.token);
      const note = accept(result);
      app.toast(
        `Saved. Found links: ${(result.links_added || []).map(linkText).join(", ") || "none"}`,
      );
      pending.current?.resolve(note);
    } catch (e) {
      report(e);
      pending.current?.reject(e);
    } finally {
      pending.current = null;
      setPreview(null);
      setConfirmBusy(false);
    }
  };
  const undo = async () => {
    if (undoBusy || !canUndo || preview) return;
    if (guard.current && !(await guard.current())) return;
    setUndoBusy(true);
    try {
      const undone = await notesApi.undo();
      setCanUndo(false);
      app.toast("Undone");
      if (noteId) {
        await reloadNote(noteId).catch(() => {
          setNoteId(null);
        });
      }
      await searchBrain("");
      if (undone.reviewWarning) setError(undone.reviewWarning);
      window.dispatchEvent(new Event("yggdress:brain-note-undone"));
    } catch (e) {
      report(e);
    } finally {
      setUndoBusy(false);
    }
  };
  const shelves = useMemo(
    () =>
      [...new Set(notes.map((n) => n.shelfId))].sort().map((id) => ({
        id,
        name: id.replace(/^\d+-/, "").replaceAll("-", " "),
        isArea: true,
        noteIds: notes.filter((n) => n.shelfId === id).map((n) => n.id),
      })),
    [notes],
  );
  const registerNoteGuard = useCallback(
    (value: (() => Promise<boolean>) | null) => {
      guard.current = value;
    },
    [],
  );
  const value: NotesContext = {
    ...app,
    state: { ...app.state, notes },
    ready,
    noteId,
    setNoteId,
    shelves,
    brainMode: available ? "lia" : "unavailable",
    brainError,
    liveNotes: true,
    markdownBlocked,
    canUndo,
    undoBusy,
    undo,
    searchBrain,
    searchResultIds,
    openNote,
    reloadNote,
    reloadBrain: async () => {
      await searchBrain("");
      return true;
    },
    createNote,
    replaceNote,
    registerNoteGuard,
  };
  return (
    <Context.Provider value={value}>
      {children}
      <Modal
        open={!!preview}
        onOpenChange={(open) => {
          if (!open) void cancel();
        }}
        title="Review note changes"
        description="Confirm the complete set of line changes before saving to Brain."
        preventDismiss={confirmBusy}
        wide
      >
        <div className="form-stack">
          {preview?.changes.map((change, index) => (
            <div className="panel" key={index}>
              <strong>{change.kind}</strong>
              <p style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>
                <del>{change.old || "(new line)"}</del>
                {" → "}
                <ins>{change.new || "(deleted)"}</ins>
              </p>
              {!!change.links_added.length && (
                <p>
                  Links added: {change.links_added.map(linkText).join(", ")}
                </p>
              )}
              {!!change.links_removed.length && (
                <p>
                  Links removed: {change.links_removed.map(linkText).join(", ")}
                </p>
              )}
              {change.kind === "remove-fact" && (
                <p className="error">This deletion cannot be undone.</p>
              )}
              {change.note && <small>{change.note}</small>}
            </div>
          ))}
          <button
            className="button primary"
            disabled={confirmBusy}
            onClick={() => void confirm()}
          >
            {confirmBusy ? "Saving…" : "Confirm changes"}
          </button>
          <button
            className="button"
            disabled={confirmBusy}
            onClick={() => void cancel()}
          >
            Cancel
          </button>
        </div>
      </Modal>
    </Context.Provider>
  );
}
