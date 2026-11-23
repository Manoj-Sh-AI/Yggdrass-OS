"use client";
import dynamic from "next/dynamic";
// Start the same split bundle on clear intent without loading personal note data.
export function preloadNoteEditor() {
  void import("./note-editor").catch(() => {
    // Opening the editor retries through next/dynamic and keeps its normal error path.
  });
}
export const NoteEditor = dynamic(() => import("./note-editor"), {
  ssr: false,
  loading: () => (
    <div className="editor-loading writing-placeholder" role="status" aria-label="Opening your writing space">
      <span className="sr-only">Opening your writing space…</span>
      <div aria-hidden="true" className="writing-placeholder-title" />
      <div aria-hidden="true" className="writing-placeholder-line" />
      <div aria-hidden="true" className="writing-placeholder-line short" />
    </div>
  ),
});
