import { describe, expect, it, vi } from "vitest";
import type { BrainNote } from "../src/lib/brain-adapter";
import { NoteSaveSession, newNoteGap } from "../src/lib/note-save-session";
import { documentFrom } from "../src/lib/note-document";
const note: BrainNote = {
  id: "synthetic",
  slug: "synthetic",
  title: "Synthetic",
  description: "",
  content: "Original",
  area: "cross",
  also: [],
  tags: [],
  links: [],
  updated: "2026-11-08T12:00:00Z",
  version: "opaque-1",
  shelfId: "14-inbox",
  backlinks: [],
  source: "mock",
};
const snapshot = {
  title: note.title,
  description: "",
  tags: [],
  document: documentFrom(
    [{ type: "paragraph", content: "Original" }],
    "Original",
  ),
};
function setup() {
  const writes: BrainNote[] = [];
  const persist = vi.fn();
  const session = new NoteSaveSession({
    note,
    snapshot,
    changed: vi.fn(),
    persist,
    markdown: () => "Updated Markdown",
    write: async (n) => {
      writes.push(n);
      return { ...n, version: `opaque-${writes.length + 1}` };
    },
  });
  return { session, writes, persist };
}
describe("revision-aware development autosave", () => {
  it("acknowledges a recovered draft with the new upstream token", async () => {
    const persist = vi.fn();
    const recovery = {
      schema: 1 as const,
      noteId: note.id,
      baseVersion: note.version,
      ...snapshot,
      dirty: true,
      savedAt: note.updated,
    };
    const session = new NoteSaveSession({
      note,
      snapshot,
      recovery,
      changed: () => {},
      persist,
      markdown: () => "",
      write: async (n) => ({ ...n, version: "opaque-restored" }),
    });
    expect(await session.flush()).toBe(true);
    expect(persist.mock.calls.at(-1)?.[0].baseVersion).toBe("opaque-restored");
  });
  it("avoids redundant writes and uses server-supplied tokens", async () => {
    const { session, writes } = setup();
    expect(await session.flush()).toBe(true);
    expect(writes).toHaveLength(0);
    session.update({ ...snapshot, title: "Updated" });
    expect(await session.flush()).toBe(true);
    expect(writes).toHaveLength(1);
    expect(writes[0].version).toBe("opaque-1");
    expect(session.note.version).toBe("opaque-2");
    expect(session.state).toBe("saved");
    await session.flush();
    expect(writes).toHaveLength(1);
  });
  it("checkpoints the full document before requesting the mock write", async () => {
    const { session, persist, writes } = setup();
    session.update({ ...snapshot, title: "Durable" });
    await session.flush();
    expect(persist.mock.calls[0][0]).toMatchObject({
      dirty: true,
      baseVersion: "opaque-1",
      document: { blocks: snapshot.document.blocks },
    });
    expect(persist.mock.calls.at(-1)?.[0]).toMatchObject({
      dirty: false,
      baseVersion: "opaque-2",
    });
    expect(writes[0].document?.markdown).toBe("Updated Markdown");
  });
  it("preserves a failed local save and does not send a network write", async () => {
    let called = false;
    const session = new NoteSaveSession({
      note,
      snapshot,
      changed: () => {},
      persist: () => {
        throw new Error("Quota exceeded");
      },
      markdown: () => "",
      write: async (n) => {
        called = true;
        return n;
      },
    });
    session.update({ ...snapshot, title: "Keep this" });
    expect(await session.flush()).toBe(false);
    expect(called).toBe(false);
    expect(session.snapshot.title).toBe("Keep this");
    expect(session.state).toBe("failed");
  });
  it("stops on conflicts, keeps the draft, and never silently retries stale updates", async () => {
    const write = vi.fn(async () => {
      throw Object.assign(new Error("Reload latest note"), { status: 409 });
    });
    const session = new NoteSaveSession({
      note,
      snapshot,
      changed: () => {},
      persist: () => {},
      markdown: () => "",
      write,
    });
    session.update({ ...snapshot, title: "Local draft" });
    expect(await session.flush()).toBe(false);
    expect(session.state).toBe("conflict");
    expect(session.snapshot.title).toBe("Local draft");
    await session.flush();
    expect(write).toHaveBeenCalledTimes(1);
  });
  it("serializes saves when edits arrive during an in-flight write", async () => {
    let resolve!: (n: BrainNote) => void;
    const writes: BrainNote[] = [];
    const session = new NoteSaveSession({
      note,
      snapshot,
      changed: () => {},
      persist: () => {},
      markdown: () => "",
      write: (n) => {
        writes.push(n);
        return writes.length === 1
          ? new Promise((r) => {
              resolve = r;
            })
          : Promise.resolve({ ...n, version: "opaque-3" });
      },
    });
    session.update({ ...snapshot, title: "First" });
    const first = session.flush();
    session.update({ ...snapshot, title: "Second" });
    const second = session.flush();
    expect(writes).toHaveLength(1);
    resolve({ ...writes[0], version: "opaque-2" });
    await Promise.all([first, second]);
    expect(writes).toHaveLength(2);
    expect(writes[1].title).toBe("Second");
    expect(writes[1].version).toBe("opaque-2");
    expect(session.state).toBe("saved");
  });
  it("recovers unsaved changes and rejects a draft based on a different opaque token", () => {
    const recovery = {
      schema: 1 as const,
      noteId: note.id,
      baseVersion: "older-opaque",
      ...snapshot,
      title: "Recovered",
      dirty: true,
      savedAt: note.updated,
    };
    const session = new NoteSaveSession({
      note,
      snapshot,
      recovery,
      changed: () => {},
      persist: () => {},
      markdown: () => "",
      write: async (n) => n,
    });
    expect(session.snapshot.title).toBe("Recovered");
    expect(session.state).toBe("conflict");
  });
  it("retains empty-title edits and reports the validation error", async () => {
    const { session, writes } = setup();
    session.update({ ...snapshot, title: " " });
    expect(await session.flush()).toBe(false);
    expect(writes).toHaveLength(0);
    expect(session.error).toContain("title");
    expect(session.snapshot.title).toBe(" ");
  });
});

describe("newNoteGap", () => {
  it("names the missing title or description in plain words", () => {
    expect(newNoteGap({ title: " ", description: "x" })).toMatch(/title/);
    expect(newNoteGap({ title: "Pools", description: "  " })).toBe(
      "Add a one-line description under the title before saving.",
    );
    expect(newNoteGap({ title: "Pools", description: "Where I swim" })).toBe(
      "",
    );
  });
});
