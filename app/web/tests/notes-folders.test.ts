import { afterEach, expect, it, vi } from "vitest";
import { blankNote, newNoteBody, notesApi } from "../src/lib/notes-api";
import { folderShelves } from "../src/components/notes-brain-provider";

afterEach(() => vi.unstubAllGlobals());

const folders = [
  { code: "04", value: "04-learning", name: "learning", notes: 1, own: false },
  { code: "09", value: "cross", name: "cross", notes: 0, own: false },
  { code: "20", value: "20-swimming", name: "swimming", notes: 0, own: true },
];

it("lists every folder, empty ones too, in the Brain's order, and marks only own ones", () => {
  const shelves = folderShelves(folders, [
    { id: "a", shelfId: "04-learning" },
    { id: "draft", shelfId: "07-home-admin" },
  ]);
  expect(shelves.map((s) => s.id)).toEqual([
    "04-learning",
    "cross",
    "20-swimming",
    "07-home-admin", // a note's area the folder list lacks still shows
  ]);
  expect(shelves.map((s) => s.own)).toEqual([false, false, true, false]);
  expect(shelves[2]).toMatchObject({ name: "Swimming", noteIds: [] });
  expect(shelves[0].noteIds).toEqual(["a"]);
});

it("a new note made in a folder names that folder as its area", () => {
  const note = blankNote("20-swimming");
  expect(note.shelfId).toBe("20-swimming");
  expect(newNoteBody(note)).toContain('area: "20-swimming"');
  expect(blankNote().area).toBe("cross");
});

it("calls the folder routes through the same-origin backend", async () => {
  const fetch = vi.fn().mockImplementation(
    async () =>
      new Response(JSON.stringify({ folders, folder: "20-x", moves: [] }), {
        status: 200,
      }),
  );
  vi.stubGlobal("fetch", fetch);
  expect(await notesApi.folders()).toEqual(folders);
  await notesApi.addFolder("Swimming");
  await notesApi.folderPreview("20-swimming");
  await notesApi.deleteFolder("20-swimming");
  const calls = fetch.mock.calls.filter((c) =>
    String(c[0]).includes("/notes/"),
  );
  expect(calls.map((c) => [c[0], c[1].method ?? "GET"])).toEqual([
    ["/api/backend/notes/folders", "GET"],
    ["/api/backend/notes/folders", "POST"],
    ["/api/backend/notes/folders/20-swimming/delete-preview", "POST"],
    ["/api/backend/notes/folders/20-swimming/delete", "POST"],
  ]);
  expect(JSON.parse(calls[1][1].body)).toEqual({ name: "Swimming" });
});
