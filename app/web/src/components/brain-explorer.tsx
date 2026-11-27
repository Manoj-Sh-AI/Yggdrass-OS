"use client";
import { EyeOff } from "lucide-react";
import { ListRow } from "@/components/primitives";
import { useRegisterPageContext } from "@/features/side-chat/page-context";
import { useEffect, useMemo, useRef, useState } from "react";
import type { BrainNote } from "@/lib/brain-adapter";
import { recoveryBundle } from "@/lib/development-drafts";
import { BRAIN_DRAFT_PREFIX } from "@/lib/notes-api";
import { searchNotes } from "@/lib/repository";
import { useNotesApp } from "./notes-brain-provider";
import { NoteEditor, preloadNoteEditor } from "./note-editor-loader";
import { NoteLinkedWork } from "./note-linked-work";
import { Empty, Icon, Modal, Panel, relativeTime } from "./ui";

const PHONE = "(max-width: 720px)";

export function BrainExplorer({
  initialNoteId,
  initialCreate = false,
}: { initialNoteId?: string; initialCreate?: boolean } = {}) {
  const {
    state,
    shelves,
    noteId,
    setNoteId,
    openNote,
    ready,
    brainMode,
    brainError,
    reloadBrain,
    createNote,
    liveNotes,
    markdownBlocked,
    canUndo,
    undoBusy,
    undo,
    searchBrain,
    searchResultIds,
  } = useNotesApp();
  const [query, setQuery] = useState(""),
    [search, setSearch] = useState(""),
    [navigation, setNavigation] = useState(true),
    [context, setContext] = useState(false),
    [shelf, setShelf] = useState<string | null>(null),
    [creating, setCreating] = useState(false),
    [title, setTitle] = useState(""),
    [destination, setDestination] = useState("14-inbox"),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const created = useRef(false);
  // Phone (Notion's mobile layout): the list and the page are two screens. A note opens
  // only when tapped, never by itself, and the page has a slim bar: back, area, menu.
  const [phone, setPhone] = useState(
    () => typeof window !== "undefined" && window.matchMedia(PHONE).matches,
  );
  const [menu, setMenu] = useState(false);
  useEffect(() => {
    const query = window.matchMedia(PHONE);
    const change = () => setPhone(query.matches);
    change();
    query.addEventListener("change", change);
    return () => query.removeEventListener("change", change);
  }, []);
  // On a phone the page opens only when tapped. Loading can still select a note (a
  // recovered unsaved draft is reopened by the provider): it stays in the list instead.
  const tapped = useRef(false);
  useEffect(() => {
    if (
      phone &&
      ready &&
      noteId &&
      !tapped.current &&
      !initialNoteId &&
      !initialCreate
    )
      setNoteId(null);
  }, [phone, ready, noteId, initialNoteId, initialCreate, setNoteId]);
  const open = (id: string) => {
    tapped.current = true;
    return openNote(id);
  };
  const note = state.notes.find((n) => n.id === noteId);
  const [revealed, setRevealed] = useState<string | null>(null);
  const contextVisible = context && (!note?.sensitive || revealed === note.id);
  useEffect(() => setRevealed(null), [note?.id]);
  useEffect(() => {
    preloadNoteEditor();
  }, []);
  useEffect(() => {
    const mobile = window.matchMedia("(max-width: 720px)"),
      tablet = window.matchMedia("(max-width: 1180px)");
    const collapse = () => {
      if (mobile.matches) setNavigation(false);
      if (tablet.matches) setContext(false);
    };
    collapse();
    mobile.addEventListener("change", collapse);
    tablet.addEventListener("change", collapse);
    return () => {
      mobile.removeEventListener("change", collapse);
      tablet.removeEventListener("change", collapse);
    };
  }, []);
  useEffect(() => {
    const timer = setTimeout(() => setSearch(query.trim()), 160);
    return () => clearTimeout(timer);
  }, [query]);
  useEffect(() => {
    if (liveNotes) void searchBrain(search);
  }, [search, liveNotes, searchBrain]);
  useEffect(() => {
    if (initialCreate) {
      if (ready && brainMode !== "unavailable" && !created.current) {
        created.current = true;
        void createNote({
          kind: "note",
          title: "",
          content: "",
          area: "cross",
          tags: [],
          date: "",
        });
      }
      return;
    }
    if (
      ready &&
      brainMode !== "unavailable" &&
      !note &&
      state.notes[0] &&
      !phone
    ) {
      let selected: string | null = null;
      try {
        selected = localStorage.getItem("yggdress.notes.active.v1");
      } catch {
        /* Navigation remains usable without local preferences. */
      }
      void openNote(
        initialNoteId ||
          state.notes.find((n) => n.id === selected)?.id ||
          state.notes[0].id,
      );
    }
  }, [
    ready,
    brainMode,
    note,
    state.notes,
    openNote,
    initialNoteId,
    initialCreate,
    createNote,
    phone,
  ]);
  useEffect(() => {
    if (note)
      try {
        localStorage.setItem("yggdress.notes.active.v1", note.id);
      } catch {
        /* Draft storage reports failures in the editor. */
      }
  }, [note?.id]);
  const visible = useMemo(
    () =>
      (liveNotes
        ? searchResultIds
          ? searchResultIds.flatMap((id) =>
              state.notes.filter((n) => n.id === id),
            )
          : state.notes
        : searchNotes(state.notes, search)
      ).filter(
        (n) => !shelf || ("shelfId" in n && n.shelfId === shelf),
      ) as BrainNote[],
    [state.notes, search, shelf, liveNotes, searchResultIds],
  );
  // Phase E: what the side chat may see. Ids and titles only; a sensitive note is an
  // id with a placeholder label (page-context.tsx safeRef), never its text.
  useRegisterPageContext("notes", () => ({
    surface: note ? "note-detail" : "notes",
    focus: note
      ? {
          kind: "doc",
          id: note.id,
          label: note.title || "Untitled",
          url: `/notes?note=${encodeURIComponent(note.id)}`,
          origin: "ambient",
          sensitivity: note.sensitive ? "restricted" : "normal",
        }
      : undefined,
    visible: visible.map((n) => ({
      kind: "doc" as const,
      id: n.id,
      label: n.title || "Untitled",
      origin: "ambient" as const,
      sensitivity: n.sensitive ? ("restricted" as const) : ("normal" as const),
    })),
    capabilities: ["note.read", "note.search"],
  }));
  const related = state.notes.filter((n) => note?.links.includes(n.id)),
    backlinks = state.notes.filter((n) => note?.backlinks.includes(n.id));
  const noteLink = (n: BrainNote) => {
    // Phase D: title only. State is an icon in the status slot; a search shows one
    // muted line of the match (never for a sensitive note), nothing else.
    const at = search
      ? n.content.toLowerCase().indexOf(search.toLowerCase())
      : -1;
    const snippet =
      !n.sensitive && at >= 0
        ? n.content.slice(Math.max(0, at - 20), Math.max(0, at - 20) + 95)
        : undefined;
    return (
      <ListRow
        key={n.id}
        title={n.title || "Untitled"}
        active={note?.id === n.id}
        onSelect={() => void open(n.id)}
        status={
          n.sensitive ? (
            <span role="img" aria-label="Sensitive note">
              <EyeOff className="size-3.5" />
            </span>
          ) : undefined
        }
      >
        {snippet}
      </ListRow>
    );
  };
  const reading = phone && !!note;
  return (
    <div
      className={`notes-application standard-page ${phone ? "notes-phone" : ""} ${reading ? "notes-phone-page" : "notes-phone-list"}`}
    >
      {reading && (
        <div className="notes-phone-bar">
          <button
            className="notes-phone-back"
            onClick={() => {
              setMenu(false);
              setContext(false);
              setNoteId(null);
            }}
          >
            <Icon name="ChevronLeft" size={18} />
            Notes
          </button>
          <span className="notes-phone-crumb">
            {shelves.find((s) => s.id === note.shelfId)?.name ||
              note.shelfId.replace(/^\d+-/, "").replaceAll("-", " ")}
          </span>
          <button
            className="icon-button"
            aria-label="Note menu"
            aria-expanded={menu}
            onClick={() => setMenu((m) => !m)}
          >
            <Icon name="Ellipsis" size={18} />
          </button>
          {menu && (
            <div className="notes-phone-menu" role="menu">
              <button
                role="menuitem"
                onClick={() => {
                  setMenu(false);
                  setContext((c) => !c);
                }}
              >
                <Icon name="Orbit" size={15} />
                {context ? "Hide what's around this note" : "Around this note"}
              </button>
              {liveNotes && (
                <button
                  role="menuitem"
                  disabled={!canUndo || undoBusy}
                  onClick={() => {
                    setMenu(false);
                    void undo();
                  }}
                >
                  <Icon name="Undo2" size={15} />
                  {undoBusy ? "Undoing…" : "Undo last saved change"}
                </button>
              )}
            </div>
          )}
        </div>
      )}
      {!reading && (
        <div className="notes-page-heading">
          <div>
            <h1>
              Notes<span>{state.notes.length}</span>
            </h1>
          </div>
          <div className="notes-layout-actions">
            {liveNotes && !phone && (
              <button
                className="button small-button"
                disabled={!canUndo || undoBusy}
                onClick={() => void undo()}
              >
                {undoBusy ? "Undoing…" : "Undo last saved change"}
              </button>
            )}
            {!phone && (
              <>
                <button
                  className={`icon-button ${navigation ? "is-active" : ""}`}
                  aria-label="Toggle notes navigation"
                  aria-expanded={navigation}
                  onClick={() => setNavigation((n) => !n)}
                >
                  <Icon name="PanelLeft" size={18} />
                </button>
                <button
                  className={`icon-button ${context ? "is-active" : ""}`}
                  aria-label="Toggle note context"
                  aria-expanded={context}
                  onClick={() => setContext((c) => !c)}
                >
                  <Icon name="PanelRight" size={18} />
                </button>
              </>
            )}
            <button
              className="button primary small-button"
              disabled={brainMode === "unavailable"}
              onClick={() => {
                if (liveNotes) {
                  tapped.current = true;
                  void createNote({
                    kind: "note",
                    title: "",
                    content: "",
                    area: "cross",
                    tags: [],
                    date: "",
                  });
                  return;
                }
                setCreating(true);
                setTitle("");
                setError("");
              }}
            >
              <Icon name="Plus" size={15} />
              New note
            </button>
          </div>
        </div>
      )}
      {markdownBlocked && (
        <div className="editor-error" role="alert">
          Writes are not live yet — the brain is still on markdown.
        </div>
      )}
      {liveNotes && brainError && brainMode !== "unavailable" && (
        <div className="editor-error" role="alert">
          {brainError}
        </div>
      )}
      {brainMode === "unavailable" ? (
        <Panel>
          <Empty
            title={ready ? "Notes are unavailable" : "Opening your notes"}
            detail={
              brainError ||
              (liveNotes
                ? "Loading notes from the Brain API…"
                : "Loading the authenticated synthetic Brain fixture…")
            }
            action={
              ready ? (
                <button className="button" onClick={() => void reloadBrain()}>
                  Retry Brain connection
                </button>
              ) : undefined
            }
          />
        </Panel>
      ) : (
        <div
          className={`notes-workbench ${(phone ? !note : navigation) ? "" : "navigation-collapsed"} ${contextVisible ? "" : "context-collapsed"}`}
        >
          {(phone ? !note : navigation) && (
            <aside
              className="notes-navigation panel"
              aria-label="Notes navigation"
            >
              <label className="notes-search">
                <Icon name="Search" size={15} />
                <input
                  aria-label={
                    liveNotes
                      ? "Search Brain notes"
                      : "Search development notes"
                  }
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Find a thought…"
                />
                <kbd>⌕</kbd>
              </label>
              <button
                className="all-notes-link"
                aria-pressed={shelf === null}
                onClick={() => setShelf(null)}
              >
                <Icon name="Layers" size={15} />
                All notes<span>{state.notes.length}</span>
              </button>
              <div className="notes-tree-heading">
                SHELVES & AREAS<span>{shelves.length}</span>
              </div>
              <div className="notes-shelf-tree">
                {search ? (
                  <div
                    className="note-search-results"
                    role="region"
                    aria-label="Note search results"
                  >
                    <p className="settings-footnote">
                      {visible.length} matches
                    </p>
                    {visible.length ? (
                      visible.map(noteLink)
                    ) : (
                      <Empty
                        title="No matching notes"
                        detail="Try a title or a word from your notes."
                      />
                    )}
                  </div>
                ) : (
                  shelves.map((s) => (
                    <details
                      className="notes-shelf"
                      key={s.id}
                      open={s.noteIds.length > 0 || s.id === note?.shelfId}
                    >
                      <summary>
                        <Icon name="ChevronRight" size={12} />
                        <span>{s.name}</span>
                        <small>
                          {state.notes.filter((n) => n.shelfId === s.id).length}
                        </small>
                      </summary>
                      <div>
                        {state.notes
                          .filter((n) => n.shelfId === s.id)
                          .map(noteLink)}
                        {!state.notes.some((n) => n.shelfId === s.id) && (
                          <p className="empty-shelf">
                            A little space for a new thought.
                          </p>
                        )}
                      </div>
                    </details>
                  ))
                )}
              </div>
              <div className="notes-navigation-footer">
                <Icon name="FlaskConical" size={13} />
                {liveNotes
                  ? "Areas supplied by Brain"
                  : "Public taxonomy fixture · no new hierarchy"}
              </div>
              <button
                className="notes-recovery-export"
                onClick={() => {
                  try {
                    const url = URL.createObjectURL(
                      new Blob(
                        [
                          recoveryBundle(
                            localStorage,
                            liveNotes ? BRAIN_DRAFT_PREFIX : undefined,
                          ),
                        ],
                        {
                          type: "application/json",
                        },
                      ),
                    );
                    const link = document.createElement("a");
                    link.href = url;
                    link.download = "yggdress-development-recovery.json";
                    link.click();
                    setTimeout(() => URL.revokeObjectURL(url), 1000);
                  } catch (e) {
                    setError(
                      e instanceof Error
                        ? e.message
                        : "Local recovery export unavailable.",
                    );
                  }
                }}
              >
                Export local recovery drafts
              </button>
              {error && !creating && (
                <p className="error" role="alert">
                  {error}
                </p>
              )}
            </aside>
          )}
          {!(phone && !note) && (
            <div className="notes-writing-panel panel">
              {note ? (
                note.sensitive && revealed !== note.id ? (
                  <Empty
                    title="Sensitive note"
                    detail="The contents stay hidden until you choose to read them."
                    action={
                      <button
                        className="button primary"
                        onClick={() => setRevealed(note.id)}
                      >
                        Show
                      </button>
                    }
                  />
                ) : (
                  <NoteEditor key={note.id} note={note} />
                )
              ) : (
                <Empty
                  title="Room for your next thought"
                  detail="Choose a note from the left or start with something new."
                  action={
                    <button
                      className="button"
                      onClick={() => {
                        tapped.current = true;
                        return liveNotes
                          ? void createNote({
                              kind: "note",
                              title: "",
                              content: "",
                              area: "cross",
                              tags: [],
                              date: "",
                            })
                          : setCreating(true);
                      }}
                    >
                      {liveNotes ? "Add note" : "Create a synthetic note"}
                    </button>
                  }
                />
              )}
            </div>
          )}
          {contextVisible && (
            <aside className="note-context panel" aria-label="Note context">
              <div className="note-context-heading">
                <Icon name="Orbit" size={17} />
                <h2>Around this note</h2>
              </div>
              <p className="settings-footnote">
                {liveNotes
                  ? "Relationships supplied by Brain."
                  : "Demonstration relationships supplied by the mock adapter."}
              </p>
              {liveNotes && note && (
                <NoteLinkedWork key={note.id} note={note} />
              )}
              <ContextLinks
                title="Connected notes"
                notes={related}
                open={open}
              />
              <ContextLinks title="Backlinks" notes={backlinks} open={open} />
              <div className="context-section">
                <h3>Note details</h3>
                <dl>
                  <dt>Source</dt>
                  <dd>{liveNotes ? "Brain API" : "Synthetic mock"}</dd>
                  <dt>Shelf</dt>
                  <dd>{note?.shelfId || "—"}</dd>
                  <dt>Primary area</dt>
                  <dd>{note?.area || "—"}</dd>
                  <dt>Last modified</dt>
                  <dd>{note?.updated ? relativeTime(note.updated) : "—"}</dd>
                  <dt>Relationships</dt>
                  <dd>
                    {liveNotes
                      ? "Read-only Brain relationships"
                      : "Read-only fixture"}
                  </dd>
                </dl>
                {note?.tags.length ? (
                  <div className="chips">
                    {note.tags.map((t, i) => (
                      <span className="tag" key={`${t}-${i}`}>
                        #{t}
                      </span>
                    ))}
                  </div>
                ) : null}
              </div>
            </aside>
          )}
        </div>
      )}
      <Modal
        open={creating}
        onOpenChange={(v) => {
          if (!busy) setCreating(v);
        }}
        title="Start a new thought"
        description="Create a synthetic note through the existing mock write adapter."
      >
        <form
          className="form-stack"
          onSubmit={async (e) => {
            e.preventDefault();
            setBusy(true);
            setError("");
            try {
              const ok = await createNote({
                kind: "note",
                title,
                content: "",
                tags: [],
                area: "cross",
                shelfId: destination,
                date: new Date().toISOString().slice(0, 10),
              });
              if (ok) {
                setCreating(false);
                setQuery("");
                setShelf(null);
              } else
                setError(
                  "Could not create the note. Your title is still here.",
                );
            } finally {
              setBusy(false);
            }
          }}
        >
          <label>
            Title
            <input
              autoFocus
              required
              maxLength={180}
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="What would you like to explore?"
            />
          </label>
          <label>
            Brain shelf
            <select
              aria-label="Brain shelf"
              value={destination}
              onChange={(e) => setDestination(e.target.value)}
            >
              {shelves.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </label>
          {error && (
            <p role="alert" className="error">
              {error}
            </p>
          )}
          <button className="button primary" disabled={busy || !title.trim()}>
            {busy ? "Creating…" : "Create note"}
          </button>
        </form>
      </Modal>
    </div>
  );
}
function ContextLinks({
  title,
  notes,
  open,
}: {
  title: string;
  notes: BrainNote[];
  open: (id: string) => Promise<boolean>;
}) {
  return (
    <div className="context-section">
      <h3>
        {title}
        <span>{notes.length}</span>
      </h3>
      {notes.length ? (
        notes.map((n) => (
          <button key={n.id} onClick={() => void open(n.id)}>
            <Icon name="FileText" size={14} />
            <span>{n.title}</span>
            <Icon name="ArrowUpRight" size={13} />
          </button>
        ))
      ) : (
        <p className="muted">No connections supplied yet.</p>
      )}
    </div>
  );
}
