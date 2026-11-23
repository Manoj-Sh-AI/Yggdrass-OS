"use client";
import { useRef } from "react";
import { usePathname } from "next/navigation";
import { useVirtualizer } from "@tanstack/react-virtual";
import type { Note } from "@/lib/types";
import { useApp } from "./provider";
import { AreaBadge, Empty, Icon, Modal, relativeTime } from "./ui";
import { NoteEditor, preloadNoteEditor } from "./note-editor-loader";
export function NoteList({ notes }: { notes: Note[] }) {
  const { openNote } = useApp(),
    parent = useRef<HTMLDivElement>(null);
  const virtual = useVirtualizer({
    count: notes.length,
    getScrollElement: () => parent.current,
    estimateSize: () => 88,
    overscan: 6,
  });
  if (!notes.length)
    return (
      <Empty
        title="A little room for a new thought"
        detail="Capture a note or try another filter."
      />
    );
  return (
    <div className="notes-scroll" ref={parent} role="list" aria-label="Notes">
      <div
        style={{
          height: virtual.getTotalSize(),
          position: "relative",
          width: "100%",
        }}
      >
        {virtual.getVirtualItems().map((row) => {
          const n = notes[row.index];
          return (
            <button
              role="listitem"
              key={n.id}
              className="note-row"
              onClick={() => openNote(n.id)}
              onPointerEnter={preloadNoteEditor}
              onFocus={preloadNoteEditor}
              style={{
                position: "absolute",
                top: 0,
                left: 0,
                width: "100%",
                height: row.size,
                transform: `translateY(${row.start}px)`,
              }}
            >
              <AreaBadge area={n.area} small />
              <span className="note-preview">
                <strong>{n.title}</strong>
                <span>
                  {n.description ||
                    n.content.slice(0, 100) ||
                    "A fresh thought, ready to grow."}
                </span>
                <span className="note-tags">
                  {n.tags.map((t) => `#${t}`).join("  ")}
                </span>
              </span>
              <span className="note-updated">{relativeTime(n.updated)}</span>
              <Icon name="ChevronRight" size={15} />
            </button>
          );
        })}
      </div>
    </div>
  );
}
export function NoteDrawer() {
  const { state, noteId, closeNote } = useApp();
  const path = usePathname();
  const note = state.notes.find((n) => n.id === noteId);
  if (path === "/notes") return null;
  return (
    <Modal
      sheet
      open={!!note}
      onOpenChange={(v) => {
        if (!v) void closeNote();
      }}
      title={note?.title || "Note"}
      description="Synthetic mock note · real Lia integration blocked · version checked on every write"
    >
      {note && <NoteEditor key={note.id} note={note} compact />}
    </Modal>
  );
}
