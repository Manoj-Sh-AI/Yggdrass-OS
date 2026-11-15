"use client";
import {
  Component,
  memo,
  useCallback,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useCreateBlockNote } from "@blocknote/react";
import { useRouter } from "next/navigation";
import type { BlockNoteEditor } from "@blocknote/core";
import { BlockNoteView } from "@blocknote/ariakit";
import "@blocknote/ariakit/style.css";
import type { BrainNote, DeletePreview } from "@/lib/brain-adapter";
import { documentFrom, markdownWarnings } from "@/lib/note-document";
import { DRAFT_PREFIX, draftRepository } from "@/lib/development-drafts";
import { NoteSaveSession, type NoteSnapshot } from "@/lib/note-save-session";
import { useNotesApp } from "./notes-brain-provider";
import { BRAIN_DRAFT_PREFIX, type LiveNote } from "@/lib/notes-api";
import { Icon, Modal } from "./ui";

function download(name: string, value: string, type = "application/json") {
  const url = URL.createObjectURL(new Blob([value], { type }));
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function originalRecovery(note: BrainNote) {
  try {
    return (
      localStorage.getItem(
        (note.source === "lia" ? BRAIN_DRAFT_PREFIX : DRAFT_PREFIX) + note.id,
      ) || JSON.stringify(note, null, 2)
    );
  } catch {
    return JSON.stringify(note, null, 2);
  }
}
class EditorBoundary extends Component<
  { note: BrainNote; children: ReactNode },
  { failed: boolean }
> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    return this.state.failed ? (
      <div className="editor-error" role="alert">
        <h3>This document could not be opened</h3>
        <p>
          The original data is preserved. Export it before making further
          changes.
        </p>
        <button
          className="button"
          onClick={() =>
            download("preserved-note.json", originalRecovery(this.props.note))
          }
        >
          Export original
        </button>
      </div>
    ) : (
      this.props.children
    );
  }
}
export default function NoteEditor({
  note,
  compact = false,
}: {
  note: BrainNote;
  compact?: boolean;
}) {
  const { reloadNote, liveNotes } = useNotesApp();
  const [generation, setGeneration] = useState(0);
  const reload = async () => {
    await reloadNote(note.id);
    localStorage.removeItem(
      (liveNotes ? BRAIN_DRAFT_PREFIX : DRAFT_PREFIX) + note.id,
    );
    setGeneration((g) => g + 1);
  };
  useEffect(() => {
    if (!liveNotes) return;
    const refresh = () => {
      localStorage.removeItem(BRAIN_DRAFT_PREFIX + note.id);
      setGeneration((g) => g + 1);
    };
    window.addEventListener("yggdress:brain-note-undone", refresh);
    return () =>
      window.removeEventListener("yggdress:brain-note-undone", refresh);
  }, [liveNotes, note.id]);
  if (note.documentError)
    return (
      <div className="editor-error" role="alert">
        <h3>Original document preserved</h3>
        <p>{note.documentError}</p>
        <button
          className="button"
          onClick={() =>
            download("original-note.txt", note.content, "text/plain")
          }
        >
          Export original
        </button>
      </div>
    );
  return (
    <EditorBoundary key={`${note.id}:${generation}`} note={note}>
      <DocumentEditor
        key={`${note.id}:${generation}`}
        note={note}
        compact={compact}
        reload={reload}
      />
    </EditorBoundary>
  );
}
function DocumentEditor({
  note,
  compact,
  reload,
}: {
  note: BrainNote;
  compact: boolean;
  reload: () => Promise<void>;
}) {
  const router = useRouter();
  const {
    replaceNote,
    registerNoteGuard,
    previewDelete,
    confirmDelete,
    toast,
    liveNotes,
    canUndo,
    undoBusy,
    undo,
  } = useNotesApp();
  const prefix = liveNotes ? BRAIN_DRAFT_PREFIX : DRAFT_PREFIX;
  const newNote = liveNotes && (note as LiveNote).newNote;
  const [recovery] = useState(() => {
    try {
      return {
        draft: draftRepository(localStorage, prefix).read(note.id),
        error: "",
      };
    } catch (error) {
      return {
        draft: null,
        error:
          error instanceof Error ? error.message : "Local draft unavailable.",
      };
    }
  });
  const initial = recovery.draft?.document || note.document;
  const [editing, setEditing] = useState(!compact),
    [reading, setReading] = useState(false),
    [, render] = useState(0),
    [exportOpen, setExportOpen] = useState(false),
    [preview, setPreview] = useState<DeletePreview | null>(null),
    [confirmed, setConfirmed] = useState(false),
    [deleting, setDeleting] = useState(false),
    [actionError, setActionError] = useState("");
  const active = useRef(false),
    timer = useRef<ReturnType<typeof setTimeout> | null>(null),
    alive = useRef(true);
  const editor = useCreateBlockNote(
    {
      initialContent: initial?.blocks.length ? initial.blocks : undefined,
      domAttributes: {
        editor: {
          "aria-label": "Content",
          role: "textbox",
          "aria-multiline": "true",
        },
      },
    },
    [],
  );
  const [session] = useState(
    () =>
      new NoteSaveSession({
        note,
        snapshot: {
          title: note.title,
          description: note.description,
          tags: note.tags,
          document: initial || documentFrom([], note.content),
        },
        recovery: recovery.draft,
        write: replaceNote,
        persist: (d) => draftRepository(localStorage, prefix).write(d),
        markdown: (d) => editor.blocksToMarkdownLossy(d.blocks),
        changed: () => {
          if (alive.current) render((n) => n + 1);
        },
      }),
  );
  const flush = useCallback(async () => {
    if (timer.current) clearTimeout(timer.current);
    if (recovery.error) return false;
    if (liveNotes && session.note.version === "new" && !session.dirty)
      session.update(session.snapshot);
    let ok = await session.flush();
    if (ok && session.dirty) ok = await session.flush();
    if (ok && liveNotes && session.note.version !== note.version)
      await reload();
    return ok;
  }, [session, recovery.error, liveNotes, reload, note.version]);
  const leave = useCallback(async () => {
    if (!liveNotes) return flush();
    if (session.state === "saving") return false;
    if (!session.dirty) return true;
    try {
      session.checkpoint();
      session.error =
        "Save this draft or reload the latest note before leaving. Your entered content has been preserved.";
    } catch (e) {
      session.state = "failed";
      session.error =
        e instanceof Error ? e.message : "Could not retain the draft.";
    }
    render((n) => n + 1);
    return false;
  }, [liveNotes, flush, session]);
  const handleChange = useCallback(() => {
    if (active.current) {
      session.update({
        ...session.snapshot,
        document: { ...session.snapshot.document, blocks: editor.document },
      });
      if (timer.current) clearTimeout(timer.current);
      if (!compact && !liveNotes)
        timer.current = setTimeout(() => void flush(), 900);
    }
  }, [session, editor, compact, flush, liveNotes]);
  const schedule = () => {
    if (timer.current) clearTimeout(timer.current);
    if (!compact && !liveNotes)
      timer.current = setTimeout(() => void flush(), 900);
  };
  const update = (patch: Partial<NoteSnapshot>) => {
    session.update({ ...session.snapshot, ...patch });
    schedule();
  };
  useEffect(() => {
    alive.current = true;
    if (!initial) {
      const blocks = editor.tryParseMarkdownToBlocks(note.content);
      editor.replaceBlocks(
        editor.document,
        blocks.length ? blocks : [{ type: "paragraph" }],
      );
      session.snapshot = {
        ...session.snapshot,
        document: documentFrom(editor.document, note.content),
      };
    }
    active.current = true;
    registerNoteGuard(leave);
    if (!recovery.error && session.state !== "conflict" && !session.dirty) {
      try {
        session.checkpoint();
      } catch (e) {
        session.state = "failed";
        session.error =
          e instanceof Error ? e.message : "Local draft storage unavailable.";
        render((n) => n + 1);
      }
    }
    if (
      recovery.draft?.dirty &&
      !liveNotes &&
      !compact &&
      session.state !== "conflict" &&
      !recovery.error
    )
      timer.current = setTimeout(() => void flush(), 900);
    const checkpoint = () => {
      if (session.dirty) {
        try {
          session.checkpoint();
        } catch (error) {
          session.state = "failed";
          session.error =
            error instanceof Error
              ? error.message
              : "Could not retain a recovery draft.";
          if (alive.current) render((n) => n + 1);
        }
      }
    };
    const unload = (e: BeforeUnloadEvent) => {
      checkpoint();
      if (session.dirty && session.state === "failed") {
        e.preventDefault();
        e.returnValue = "";
      }
    };
    const hidden = () => {
      if (document.visibilityState === "hidden") checkpoint();
    };
    window.addEventListener("beforeunload", unload);
    document.addEventListener("visibilitychange", hidden);
    return () => {
      alive.current = false;
      active.current = false;
      if (timer.current) clearTimeout(timer.current);
      checkpoint();
      registerNoteGuard(null);
      window.removeEventListener("beforeunload", unload);
      document.removeEventListener("visibilitychange", hidden);
    };
  }, []);
  useEffect(() => {
    const hotkey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") {
        e.preventDefault();
        void flush();
      }
    };
    window.addEventListener("keydown", hotkey);
    return () => window.removeEventListener("keydown", hotkey);
  }, [flush]);
  useEffect(() => {
    const navigate = (event: MouseEvent) => {
      if (
        !session.dirty ||
        event.defaultPrevented ||
        event.button !== 0 ||
        event.metaKey ||
        event.ctrlKey ||
        event.shiftKey ||
        event.altKey
      )
        return;
      const anchor = (event.target as HTMLElement)?.closest?.(
        "a[href]",
      ) as HTMLAnchorElement | null;
      if (
        !anchor ||
        anchor.target === "_blank" ||
        anchor.hasAttribute("download")
      )
        return;
      const target = new URL(anchor.href, window.location.href);
      if (
        target.origin !== window.location.origin ||
        target.protocol !== window.location.protocol ||
        target.pathname === window.location.pathname
      )
        return;
      event.preventDefault();
      event.stopPropagation();
      void leave().then((ok) => {
        if (ok) router.push(target.pathname + target.search + target.hash);
      });
    };
    document.addEventListener("click", navigate, true);
    return () => document.removeEventListener("click", navigate, true);
  }, [session, leave, router]);
  const snapshot = session.snapshot;
  const canEdit =
    editing &&
    !reading &&
    !recovery.error &&
    !(liveNotes && session.state === "saving");
  const status = recovery.error ? "failed" : session.state;
  const errors = recovery.error || session.error || actionError;
  const warning = exportOpen ? markdownWarnings(snapshot.document.blocks) : [];
  const toolbar = (label: string, icon: string, action: () => void) => (
    <button
      className="editor-tool"
      aria-label={label}
      title={label}
      disabled={!canEdit}
      onMouseDown={(e) => e.preventDefault()}
      onClick={() => {
        editor.focus();
        action();
      }}
    >
      <Icon name={icon} size={15} />
    </button>
  );
  return (
    <section
      className={`note-editor ${compact ? "compact-editor" : ""}`}
      aria-label="Note editor"
    >
      <div className="editor-topbar">
        <span className="editor-breadcrumb">
          <Icon name="NotebookPen" size={14} />
          {note.shelfId.replace(/^\d+-/, "").replaceAll("-", " ")}
          <Icon name="ChevronRight" size={12} />
          <span>{liveNotes ? "Brain note" : "Private demo"}</span>
        </span>
        <span
          className={`save-state ${status}`}
          role="status"
          data-save-state={status}
        >
          <i />
          {
            {
              unsaved: "Unsaved changes",
              saving: "Saving…",
              saved: liveNotes
                ? newNote
                  ? "New draft"
                  : "Saved to Brain"
                : "Saved locally",
              failed: "Failed",
              conflict: "Conflict",
            }[status]
          }
        </span>
      </div>
      <div className="editor-actions">
        {compact && (
          <button
            className="button small-button"
            onClick={() => setEditing((e) => !e)}
          >
            {editing ? "Cancel edit" : "Edit note"}
          </button>
        )}
        {!compact && (
          <button
            className="editor-tool"
            aria-label={reading ? "Switch to editing" : "Reading mode"}
            onClick={() => setReading((r) => !r)}
          >
            <Icon name={reading ? "Pencil" : "BookOpen"} size={16} />
          </button>
        )}
        <button
          className="button small-button"
          disabled={status === "saving" || !!recovery.error}
          onClick={() => void flush()}
        >
          <Icon name="Save" size={13} />
          {compact ? "Save changes" : "Save now"}
        </button>
        <button
          className="editor-tool"
          aria-label="Export note"
          title="Export note"
          onClick={() => setExportOpen(true)}
        >
          <Icon name="Download" size={16} />
        </button>
        {liveNotes && (
          <button
            className="button small-button"
            disabled={!canUndo || undoBusy || status === "saving"}
            onClick={() => void undo()}
          >
            Undo last saved change
          </button>
        )}
        {!liveNotes && (
          <button
            className="editor-tool danger-tool"
            aria-label="Preview permanent deletion"
            title="Preview permanent deletion"
            disabled={deleting || status === "saving"}
            onClick={async () => {
              setActionError("");
              if (!(await flush())) return;
              try {
                setPreview(await previewDelete(session.note));
                setConfirmed(false);
              } catch (e) {
                setActionError(
                  e instanceof Error
                    ? e.message
                    : "Delete preview unavailable.",
                );
              }
            }}
          >
            <Icon name="Trash2" size={15} />
          </button>
        )}
      </div>
      <div className="editor-document-heading">
        <input
          className="note-emoji"
          value={snapshot.document.icon}
          placeholder="✧"
          maxLength={8}
          aria-label="Note icon"
          disabled={!canEdit || liveNotes}
          onChange={(e) =>
            update({ document: { ...snapshot.document, icon: e.target.value } })
          }
        />
        <input
          className="note-title-input"
          aria-label="Title"
          value={snapshot.title}
          placeholder="Untitled note"
          maxLength={180}
          readOnly={!canEdit || (liveNotes && !newNote)}
          onChange={(e) => update({ title: e.target.value })}
        />
        <input
          className="note-summary-input"
          aria-label="Summary"
          placeholder="A little context, if you need it…"
          value={snapshot.description}
          readOnly={!canEdit || (liveNotes && !newNote)}
          maxLength={1000}
          onChange={(e) => update({ description: e.target.value })}
        />
      </div>
      <div
        className="editor-format-tools"
        role="toolbar"
        aria-label="Writing tools"
      >
        {toolbar(liveNotes ? "Undo typing" : "Undo", "Undo2", () =>
          editor.undo(),
        )}
        {toolbar("Redo", "Redo2", () => editor.redo())}
        <span className="tool-separator" />
        {toolbar("Move block up", "ArrowUp", () => editor.moveBlocksUp())}
        {toolbar("Move block down", "ArrowDown", () => editor.moveBlocksDown())}
        {toolbar("Duplicate block", "Copy", () => {
          const b = editor.getTextCursorPosition().block;
          const strip = (value: unknown): unknown => {
            if (Array.isArray(value)) return value.map(strip);
            if (value && typeof value === "object")
              return Object.fromEntries(
                Object.entries(value)
                  .filter(([k]) => k !== "id")
                  .map(([k, v]) => [k, strip(v)]),
              );
            return value;
          };
          editor.insertBlocks([strip(b) as typeof b], b, "after");
        })}
        {toolbar("Add paragraph", "Plus", () =>
          editor.insertBlocks(
            [{ type: "paragraph" }],
            editor.getTextCursorPosition().block,
            "after",
          ),
        )}
        {toolbar("Remove block", "Minus", () =>
          editor.removeBlocks([editor.getTextCursorPosition().block]),
        )}
      </div>
      {errors && (
        <div className="editor-error" role="alert">
          {errors}
          <div className="editor-error-actions">
            <button
              className="button small-button"
              onClick={async () => {
                try {
                  await reload();
                } catch (e) {
                  setActionError(
                    e instanceof Error ? e.message : "Reload unavailable.",
                  );
                }
              }}
            >
              Reload latest note
            </button>
            <button
              className="button small-button"
              onClick={() =>
                download(
                  "local-note-recovery.json",
                  recovery.error
                    ? originalRecovery(note)
                    : JSON.stringify(snapshot, null, 2),
                )
              }
            >
              Export recovery draft
            </button>
          </div>
          <small>
            Reload replaces this local draft with the latest{" "}
            {liveNotes ? "Brain" : "mock"} note. Export first if you want to
            keep it.
          </small>
        </div>
      )}
      <EditorCanvas
        editor={editor}
        editable={canEdit}
        onChange={handleChange}
      />
      <div className="editor-footer">
        <span>
          Type <kbd>/</kbd> for blocks · drag the handle to reorder
        </span>
        <a
          href="/licenses/blocknote/MPL-2.0.txt"
          target="_blank"
          rel="noreferrer"
        >
          BlockNote · MPL-2.0
        </a>
      </div>
      {canEdit && !liveNotes && (
        <label className="editor-tags">
          Tags, separated by commas
          <input
            value={snapshot.tags.join(", ")}
            placeholder="Add a tag…"
            onChange={(e) =>
              update({
                tags: e.target.value.split(",").map((t) => t.trimStart()),
              })
            }
          />
        </label>
      )}
      <div className="editor-local-notice">
        <Icon name="HardDrive" size={13} />
        <span>
          {liveNotes ? (
            "Explicit save reviews changes to the Facts section. Metadata and other sections are read-only in the current Brain API. Unsaved recovery drafts stay in this browser."
          ) : (
            <>
              Synthetic development note · rich blocks and recovery drafts stay
              in this browser. Mock text uses the existing adapter. Real Brain
              sync is not connected.
            </>
          )}
        </span>
      </div>
      <Modal
        open={exportOpen}
        onOpenChange={setExportOpen}
        title="Take your note with you"
        description="Native JSON preserves every block and style. Markdown is a portable, potentially lossy export."
      >
        <div className="form-stack">
          {warning.length > 0 && (
            <div className="editor-error">
              {warning.map((w) => (
                <p key={w}>{w}</p>
              ))}
            </div>
          )}
          <button
            className="button primary"
            onClick={() =>
              download(
                `${snapshot.title || "note"}.json`,
                JSON.stringify(snapshot.document, null, 2),
              )
            }
          >
            Download lossless JSON
          </button>
          <button
            className="button"
            onClick={() =>
              download(
                `${snapshot.title || "note"}.md`,
                editor.blocksToMarkdownLossy(snapshot.document.blocks),
                "text/markdown",
              )
            }
          >
            Download Markdown{warning.length ? " (formatting may change)" : ""}
          </button>
        </div>
      </Modal>
      <Modal
        open={!!preview}
        onOpenChange={(v) => {
          if (!v && !deleting) setPreview(null);
        }}
        title="Delete this synthetic note?"
        description="Development data only. This is not a real Brain deletion."
      >
        <section
          aria-label="Permanent delete preview"
          className="delete-preview"
        >
          <strong>{preview?.title}</strong>
          <div className="markdown-content">{preview?.content}</div>
          <label>
            <input
              type="checkbox"
              checked={confirmed}
              onChange={(e) => setConfirmed(e.target.checked)}
            />
            I understand this permanently deletes the note.
          </label>
          <div className="modal-actions">
            <button
              className="button"
              disabled={deleting}
              onClick={() => setPreview(null)}
            >
              Cancel deletion
            </button>
            <button
              className="button primary"
              disabled={!confirmed || deleting}
              onClick={async () => {
                if (!preview) return;
                setDeleting(true);
                try {
                  await confirmDelete(preview);
                  toast("Synthetic note and its local draft deleted.");
                } catch (e) {
                  setActionError(
                    e instanceof Error ? e.message : "Deletion unavailable.",
                  );
                  setPreview(null);
                } finally {
                  setDeleting(false);
                }
              }}
            >
              Delete permanently
            </button>
          </div>
        </section>
      </Modal>
    </section>
  );
}
const EditorCanvas = memo(function EditorCanvas({
  editor,
  editable,
  onChange,
}: {
  editor: BlockNoteEditor;
  editable: boolean;
  onChange: () => void;
}) {
  return (
    <BlockNoteView
      editor={editor}
      editable={editable}
      onChange={onChange}
      theme="dark"
      emojiPicker={false}
      comments={false}
      attributionTooltip={false}
    />
  );
});
