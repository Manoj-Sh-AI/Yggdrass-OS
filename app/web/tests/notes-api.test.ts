import { afterEach, expect, it, vi } from "vitest";
import { blankNote, newNoteBody, notesApi } from "../src/lib/notes-api";
import { ApiError } from "../src/lib/api";
import { draftRepository, DRAFT_PREFIX } from "../src/lib/development-drafts";
import { BRAIN_DRAFT_PREFIX } from "../src/lib/notes-api";

afterEach(() => vi.unstubAllGlobals());
it("creates a blank draft without calling any API, serializes the full note safely", () => {
  const fetch = vi.fn();
  vi.stubGlobal("fetch", fetch);
  const note = blankNote();
  expect(fetch).not.toHaveBeenCalled();
  expect(note.newNote).toBe(true);
  note.title = 'A title: "quoted"\nnot: metadata';
  note.content = "## Facts\n- An entered fact\n";
  const text = newNoteBody(note);
  expect(text).toContain(
    'name: "A title: \\"quoted\\"\\nnot: metadata"'.replaceAll('\\\\"', '\\"'),
  );
  expect(text).toContain(note.content);
  expect(text).toContain(`slug: "${note.slug}"`);
});
it("uses the same-origin backend with no Basic credential in browser requests", async () => {
  const fetch = vi
    .fn()
    .mockResolvedValue(
      new Response(JSON.stringify({ notes: [], canUndo: false }), {
        status: 200,
      }),
    );
  vi.stubGlobal("fetch", fetch);
  await notesApi.search("words & spaces");
  expect(fetch.mock.calls[0][0]).toBe(
    "/api/backend/notes/search?q=words%20%26%20spaces",
  );
  expect(fetch.mock.calls[0][1].headers).not.toHaveProperty("Authorization");
  expect(fetch.mock.calls[0][1].credentials).toBe("same-origin");
});
it("retains structured 409 Markdown feedback for the editor and banner", async () => {
  vi.stubGlobal(
    "fetch",
    vi
      .fn()
      .mockResolvedValue(
        new Response(
          JSON.stringify({
            detail: "Writes are not live yet — the brain is still on markdown.",
            code: "brain_markdown",
            completed: 0,
          }),
          { status: 409 },
        ),
      ),
  );
  await expect(notesApi.search()).rejects.toMatchObject({
    status: 409,
    code: "brain_markdown",
    extra: { completed: 0 },
  });
  expect(new ApiError(400, "cannot undo").message).toBe("cannot undo");
});
it("keeps live recovery drafts separate from synthetic mock drafts", () => {
  const map = new Map<string, string>();
  const storage = {
    getItem: (k: string) => map.get(k) || null,
    setItem: (k: string, v: string) => {
      map.set(k, v);
    },
    removeItem: (k: string) => {
      map.delete(k);
    },
  };
  const draft = {
    schema: 1 as const,
    noteId: "same-slug",
    baseVersion: "7",
    title: "Draft",
    description: "",
    tags: [],
    document: {
      format: "yggdress.blocknote" as const,
      version: 1 as const,
      blocks: [],
      markdown: "",
      icon: "",
    },
    dirty: true,
    savedAt: "2030-01-01",
  };
  draftRepository(storage, BRAIN_DRAFT_PREFIX).write(draft);
  expect(draftRepository(storage).read("same-slug")).toBeNull();
  expect(
    draftRepository(storage, BRAIN_DRAFT_PREFIX).read("same-slug"),
  ).toEqual(draft);
  expect(map.has(DRAFT_PREFIX + "same-slug")).toBe(false);
});
