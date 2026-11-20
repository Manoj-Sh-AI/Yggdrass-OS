import { expect, it } from "vitest";
import { blankNote } from "../src/lib/notes-api";
import { reconcileNoteCatalogue } from "../src/lib/notes-catalogue";

const note = (id: string) => ({ ...blankNote(), id, slug: id, newNote: false });

it("keeps the complete catalogue and backlink targets when a search matches one note", () => {
  const first = { ...note("first"), links: ["second"] };
  const second = note("second");
  const result = reconcileNoteCatalogue(
    [first, second],
    [first],
    "first",
    null,
  );
  expect(result.map((n) => n.id)).toEqual(["first", "second"]);
  expect(result[0].links).toEqual(["second"]);
  expect(reconcileNoteCatalogue(result, [], "no matches", null)).toEqual(
    result,
  );
});

it("removes deleted catalogue entries on unfiltered refresh while preserving an open draft", () => {
  const draft = { ...note("draft"), newNote: true };
  const result = reconcileNoteCatalogue(
    [note("removed"), note("kept"), draft],
    [note("kept")],
    "",
    "draft",
  );
  expect(result.map((n) => n.id)).toEqual(["kept", "draft"]);
});

it("preserves the fetched editing baseline while adding newly discovered search results", () => {
  const editing = {
    ...note("editing"),
    content: "original baseline",
    fetchToken: "fixture-fetch",
  };
  const result = reconcileNoteCatalogue(
    [editing],
    [{ ...editing, content: "external edit" }, note("new")],
    "match",
    "editing",
  );
  expect(result[0]).toBe(editing);
  expect(result[1].id).toBe("new");
});
