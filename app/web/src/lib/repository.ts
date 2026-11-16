import { seed, brainAreaForApp } from "./data";
import type { CaptureInput, DemoState, Note } from "./types";
import { ROUTINE_STORAGE_KEY } from "./routine-repository";
import { createRoutineStore } from "./routines";
export const STORAGE_KEY = "yggdras.demo.v1";
export interface Repository {
  load(): Promise<DemoState>;
  save(state: DemoState): Promise<void>;
  reset(): Promise<DemoState>;
}
export interface StorageLike {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
}
export function isState(value: unknown): value is DemoState {
  if (!value || typeof value !== "object") return false;
  const s = value as DemoState;
  const strings = (v: unknown): v is string[] =>
    Array.isArray(v) && v.every((x) => typeof x === "string");
  const record = (v: unknown): v is Record<string, unknown> =>
    !!v && typeof v === "object";
  const textFields = (v: unknown, keys: string[]) =>
    record(v) && keys.every((key) => typeof v[key] === "string");
  const p = s.preferences,
    place = p?.place;
  if (!p || !place || typeof place.timezone !== "string") return false;
  try {
    new Intl.DateTimeFormat("en", { timeZone: place.timezone });
  } catch {
    return false;
  }
  return (
    s.version === 1 &&
    Array.isArray(s.notes) &&
    s.notes.every(
      (n) =>
        record(n) &&
        textFields(n, [
          "id",
          "slug",
          "title",
          "description",
          "content",
          "area",
          "updated",
        ]) &&
        strings(n.tags) &&
        strings(n.links) &&
        strings(n.also),
    ) &&
    Array.isArray(s.tasks) &&
    s.tasks.every(
      (t) =>
        record(t) &&
        typeof t.id === "string" &&
        typeof t.title === "string" &&
        typeof t.area === "string" &&
        typeof t.date === "string" &&
        typeof t.done === "boolean",
    ) &&
    Array.isArray(s.events) &&
    s.events.every((e) =>
      textFields(e, [
        "id",
        "title",
        "description",
        "area",
        "date",
        "time",
        "duration",
        "location",
        "noteId",
      ]),
    ) &&
    Array.isArray(s.activities) &&
    s.activities.every(
      (a) =>
        record(a) &&
        typeof a.id === "string" &&
        typeof a.title === "string" &&
        typeof a.date === "string" &&
        ["note", "task", "idea", "file"].includes(a.kind as string),
    ) &&
    Array.isArray(s.goals) &&
    s.goals.every(
      (g) =>
        record(g) &&
        typeof g.title === "string" &&
        typeof g.area === "string" &&
        typeof g.progress === "number",
    ) &&
    Array.isArray(s.cards) &&
    s.cards.every((c) => textFields(c, ["id", "area", "front", "back"])) &&
    typeof p.name === "string" &&
    typeof p.notifications === "boolean" &&
    typeof p.reducedMotion === "boolean" &&
    (p.reducedTransparency === undefined ||
      typeof p.reducedTransparency === "boolean") &&
    typeof p.locationPrompted === "boolean" &&
    ["auto", "spring", "summer", "autumn", "winter"].includes(p.season) &&
    ["auto", "sunrise", "afternoon", "night"].includes(p.phase) &&
    ["auto", "clear", "rainy"].includes(p.sky) &&
    typeof place.name === "string" &&
    Number.isFinite(place.latitude) &&
    Math.abs(place.latitude) <= 90 &&
    Number.isFinite(place.longitude) &&
    Math.abs(place.longitude) <= 180
  );
}
export function browserRepository(storage: StorageLike): Repository {
  return {
    async load() {
      const raw = storage.getItem(STORAGE_KEY);
      if (!raw) return seed();
      try {
        const value: unknown = JSON.parse(raw);
        if (isState(value)) return value;
      } catch {
        /* Recover without deleting the original storage. */
      }
      throw new Error(
        "The saved demo could not be read. Reset the demo in Settings to start fresh.",
      );
    },
    async save(state) {
      storage.setItem(STORAGE_KEY, JSON.stringify(state));
    },
    async reset() {
      const state = seed();
      storage.setItem(
        ROUTINE_STORAGE_KEY,
        JSON.stringify(
          createRoutineStore(new Date(), state.preferences.place.timezone),
        ),
      );
      storage.setItem(STORAGE_KEY, JSON.stringify(state));
      return state;
    },
  };
}
export function capture(
  state: DemoState,
  input: CaptureInput,
  id = crypto.randomUUID(),
  now = new Date().toISOString(),
): DemoState {
  const title = input.title.trim();
  if (!title) throw new Error("Give your capture a title.");
  const next = {
    ...state,
    activities: [
      {
        id: `activity-${id}`,
        title: `${input.kind === "task" ? "Added task" : input.kind === "idea" ? "Captured idea" : input.kind === "file" ? "Added file" : "Created note"}: ${title}`,
        kind: input.kind,
        date: now,
        noteId: input.kind === "task" ? undefined : id,
      },
      ...state.activities,
    ],
  };
  if (input.kind === "task")
    return {
      ...next,
      tasks: [
        ...state.tasks,
        {
          id,
          title,
          description: input.content,
          area: input.area,
          done: false,
          date: input.date,
        },
      ],
    };
  const note: Note = {
    id,
    slug: `${
      title
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, "-")
        .replace(/^-|-$/g, "") || "note"
    }-${id.slice(0, 8)}`,
    title,
    description: input.content.trim().slice(0, 130),
    content: input.content.trim(),
    area: input.area,
    also: [],
    tags: input.tags,
    links: [],
    updated: now,
    ...(input.filename ? { filename: input.filename } : {}),
  };
  return { ...next, notes: [note, ...state.notes] };
}
export function searchNotes(
  notes: Note[],
  query: string,
  area?: string,
  tag?: string,
): Note[] {
  const terms = query.toLocaleLowerCase().trim().split(/\s+/).filter(Boolean);
  return notes.filter(
    (n) =>
      (!area ||
        n.area === area ||
        n.also.includes(area) ||
        n.area === brainAreaForApp[area] ||
        ("shelfId" in n && n.shelfId === brainAreaForApp[area])) &&
      (!tag || n.tags.includes(tag)) &&
      terms.every((t) =>
        `${n.title} ${n.description} ${n.content} ${n.tags.join(" ")}`
          .toLocaleLowerCase()
          .includes(t),
      ),
  );
}
export function saveNote(state: DemoState, note: Note): DemoState {
  if (!note.title.trim()) throw new Error("A note needs a title.");
  const ids = new Set(state.notes.map((n) => n.id));
  const updated = {
    ...note,
    title: note.title.trim(),
    tags: [...new Set(note.tags.map((t) => t.trim()).filter(Boolean))],
    also: [...new Set(note.also)].filter((id) => id !== note.area),
    links: [...new Set(note.links)].filter(
      (id) => ids.has(id) && id !== note.id,
    ),
    updated: new Date().toISOString(),
  };
  return {
    ...state,
    notes: state.notes.map((n) => (n.id === note.id ? updated : n)),
    activities: [
      {
        id: crypto.randomUUID(),
        title: `Updated ${updated.title}`,
        kind: "note",
        date: updated.updated,
        noteId: note.id,
      },
      ...state.activities,
    ],
  };
}
export function demoAnswer(state: DemoState, query: string) {
  const matches = searchNotes(state.notes, query).slice(0, 3);
  const cited = matches.length ? matches : state.notes.slice(0, 3);
  return {
    text: matches.length
      ? `Here’s what your demo notes say about “${query}”.\n\n${cited.map((n, i) => `${n.description || n.title} [${i + 1}]`).join("\n\n")}\n\nA good next step: open one of these notes and choose a small action for today.`
      : `I couldn’t find a direct match for “${query}” in these demo notes. You could capture it as a new idea, or explore the related notes below.`,
    sources: cited,
  };
}
