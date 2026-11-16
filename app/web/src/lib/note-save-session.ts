import type { BrainNote } from "./brain-adapter";
import type { DevelopmentDraft } from "./development-drafts";
import type { NoteDocument } from "./note-document";
export type NoteSnapshot = {
  title: string;
  description: string;
  tags: string[];
  document: NoteDocument;
};
export type SaveState = "unsaved" | "saving" | "saved" | "failed" | "conflict";
type Options = {
  note: BrainNote;
  snapshot: NoteSnapshot;
  recovery?: DevelopmentDraft | null;
  write: (note: BrainNote) => Promise<BrainNote>;
  persist: (draft: DevelopmentDraft) => void;
  markdown: (document: NoteDocument) => string;
  changed: () => void;
};
/** One current development draft; opaque conflict versions always come from the mock port. */
export class NoteSaveSession {
  snapshot: NoteSnapshot;
  note: BrainNote;
  state: SaveState;
  error = "";
  revision = 0;
  private synced = 0;
  private durable = 0;
  private active: Promise<boolean> | null = null;
  constructor(private options: Options) {
    this.note = options.note;
    this.snapshot = options.snapshot;
    this.state = "saved";
    if (options.recovery) {
      const d = options.recovery;
      this.snapshot = {
        title: d.title,
        description: d.description,
        tags: d.tags,
        document: d.document,
      };
      this.revision = d.dirty ? 1 : 0;
      if (d.baseVersion !== this.note.version) {
        this.note = { ...this.note, version: d.baseVersion };
        this.state = "conflict";
        this.error =
          "This note changed elsewhere. Reload the latest note or export your local draft.";
      } else if (d.dirty) this.state = "unsaved";
    }
  }
  get dirty() {
    return this.revision !== this.synced || this.state === "conflict";
  }
  update(snapshot: NoteSnapshot) {
    this.snapshot = snapshot;
    this.revision++;
    if (this.state !== "conflict") {
      this.state = "unsaved";
      this.error = "";
    }
    this.options.changed();
  }
  checkpoint() {
    this.options.persist({
      schema: 1,
      noteId: this.note.id,
      baseVersion: this.note.version,
      ...this.snapshot,
      dirty: this.dirty,
      savedAt: new Date().toISOString(),
    });
    this.durable = this.revision;
  }
  flush(): Promise<boolean> {
    if (this.active)
      return this.active.then((ok) => (ok ? this.flush() : false));
    if (this.state === "conflict") {
      try {
        this.checkpoint();
      } catch {
        /* Preserve the in-memory draft too. */
      }
      return Promise.resolve(false);
    }
    if (
      !this.dirty &&
      this.durable === this.revision &&
      this.state !== "failed"
    )
      return Promise.resolve(true);
    const operation = this.save();
    this.active = operation;
    void operation.finally(() => {
      this.active = null;
    });
    return operation;
  }
  private async save() {
    this.state = "saving";
    this.error = "";
    this.options.changed();
    try {
      if (!this.snapshot.title.trim())
        throw new Error("A note needs a title. Your changes are still here.");
      if (this.snapshot.title.length > 180)
        throw new Error("Use a title of 180 characters or fewer.");
      const revision = this.revision;
      if (this.dirty) {
        const snapshot = {
          ...this.snapshot,
          document: {
            ...this.snapshot.document,
            markdown: this.options.markdown(this.snapshot.document),
          },
        };
        this.snapshot = snapshot;
        this.checkpoint();
        const updated = await this.options.write({
          ...this.note,
          ...snapshot,
          content: snapshot.document.markdown,
        });
        this.note = updated;
        this.synced = revision;
      }
      this.checkpoint();
      this.state = this.dirty ? "unsaved" : "saved";
      this.options.changed();
      return true;
    } catch (error) {
      this.state =
        (error as { status?: number; code?: string })?.status === 409 &&
        (error as { code?: string }).code !== "brain_markdown"
          ? "conflict"
          : "failed";
      this.error =
        error instanceof Error
          ? error.message
          : "Could not save. Your draft has been preserved.";
      this.options.changed();
      return false;
    }
  }
}
