import { applicationApi } from "./api";
import type { BrainNote } from "./brain-adapter";

export const BRAIN_DRAFT_PREFIX = "yggdress.notes.brain.v1:";
export type LiveNote = BrainNote & {
  rawBody: string;
  bodyPrefix: string;
  fetchToken: string;
  newNote?: boolean;
};
export type NoteResult = {
  note: LiveNote;
  canUndo: boolean;
  links_added?: unknown[];
  reviewWarning?: string;
};
export type SavePreview = {
  token: string;
  slug: string;
  changes: {
    kind: string;
    old: string;
    new: string;
    links_added: unknown[];
    links_removed: unknown[];
    permanent: string;
    note: string;
  }[];
};
const post = <T>(path: string, body = {}) =>
  applicationApi<T>(`notes/${path}`, {
    method: "POST",
    body: JSON.stringify(body),
  });
/** A Brain folder (an area). `own`: one of Manoj's, numbered from 20, removable. */
export type BrainFolder = {
  code: string;
  value: string;
  name: string;
  notes: number;
  own: boolean;
};
export type FolderPreview = {
  delete: string;
  moves: { slug: string; title: string }[];
  hidden?: number;
  message?: string;
};
export const notesApi = {
  folders: () =>
    applicationApi<{ folders: BrainFolder[] }>("notes/folders").then(
      (r) => r.folders,
    ),
  addFolder: (name: string) => post<{ folder: string }>("folders", { name }),
  /** Removing a folder moves its notes to cross; no note is deleted. */
  folderPreview: (value: string) =>
    post<FolderPreview>(`folders/${encodeURIComponent(value)}/delete-preview`),
  deleteFolder: (value: string) =>
    post<FolderPreview>(`folders/${encodeURIComponent(value)}/delete`),
  search: (q = "") =>
    applicationApi<{ notes: LiveNote[]; canUndo: boolean }>(
      `notes/search?q=${encodeURIComponent(q)}`,
    ),
  get: (slug: string) =>
    applicationApi<NoteResult>(`notes/items/${encodeURIComponent(slug)}`),
  preview: (note: LiveNote) =>
    post<SavePreview>(`items/${encodeURIComponent(note.slug)}/preview`, {
      fetchToken: note.fetchToken,
      body: note.bodyPrefix + note.content,
    }),
  confirm: (token: string) => post<NoteResult>(`previews/${token}/confirm`),
  cancel: (token: string) => post(`previews/${token}/cancel`),
  create: (note: LiveNote) =>
    post<NoteResult>("create", { slug: note.slug, text: newNoteBody(note) }),
  undo: () =>
    post<{ message: string; canUndo: boolean; reviewWarning?: string }>("undo"),
  /** Deleting is permanent (Manoj, 2026-11-28): preview, then delete. */
  deletePreview: (slug: string) =>
    post<{
      title: string;
      permanent: string;
      linked_from: { slug: string; title: string }[];
    }>(`items/${encodeURIComponent(slug)}/delete-preview`),
  delete: (slug: string, version: number) =>
    post<{ deleted: string; canUndo: boolean }>(
      `items/${encodeURIComponent(slug)}/delete`,
      { version },
    ),
};
export function blankNote(area = "cross", shelfId = area): LiveNote {
  const slug = `note-${crypto.randomUUID()}`;
  return {
    id: slug,
    slug,
    title: "",
    description: "",
    content: "## Summary\n\n## Facts\n\n## Links\n",
    area,
    also: [],
    tags: [],
    links: [],
    backlinks: [],
    shelfId,
    updated: "",
    source: "lia",
    version: "new",
    rawBody: "",
    bodyPrefix: "",
    fetchToken: "",
    newNote: true,
  };
}
export function newNoteBody(note: LiveNote) {
  const day = new Date().toISOString().slice(0, 10);
  const quoted = (value: string) => JSON.stringify(value);
  const content = note.description
    ? note.content.replace(
        /(## Summary\s*\n)\s*(?=## )/,
        (_, heading: string) => `${heading}\n${note.description}\n\n`,
      )
    : note.content;
  return `---\nid: ${quoted(note.slug)}\nslug: ${quoted(note.slug)}\nname: ${quoted(note.title.trim())}\ntype: concept\narea: ${quoted(note.area)}\ndescription: ${quoted(note.description)}\naliases: []\ncreated: ${day}\nupdated: ${day}\n---\n${content}\n`;
}
export function linkText(value: unknown): string {
  if (typeof value === "string") return value;
  if (value && typeof value === "object") {
    const v = value as Record<string, unknown>;
    return String(v.to || v.target || v.target_slug || JSON.stringify(value));
  }
  return String(value);
}
