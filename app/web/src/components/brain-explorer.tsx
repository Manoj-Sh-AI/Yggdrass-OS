"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import type { BrainNote } from "@/lib/brain-adapter";
import { recoveryBundle } from "@/lib/development-drafts";
import { BRAIN_DRAFT_PREFIX } from "@/lib/notes-api";
import { searchNotes } from "@/lib/repository";
import { useNotesApp } from "./notes-brain-provider";
import { NoteEditor, preloadNoteEditor } from "./note-editor-loader";
import { NoteLinkedWork } from "./note-linked-work";
import { Empty, Icon, Modal, Panel, relativeTime } from "./ui";

function Match({ text, query }: { text: string; query: string }) {
  const index = text.toLowerCase().indexOf(query.toLowerCase());
  return !query || index < 0 ? (
    <>{text}</>
  ) : (
    <>
      {text.slice(0, index)}
      <mark>{text.slice(index, index + query.length)}</mark>
      {text.slice(index + query.length)}
    </>
  );
}
export function BrainExplorer({
  initialNoteId,
  initialCreate = false,
}: { initialNoteId?: string; initialCreate?: boolean } = {}) {
  const {
    state,
    shelves,
    noteId,
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
  const note = state.notes.find((n) => n.id === noteId);
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
    if (ready && brainMode !== "unavailable" && !note && state.notes[0]) {
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
  const related = state.notes.filter((n) => note?.links.includes(n.id)),
    backlinks = state.notes.filter((n) => note?.backlinks.includes(n.id));
  const noteLink = (n: BrainNote) => (
    <button
      key={n.id}
      className={`note-tree-item ${note?.id === n.id ? "selected" : ""}`}
      aria-current={note?.id === n.id ? "page" : undefined}
      onClick={() => void openNote(n.id)}
    >
      <Icon name="FileText" size={14} />
      <span>
        <Match text={n.title} query={search} />
        {liveNotes && (
          <>
            <small>{n.description}</small>
            <small>{[n.area, ...n.also].join(" · ")}</small>
          </>
        )}
        {search && n.content.toLowerCase().includes(search.toLowerCase()) && (
          <small>
            <Match
              text={n.content.slice(
                Math.max(
                  0,
                  n.content.toLowerCase().indexOf(search.toLowerCase()) - 20,
                ),
                Math.max(
                  0,
                  n.content.toLowerCase().indexOf(search.toLowerCase()) - 20,
                ) + 95,
              )}
              query={search}
            />
          </small>
        )}
      </span>
    </button>
  );
  return (
    <div className="notes-application standard-page">
      <div className="notes-page-heading">
        <div>
          <h1>
            Notes<span>{state.notes.length}</span>
          </h1>
        </div>
        <div className="notes-layout-actions">
          {liveNotes && (
            <button
              className="button small-button"
              disabled={!canUndo || undoBusy}
              onClick={() => void undo()}
            >
              {undoBusy ? "Undoing…" : "Undo last saved change"}
            </button>
          )}
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
          <button
            className="button primary small-button"
            disabled={brainMode === "unavailable"}
            onClick={() => {
              if (liveNotes) {
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
          className={`notes-workbench ${navigation ? "" : "navigation-collapsed"} ${context ? "" : "context-collapsed"}`}
        >
          {navigation && (
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
                        <Icon
                          name={s.isArea ? "FolderKanban" : "Folder"}
                          size={14}
                        />
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
          <div className="notes-writing-panel panel">
            {note ? (
              <NoteEditor key={note.id} note={note} />
            ) : (
              <Empty
                title="Room for your next thought"
                detail="Choose a note from the left or start with something new."
                action={
                  <button
                    className="button"
                    onClick={() =>
                      liveNotes
                        ? void createNote({
                            kind: "note",
                            title: "",
                            content: "",
                            area: "cross",
                            tags: [],
                            date: "",
                          })
                        : setCreating(true)
                    }
                  >
                    {liveNotes ? "Add note" : "Create a synthetic note"}
                  </button>
                }
              />
            )}
          </div>
          {context && (
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
                open={openNote}
              />
              <ContextLinks
                title="Backlinks"
                notes={backlinks}
                open={openNote}
              />
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
