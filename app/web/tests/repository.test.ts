import { describe, expect, it } from "vitest";
import { seed } from "../src/lib/data";
import {
  browserRepository,
  capture,
  demoAnswer,
  saveNote,
  searchNotes,
  STORAGE_KEY,
} from "../src/lib/repository";
import type { CaptureInput } from "../src/lib/types";
const input: CaptureInput = {
  kind: "note",
  title: "A connected thought",
  content: "Mindful systems and creative habits",
  area: "projects",
  tags: ["thinking"],
  date: "2026-11-08",
};
const createStorage = () => {
  const data = new Map<string, string>();
  return {
    getItem: (key: string) => data.get(key) ?? null,
    setItem: (key: string, value: string) => {
      data.set(key, value);
    },
  };
};
describe("browser repository and connected note workflows", () => {
  it("seeds fictional data on an empty browser", async () => {
    const state = await browserRepository(createStorage()).load();
    expect(state.notes.length).toBeGreaterThan(0);
    expect(state.preferences.name).toBe("Alex");
  });
  it("captures, links, searches, and reloads notes", async () => {
    const repo = browserRepository(createStorage());
    let state = capture(seed(), input, "test-note");
    state = saveNote(state, {
      ...state.notes[0],
      links: ["thesis", "thesis", "missing", "test-note"],
      also: ["learning"],
      tags: ["thinking", "reflection"],
    });
    await repo.save(state);
    const reloaded = await repo.load();
    expect(
      searchNotes(reloaded.notes, "mindful reflection", "learning"),
    ).toHaveLength(1);
    expect(reloaded.notes[0].links).toEqual(["thesis"]);
    expect(reloaded.activities[0].noteId).toBe("test-note");
  });
  it("rejects blank captures without mutating the original state", () => {
    const state = seed();
    expect(() => capture(state, { ...input, title: "  " })).toThrow("title");
    expect(state.notes).toHaveLength(8);
  });
  it("creates tasks rather than notes for task captures", () => {
    const original = seed(),
      state = capture(original, { ...input, kind: "task" }, "task");
    expect(state.notes).toHaveLength(original.notes.length);
    expect(state.tasks.at(-1)?.done).toBe(false);
    expect(state.tasks.at(-1)?.date).toBe(input.date);
    expect(state.activities[0].kind).toBe("task");
  });
  it("captures only file metadata", () => {
    const state = capture(
      seed(),
      { ...input, kind: "file", filename: "reading.pdf" },
      "file",
    );
    expect(state.notes[0].filename).toBe("reading.pdf");
    expect(state.activities[0].kind).toBe("file");
  });
  it("does not silently overwrite malformed storage", async () => {
    const storage = createStorage();
    storage.setItem(STORAGE_KEY, '{"version":50}');
    await expect(browserRepository(storage).load()).rejects.toThrow(
      "could not be read",
    );
    expect(storage.getItem(STORAGE_KEY)).toBe('{"version":50}');
  });
  it("reports quota failures and leaves previously saved data intact", async () => {
    const storage = createStorage(),
      repo = browserRepository(storage);
    await repo.save(seed());
    const before = storage.getItem(STORAGE_KEY);
    const broken = browserRepository({
      ...storage,
      setItem: () => {
        throw new Error("Quota exceeded");
      },
    });
    await expect(broken.save(capture(seed(), input))).rejects.toThrow("Quota");
    expect(storage.getItem(STORAGE_KEY)).toBe(before);
  });
  it("reset restores a clean fictional workspace", async () => {
    const repo = browserRepository(createStorage());
    await repo.save(capture(seed(), input));
    await repo.reset();
    expect((await repo.load()).notes).toHaveLength(8);
  });
  it("finds all query terms in content and tags, case insensitively", () => {
    const state = capture(seed(), input, "new");
    expect(searchNotes(state.notes, "THINKING mindful")[0].id).toBe("new");
    expect(searchNotes(state.notes, "mindful unavailable")).toHaveLength(0);
  });
  it("preserves backlinks when editing another note", () => {
    const original = seed(),
      state = saveNote(original, { ...original.notes[0], links: ["thesis"] });
    expect(
      state.notes.filter((n) => n.links.includes("thesis")).map((n) => n.id),
    ).toContain("credit-report");
  });
  it("labels generated answers as demo when archived and cites existing notes", () => {
    const state = seed(),
      answer = demoAnswer(state, "German");
    expect(answer.sources[0].id).toBe("german-a2");
    expect(answer.text).toContain("[1]");
    expect(demoAnswer(state, "not in this dataset").text).toContain(
      "couldn’t find",
    );
  });
  it("handles 10,000 notes with area and tag filters", () => {
    const original = seed().notes[0];
    const notes = Array.from({ length: 10000 }, (_, i) => ({
      ...original,
      id: `note-${i}`,
      title: `Research ${i}`,
      area: i % 2 ? "learning" : "work",
      tags: ["research"],
    }));
    const start = performance.now();
    const found = searchNotes(notes, "research 9999", "learning", "research");
    expect(found).toHaveLength(1);
    expect(found[0].id).toBe("note-9999");
    expect(performance.now() - start).toBeLessThan(1500);
  });
});
