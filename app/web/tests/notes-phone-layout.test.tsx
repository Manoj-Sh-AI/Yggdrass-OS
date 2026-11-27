// @vitest-environment jsdom
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// Notes on a phone follow Notion's mobile layout: the list and the page are two screens,
// nothing opens by itself, and the page has a slim bar with back, area and a menu.

const notes = [
  {
    id: "invented-a",
    title: "Invented swimming plan",
    content: "",
    shelfId: "03-health",
    area: "health",
    tags: [],
    links: [],
    backlinks: [],
    sensitive: false,
    updated: "",
  },
];
const undo = vi.fn();
let selected: string | null = null;
let preselected: string | null = null;
let setSelected: (id: string | null) => void = () => {};
vi.mock("@/components/notes-brain-provider", () => ({
  useNotesApp: () => ({
    state: { notes },
    shelves: [{ id: "03-health", name: "Health", noteIds: ["invented-a"] }],
    noteId: selected,
    setNoteId: (id: string | null) => setSelected(id),
    openNote: async (id: string) => {
      setSelected(id);
      return true;
    },
    ready: true,
    brainMode: "lia",
    brainError: "",
    reloadBrain: vi.fn(),
    createNote: vi.fn(),
    liveNotes: true,
    markdownBlocked: false,
    canUndo: true,
    undoBusy: false,
    undo,
    searchBrain: vi.fn(async () => {}),
    searchResultIds: null,
  }),
}));
vi.mock("@/components/note-editor-loader", () => ({
  NoteEditor: ({ note }: { note: { title: string } }) => (
    <section aria-label="Note editor">{note.title}</section>
  ),
  preloadNoteEditor: () => {},
}));
vi.mock("@/components/note-linked-work", () => ({
  NoteLinkedWork: () => null,
}));
vi.mock("@/features/side-chat/page-context", () => ({
  useRegisterPageContext: () => {},
}));

function phoneScreen(matches: boolean) {
  window.matchMedia = ((query: string) => ({
    matches:
      query.includes("720px") || query.includes("1180px") ? matches : false,
    media: query,
    addEventListener: () => {},
    removeEventListener: () => {},
  })) as unknown as typeof window.matchMedia;
}

async function renderExplorer() {
  const { BrainExplorer } = await import("@/components/brain-explorer");
  function Harness() {
    const [id, setId] = useState<string | null>(preselected);
    selected = id;
    setSelected = setId;
    return <BrainExplorer />;
  }
  return render(<Harness />);
}

describe("Notes on a phone", () => {
  beforeEach(() => phoneScreen(true));
  afterEach(() => {
    cleanup();
    selected = null;
    vi.clearAllMocks();
  });

  it("starts on the list and never opens a note by itself", async () => {
    await renderExplorer();
    expect(screen.getByText("Invented swimming plan")).toBeTruthy();
    expect(screen.queryByLabelText("Note editor")).toBeNull();
    expect(screen.queryByText("Undo last saved change")).toBeNull();
  });

  it("keeps a note the app selected on load (a recovered draft) in the list", async () => {
    preselected = "invented-a";
    await renderExplorer();
    preselected = null;
    expect(screen.queryByLabelText("Note editor")).toBeNull();
    expect(screen.getByText("Invented swimming plan")).toBeTruthy();
  });

  it("opens a tapped note as its own page, and back returns to the list", async () => {
    await renderExplorer();
    await act(async () => {
      fireEvent.click(screen.getByText("Invented swimming plan"));
    });
    expect(screen.getByLabelText("Note editor")).toBeTruthy();
    expect(screen.getByText("Health")).toBeTruthy(); // the area's name in the slim bar
    expect(screen.queryByRole("heading", { name: /Notes/ })).toBeNull();
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /Notes/ }));
    });
    expect(screen.queryByLabelText("Note editor")).toBeNull();
    expect(screen.getByText("Invented swimming plan")).toBeTruthy();
  });

  it("keeps undo and the note's context in the page menu", async () => {
    await renderExplorer();
    await act(async () => {
      fireEvent.click(screen.getByText("Invented swimming plan"));
    });
    fireEvent.click(screen.getByLabelText("Note menu"));
    fireEvent.click(
      screen.getByRole("menuitem", { name: "Undo last saved change" }),
    );
    expect(undo).toHaveBeenCalledOnce();
    fireEvent.click(screen.getByLabelText("Note menu"));
    fireEvent.click(screen.getByRole("menuitem", { name: "Around this note" }));
    expect(screen.getByLabelText("Note context")).toBeTruthy();
  });
});

describe("Notes on a desktop", () => {
  beforeEach(() => phoneScreen(false));
  afterEach(() => cleanup());
  it("still opens the first note beside the list", async () => {
    await renderExplorer();
    expect(await screen.findByLabelText("Note editor")).toBeTruthy();
    expect(screen.queryByLabelText("Note menu")).toBeNull();
  });
});
