// @vitest-environment jsdom
import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import {
  chipLabel, type ContextRef, mergeContributions, PageContextProvider, safeRef, usePageContext,
  useRegisterPageContext, VISIBLE_CAP,
} from "@/features/side-chat/page-context";
import { clampWidth, isToggle } from "@/features/side-chat/side-chat";

afterEach(cleanup);

const note = (id: string, restricted = false): ContextRef => ({
  kind: "doc", id, label: `Invented note ${id}`, origin: "ambient",
  sensitivity: restricted ? "restricted" : "normal", fields: { words: 120 },
});

describe("page context safety", () => {
  it("a sensitive note is an id with a placeholder label, nothing else", () => {
    expect(safeRef(note("n1", true))).toEqual({
      kind: "doc", id: "n1", label: "Sensitive note", origin: "ambient", sensitivity: "restricted",
    });
    expect(safeRef(note("n2"))).toEqual(note("n2"));
  });
  it("a selection inside a sensitive note sends no text", () => {
    const page = mergeContributions("/notes", [
      { selection: { text: "invented secret", refs: [note("n1", true)] } },
    ]);
    expect(page.selection).toEqual({ text: "", refs: [safeRef(note("n1", true))] });
  });
  it("caps visible items and merges surfaces, focus and capabilities", () => {
    const page = mergeContributions("/notes", [
      { surface: "notes", visible: Array.from({ length: 40 }, (_, i) => note(`n${i}`)), capabilities: ["note.read"] },
      { surface: "note-detail", focus: note("n3", true), capabilities: ["note.read", "note.search"] },
    ], new Date("2026-11-22T10:00:00Z"));
    expect(page.visible).toHaveLength(VISIBLE_CAP);
    expect(page.surface).toBe("note-detail");
    expect(page.focus?.label).toBe("Sensitive note");
    expect(page.capabilities).toEqual(["note.read", "note.search"]);
    expect(page.capturedAt).toBe("2026-11-22T10:00:00.000Z");
  });
  it("the chip shows count and kind, never a dump", () => {
    const page = mergeContributions("/notes", [{ focus: note("a"), visible: [note("a"), note("b"), note("c")] }]);
    expect(chipLabel(page)).toBe("Note · Invented note a + 2 visible");
  });
  it("getters run only on collect, and unmounting unregisters", () => {
    let calls = 0;
    let collect: (() => ReturnType<NonNullable<ReturnType<typeof usePageContext>>["collect"]>) | null = null;
    function Screen() {
      useRegisterPageContext("s", () => {
        calls += 1;
        return { surface: "invented-screen" };
      });
      return null;
    }
    function Reader() {
      collect = usePageContext()!.collect;
      return null;
    }
    const { rerender } = render(<PageContextProvider><Screen /><Reader /></PageContextProvider>);
    expect(calls).toBe(0);
    expect(collect!().surface).toBe("invented-screen");
    expect(calls).toBe(1);
    rerender(<PageContextProvider><Reader /></PageContextProvider>);
    expect(collect!().surface).toBe("page");
  });
});

describe("side panel", () => {
  it("toggles on Mod+J only", () => {
    expect(isToggle({ key: "j", ctrlKey: true, metaKey: false, shiftKey: false, altKey: false })).toBe(true);
    expect(isToggle({ key: "J", ctrlKey: false, metaKey: true, shiftKey: false, altKey: false })).toBe(true);
    expect(isToggle({ key: "j", ctrlKey: true, metaKey: false, shiftKey: true, altKey: false })).toBe(false);
    expect(isToggle({ key: "k", ctrlKey: true, metaKey: false, shiftKey: false, altKey: false })).toBe(false);
  });
  it("keeps its width between 360 and 480px", () => {
    expect([clampWidth(200), clampWidth(400.4), clampWidth(900)]).toEqual([360, 400, 480]);
  });
});
