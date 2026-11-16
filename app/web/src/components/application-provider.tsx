"use client";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { seed } from "@/lib/data";
import { isState } from "@/lib/repository";
import { applicationApi } from "@/lib/api";
import {
  brainAdapter,
  type BrainNote,
  type BrainShelf,
  type DeletePreview,
} from "@/lib/brain-adapter";
import type { CaptureInput, DemoState, Task } from "@/lib/types";
import { draftRepository } from "@/lib/development-drafts";
type ViewState = Omit<DemoState, "notes"> & { notes: BrainNote[] };
type Context = {
  state: ViewState;
  ready: boolean;
  error: string;
  update: (fn: (s: DemoState) => DemoState) => Promise<boolean>;
  reset: () => Promise<void>;
  toast: (s: string) => void;
  openNote: (id: string) => Promise<boolean>;
  registerNoteGuard: (guard: (() => Promise<boolean>) | null) => void;
  closeNote: () => Promise<boolean>;
  noteId: string | null;
  setNoteId: (id: string | null) => void;
  shelves: BrainShelf[];
  brainMode: "mock" | "unavailable";
  brainError: string;
  reloadBrain: () => Promise<boolean>;
  reloadNote: (id: string) => Promise<BrainNote>;
  createNote: (input: CaptureInput) => Promise<boolean>;
  replaceNote: (note: BrainNote) => Promise<BrainNote>;
  previewDelete: (note: BrainNote) => Promise<DeletePreview>;
  confirmDelete: (preview: DeletePreview) => Promise<void>;
};
const Context = createContext<Context | null>(null);
const PREFS = "yggdress.app.preferences.v1";
export function AppProvider({ children }: { children: ReactNode }) {
  const initial = () => ({
    ...seed(new Date("2026-01-01T12:00:00Z")),
    notes: [],
    tasks: [],
    activities: [],
  });
  const [state, setState] = useState<ViewState>(initial),
    current = useRef(state),
    queue = useRef(Promise.resolve());
  const noteGuard = useRef<(() => Promise<boolean>) | null>(null);
  const registerNoteGuard = useCallback(
    (guard: (() => Promise<boolean>) | null) => {
      noteGuard.current = guard;
    },
    [],
  );
  const closeNote = useCallback(async () => {
    if (noteGuard.current && !(await noteGuard.current())) return false;
    setNoteId(null);
    return true;
  }, []);
  const [ready, setReady] = useState(false),
    [error, setError] = useState(""),
    [message, setMessage] = useState(""),
    [noteId, setNoteId] = useState<string | null>(null),
    [shelves, setShelves] = useState<BrainShelf[]>([]),
    [brainMode, setBrainMode] = useState<"mock" | "unavailable">("unavailable"),
    [brainError, setBrainError] = useState("");
  const publish = useCallback((fn: (s: ViewState) => ViewState) => {
    const next = fn(current.current);
    current.current = next;
    setState(next);
  }, []);
  const reloadBrain = useCallback(async () => {
    try {
      const [tree, list] = await Promise.all([
        brainAdapter.tree(),
        brainAdapter.notes(),
      ]);
      if (tree.mode !== "mock" || list.mode !== "mock")
        throw new Error(
          "Real Brain integration requires Claude’s approved contract.",
        );
      setShelves(tree.shelves);
      setBrainMode("mock");
      setBrainError("");
      publish((s) => ({ ...s, notes: list.notes }));
      return true;
    } catch (e) {
      setBrainMode("unavailable");
      setBrainError(e instanceof Error ? e.message : "Lia unavailable.");
      setShelves([]);
      publish((s) => ({ ...s, notes: [] }));
      return false;
    }
  }, [publish]);
  useEffect(() => {
    let active = true;
    const load = async () => {
      const next = {
        ...seed(),
        notes: [],
        tasks: [],
        activities: [],
      } as ViewState;
      try {
        const raw = localStorage.getItem(PREFS);
        if (raw) {
          const candidate = { ...next, preferences: JSON.parse(raw) };
          if (isState(candidate)) next.preferences = candidate.preferences;
        }
      } catch {
        /* Appearance defaults do not import legacy note storage. */
      }
      if (active) publish(() => next);
      try {
        const result = await applicationApi<{ tasks: Task[] }>(
          "application/tasks",
        );
        if (active) publish((s) => ({ ...s, tasks: result.tasks }));
      } catch (e) {
        if (active)
          setError(
            e instanceof Error ? e.message : "Application data unavailable.",
          );
      }
      if (active) {
        setReady(true);
      }
    };
    void load();
    return () => {
      active = false;
    };
  }, [publish, reloadBrain]);
  useEffect(() => {
    const reload = () => {
      void applicationApi<{ tasks: Task[] }>("application/tasks")
        .then((result) => publish((s) => ({ ...s, tasks: result.tasks })))
        .catch(() => {});
    };
    window.addEventListener("yggdress:planning-changed", reload);
    return () =>
      window.removeEventListener("yggdress:planning-changed", reload);
  }, [publish]);
  useEffect(() => {
    if (!message) return;
    const t = setTimeout(() => setMessage(""), 4500);
    return () => clearTimeout(t);
  }, [message]);
  const toast = useCallback((text: string) => setMessage(text), []);
  const update = useCallback(
    (fn: (s: DemoState) => DemoState): Promise<boolean> => {
      const action = queue.current.then(async () => {
        try {
          const before = current.current,
            next = fn(before);
          if (JSON.stringify(next.notes) !== JSON.stringify(before.notes))
            throw new Error(
              "Note mutations must pass through the Brain adapter.",
            );
          const old = new Map(before.tasks.map((t) => [t.id, t]));
          if (next.tasks.length < before.tasks.length)
            throw new Error("Task deletion is not part of this phase.");
          for (const task of next.tasks) {
            const previous = old.get(task.id);
            if (!previous) {
              await applicationApi("application/tasks", {
                method: "POST",
                body: JSON.stringify({
                  title: task.title,
                  description: task.description || "",
                  area: task.area,
                  date: task.date,
                }),
              });
            } else if (JSON.stringify(previous) !== JSON.stringify(task)) {
              if (
                previous.title !== task.title ||
                previous.area !== task.area ||
                previous.date !== task.date
              )
                throw new Error(
                  "Use the Task Manager editor to change task details.",
                );
              await applicationApi(
                `application/tasks/${encodeURIComponent(task.id)}`,
                {
                  method: "PATCH",
                  body: JSON.stringify({
                    done: task.done,
                    version: previous.version,
                  }),
                },
              );
            }
          }
          let tasks = before.tasks;
          if (JSON.stringify(next.tasks) !== JSON.stringify(before.tasks))
            tasks = (
              await applicationApi<{ tasks: Task[] }>("application/tasks")
            ).tasks;
          if (JSON.stringify(next.tasks) !== JSON.stringify(before.tasks))
            window.dispatchEvent(new Event("yggdress:tasks-changed"));
          if (
            JSON.stringify(next.preferences) !==
            JSON.stringify(before.preferences)
          )
            localStorage.setItem(PREFS, JSON.stringify(next.preferences));
          publish((s) => ({
            ...s,
            preferences: next.preferences,
            tasks,
            activities: next.activities,
          }));
          setError("");
          return true;
        } catch (e) {
          setError(e instanceof Error ? e.message : "Could not save.");
          return false;
        }
      });
      queue.current = action.then(() => {});
      return action;
    },
    [publish],
  );
  const reloadNote = useCallback(
    async (id: string) => {
      const { note } = await brainAdapter.note(id);
      publish((s) => ({
        ...s,
        notes: [note, ...s.notes.filter((n) => n.id !== id)],
      }));
      return note;
    },
    [publish],
  );
  const openNote = useCallback(
    async (id: string) => {
      if (noteGuard.current && !(await noteGuard.current())) return false;
      try {
        await reloadNote(id);
        setNoteId(id);
        return true;
      } catch (e) {
        const message = e instanceof Error ? e.message : "Note unavailable.";
        setBrainError(message);
        toast(message);
        return false;
      }
    },
    [reloadNote, toast],
  );
  const createNote = useCallback(
    async (input: CaptureInput) => {
      try {
        if (brainMode !== "mock")
          throw new Error("Lia unavailable. Capture was not saved.");
        if (
          window.location.pathname === "/notes" &&
          noteGuard.current &&
          !(await noteGuard.current())
        )
          return false;
        const shelfId = input.shelfId || "14-inbox";
        if (!shelves.some((s) => s.id === shelfId))
          throw new Error(
            "Choose a destination supplied by the Brain adapter.",
          );
        const content = input.filename
          ? `${input.content}\n\nFilename (metadata only): ${input.filename}`
          : input.content;
        const result = await brainAdapter.create({
          title: input.title.trim(),
          description: input.content.trim().slice(0, 130),
          content,
          tags: input.tags,
          shelfId,
        });
        publish((s) => ({ ...s, notes: [result.note, ...s.notes] }));
        if (window.location.pathname === "/notes") {
          setNoteId(result.note.id);
        }
        return true;
      } catch (e) {
        setBrainError(
          e instanceof Error ? e.message : "Brain capture unavailable.",
        );
        return false;
      }
    },
    [brainMode, shelves, publish],
  );
  const replaceNote = useCallback(
    async (note: BrainNote) => {
      const result = await brainAdapter.replace(note);
      publish((s) => ({
        ...s,
        notes: s.notes.map((n) => (n.id === note.id ? result.note : n)),
      }));
      return result.note;
    },
    [publish],
  );
  const previewDelete = useCallback(
    async (note: BrainNote) => (await brainAdapter.previewDelete(note)).preview,
    [],
  );
  const confirmDelete = useCallback(
    async (preview: DeletePreview) => {
      await draftRepository(localStorage).deleteWithConfirmation(
        preview.noteId,
        () => brainAdapter.confirmDelete(preview),
      );
      setNoteId(null);
      await reloadBrain();
    },
    [reloadBrain],
  );
  const reset = useCallback(async () => {
    try {
      const preferences = seed().preferences;
      localStorage.setItem(PREFS, JSON.stringify(preferences));
      publish((s) => ({ ...s, preferences }));
      toast(
        "Appearance preferences reset. PostgreSQL records and Brain data were preserved.",
      );
    } catch {
      setError("Could not reset appearance preferences.");
    }
  }, [publish, toast]);
  return (
    <Context.Provider
      value={{
        state,
        ready,
        error,
        update,
        reset,
        toast,
        openNote,
        registerNoteGuard,
        closeNote,
        noteId,
        setNoteId,
        shelves,
        brainMode,
        brainError,
        reloadBrain,
        reloadNote,
        createNote,
        replaceNote,
        previewDelete,
        confirmDelete,
      }}
    >
      {children}
      <div className="toast" role="status" aria-live="polite">
        {message}
      </div>
    </Context.Provider>
  );
}
export function useApp() {
  const value = useContext(Context);
  if (!value) throw new Error("Missing application provider");
  return value;
}
