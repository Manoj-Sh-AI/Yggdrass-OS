import type { NoteDocument } from "./note-document";
export const DRAFT_PREFIX = "yggdress.notes.development.v1:";
export type DevelopmentDraft = {
  schema: 1;
  noteId: string;
  baseVersion: string;
  title: string;
  description: string;
  tags: string[];
  document: NoteDocument;
  dirty: boolean;
  savedAt: string;
};
export interface DraftStorage {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}
export function recoveryBundle(
  storage: DraftStorage & { length: number; key(index: number): string | null },
  prefix = DRAFT_PREFIX,
): string {
  const drafts = [];
  for (let i = 0; i < storage.length; i++) {
    const key = storage.key(i);
    if (key?.startsWith(prefix))
      drafts.push({
        noteId: key.slice(prefix.length),
        raw: storage.getItem(key),
      });
  }
  return JSON.stringify(
    { format: "yggdress.development-recovery", version: 1, drafts },
    null,
    2,
  );
}
export function draftRepository(storage: DraftStorage, prefix = DRAFT_PREFIX) {
  return {
    read(id: string): DevelopmentDraft | null {
      const raw = storage.getItem(prefix + id);
      if (!raw) return null;
      const d = JSON.parse(raw);
      if (
        d.schema !== 1 ||
        d.noteId !== id ||
        typeof d.baseVersion !== "string" ||
        typeof d.title !== "string" ||
        typeof d.description !== "string" ||
        !Array.isArray(d.tags) ||
        !d.tags.every((t: unknown) => typeof t === "string") ||
        typeof d.dirty !== "boolean" ||
        d.document?.version !== 1 ||
        d.document?.format !== "yggdress.blocknote" ||
        !Array.isArray(d.document.blocks)
      )
        throw new Error(
          "The local development draft is unreadable. It has been preserved; export or repair it before saving.",
        );
      return d;
    },
    write(draft: DevelopmentDraft) {
      storage.setItem(prefix + draft.noteId, JSON.stringify(draft));
    },
    async deleteWithConfirmation(id: string, write: () => Promise<unknown>) {
      // A failed local removal must not leave a retained rich copy after mock deletion.
      const raw = storage.getItem(prefix + id);
      storage.removeItem(prefix + id);
      try {
        await write();
      } catch (error) {
        if (raw) storage.setItem(prefix + id, raw);
        throw error;
      }
    },
  };
}
