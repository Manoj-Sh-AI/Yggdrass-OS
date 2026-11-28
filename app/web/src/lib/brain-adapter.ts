import { applicationApi } from "./api";
import type { Note } from "./types";
import {
  decodeDocument,
  encodeDocument,
  type NoteDocument,
} from "./note-document";
export type BrainNote = Note & {
  sensitive?: boolean;
  version: string;
  shelfId: string;
  backlinks: string[];
  source: "mock" | "lia";
  document?: NoteDocument;
  documentError?: string;
};
export type BrainShelf = {
  id: string;
  name: string;
  isArea: boolean;
  noteIds: string[];
  /** One of Manoj's own folders (numbered from 20): it can be removed. */
  own?: boolean;
};
export type BrainEnvelope = {
  mode: "mock" | "lia";
  integrationBlocked: boolean;
};
export type DeletePreview = {
  token: string;
  noteId: string;
  version: string;
  title: string;
  content: string;
};
export interface BrainAdapter {
  tree(): Promise<BrainEnvelope & { shelves: BrainShelf[] }>;
  notes(): Promise<BrainEnvelope & { notes: BrainNote[] }>;
  note(id: string): Promise<BrainEnvelope & { note: BrainNote }>;
  create(input: {
    title: string;
    description: string;
    content: string;
    tags: string[];
    shelfId: string;
  }): Promise<BrainEnvelope & { note: BrainNote }>;
  replace(note: BrainNote): Promise<BrainEnvelope & { note: BrainNote }>;
  previewDelete(
    note: BrainNote,
  ): Promise<BrainEnvelope & { preview: DeletePreview }>;
  confirmDelete(
    preview: DeletePreview,
  ): Promise<BrainEnvelope & { deleted: boolean }>;
}
const route = (id: string) => `brain/notes/${encodeURIComponent(id)}`;
function decodeNote(note: BrainNote): BrainNote {
  try {
    const document = decodeDocument(note.content);
    return document ? { ...note, content: document.markdown, document } : note;
  } catch (error) {
    return {
      ...note,
      documentError:
        error instanceof Error
          ? error.message
          : "The structured document is unreadable.",
    };
  }
}
async function readNote(path: string, init?: RequestInit) {
  const result = await applicationApi<BrainEnvelope & { note: BrainNote }>(
    path,
    init,
  );
  return { ...result, note: decodeNote(result.note) };
}
export const brainAdapter: BrainAdapter = {
  tree: () => applicationApi("brain/tree"),
  notes: async () => {
    const result = await applicationApi<BrainEnvelope & { notes: BrainNote[] }>(
      "brain/notes",
    );
    return { ...result, notes: result.notes.map(decodeNote) };
  },
  note: (id) => readNote(route(id)),
  create: (input) =>
    readNote("brain/notes", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  replace: (note) => {
    if (note.document && note.source !== "mock")
      return Promise.reject(
        new Error(
          "Structured content requires Claude’s approved Brain contract.",
        ),
      );
    return readNote(route(note.id), {
      method: "PUT",
      body: JSON.stringify({
        version: note.version,
        title: note.title,
        description: note.description,
        content: note.document ? encodeDocument(note.document) : note.content,
        tags: note.tags.map((t) => t.trim()).filter(Boolean),
      }),
    });
  },
  previewDelete: async (note) => {
    const result = await applicationApi<
      BrainEnvelope & { preview: DeletePreview }
    >(`${route(note.id)}/delete-preview`, {
      method: "POST",
      body: JSON.stringify({ version: note.version }),
    });
    const document = decodeDocument(result.preview.content);
    return document
      ? {
          ...result,
          preview: { ...result.preview, content: document.markdown },
        }
      : result;
  },
  confirmDelete: (preview) =>
    applicationApi(`${route(preview.noteId)}/delete-confirm`, {
      method: "POST",
      body: JSON.stringify({
        version: preview.version,
        token: preview.token,
        confirmed: true,
      }),
    }),
};

/**
 * The name a group header shows for an area id. The Brain sends ids such as
 * "03-health" or a bare code such as "01"; a bare code is shown as "Area 01" until the
 * Brain supplies area names (Phase D: the header carries the area once, rows never).
 */
export function areaLabel(id: string): string {
  const name = id.replace(/^\d+-/, "").replaceAll("-", " ").trim();
  if (!name || /^\d+$/.test(name)) return `Area ${id}`;
  return name.charAt(0).toUpperCase() + name.slice(1);
}
