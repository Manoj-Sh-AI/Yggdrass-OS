import { describe, expect, it } from "vitest";
import {
  decodeDocument,
  documentFrom,
  encodeDocument,
  markdownWarnings,
  DOCUMENT_MARKER,
} from "../src/lib/note-document";
import {
  draftRepository,
  DRAFT_PREFIX,
  type DevelopmentDraft,
} from "../src/lib/development-drafts";

const document = documentFrom(
  [
    { type: "heading", props: { level: 2 }, content: "A synthetic heading" },
    {
      type: "paragraph",
      content: [
        {
          type: "text",
          text: "Keep every detail",
          styles: { underline: true, textColor: "blue" },
        },
      ],
    },
    {
      type: "table",
      content: {
        type: "tableContent",
        rows: [
          {
            cells: [
              {
                type: "tableCell",
                content: [{ type: "text", text: "Cell", styles: {} }],
                props: {
                  backgroundColor: "default",
                  textColor: "default",
                  textAlignment: "left",
                  colspan: 1,
                  rowspan: 1,
                },
              },
            ],
          },
        ],
      },
    },
  ],
  "## A synthetic heading\nKeep every detail",
  "🌱",
);
function memory() {
  const map = new Map<string, string>();
  return {
    map,
    getItem: (k: string) => map.get(k) ?? null,
    setItem: (k: string, v: string) => {
      map.set(k, v);
    },
    removeItem: (k: string) => {
      map.delete(k);
    },
  };
}
const draft: DevelopmentDraft = {
  schema: 1,
  noteId: "synthetic",
  baseVersion: "opaque-upstream",
  title: "Synthetic",
  description: "",
  tags: [],
  document,
  dirty: true,
  savedAt: "2026-11-08T12:00:00Z",
};
describe("lossless development documents", () => {
  it("retains blocks, rich styles, table cells and icon without depending on Markdown fidelity", () => {
    expect(decodeDocument(encodeDocument(document))).toEqual(document);
  });
  it("keeps existing plain Markdown readable", () => {
    expect(decodeDocument("## Ordinary Markdown\nA note")).toBeNull();
  });
  it("rejects a newer format or malformed document without producing an empty replacement", () => {
    expect(() => decodeDocument("<!-- yggdress:blocknote:v99 -->\n{}")).toThrow(
      "unsupported",
    );
    expect(() => decodeDocument(DOCUMENT_MARKER + "{}")).toThrow("unreadable");
  });
  it("reports lossy table, underline and color conversion", () => {
    const warnings = markdownWarnings(document.blocks);
    expect(warnings.some((w) => w.includes("tables"))).toBe(true);
    expect(warnings.some((w) => w.includes("Underline"))).toBe(true);
  });
  it("does not warn for supported plain headings, lists, checklists, quotes, code and links", () => {
    expect(
      markdownWarnings([
        { type: "heading", props: { level: 1 }, content: "Heading" },
        {
          type: "bulletListItem",
          content: "Item",
          children: [{ type: "numberedListItem", content: "Nested" }],
        },
        { type: "checkListItem", props: { checked: true }, content: "Done" },
        { type: "quote", content: "A quote" },
        {
          type: "codeBlock",
          props: { language: "javascript" },
          content: "const x = 1;",
        },
        {
          type: "paragraph",
          content: [
            {
              type: "link",
              href: "https://example.com",
              content: [
                {
                  type: "text",
                  text: "Example",
                  styles: {
                    bold: true,
                    italic: true,
                    strike: true,
                    code: true,
                  },
                },
              ],
            },
          ],
        },
      ]),
    ).toEqual([]);
  });
  it("flags an unknown advanced block rather than silently promising a faithful export", () => {
    expect(markdownWarnings([{ type: "futureWidget" } as never])).not.toEqual(
      [],
    );
  });
});
describe("isolated browser development drafts", () => {
  it("persists one latest draft across repository instances", () => {
    const storage = memory();
    draftRepository(storage).write(draft);
    expect(draftRepository(storage).read(draft.noteId)).toEqual(draft);
    draftRepository(storage).write({ ...draft, title: "Latest only" });
    expect(storage.map.size).toBe(1);
    expect(draftRepository(storage).read(draft.noteId)?.title).toBe(
      "Latest only",
    );
  });
  it("preserves unrecognized storage instead of replacing it with demo data", () => {
    const storage = memory();
    storage.setItem(DRAFT_PREFIX + draft.noteId, '{"schema":999}');
    expect(() => draftRepository(storage).read(draft.noteId)).toThrow(
      "preserved",
    );
    expect(storage.getItem(DRAFT_PREFIX + draft.noteId)).toBe('{"schema":999}');
  });
  it("surfaces quota errors", () => {
    expect(() =>
      draftRepository({
        ...memory(),
        setItem: () => {
          throw new Error("Quota exceeded");
        },
      }).write(draft),
    ).toThrow("Quota");
  });
  it("removes the local copy only through the confirmed write and restores it if that write fails", async () => {
    const storage = memory(),
      repo = draftRepository(storage);
    repo.write(draft);
    await expect(
      repo.deleteWithConfirmation(draft.noteId, async () => {
        throw new Error("Service unavailable");
      }),
    ).rejects.toThrow("unavailable");
    expect(repo.read(draft.noteId)).toEqual(draft);
    await repo.deleteWithConfirmation(draft.noteId, async () => true);
    expect(repo.read(draft.noteId)).toBeNull();
  });
  it("does not invoke deletion when local cleanup fails", async () => {
    let invoked = false;
    await expect(
      draftRepository({
        ...memory(),
        removeItem: () => {
          throw new Error("Storage denied");
        },
      }).deleteWithConfirmation(draft.noteId, async () => {
        invoked = true;
      }),
    ).rejects.toThrow("denied");
    expect(invoked).toBe(false);
  });
});
