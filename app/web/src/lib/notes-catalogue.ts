import type { LiveNote } from "./notes-api";

/** Search selects matches; only an unfiltered fetch replaces the catalogue. */
export function reconcileNoteCatalogue(
  previous: LiveNote[],
  incoming: LiveNote[],
  query: string,
  selected: string | null,
): LiveNote[] {
  const existing = new Map(previous.map((note) => [note.id, note]));
  const received = incoming.map((note) => {
    const cached = existing.get(note.id);
    // Preserve the fetched editing baseline until the explicit note refresh.
    return cached?.fetchToken ? cached : note;
  });
  if (query) {
    const merged = new Map(previous.map((note) => [note.id, note]));
    for (const note of received) merged.set(note.id, note);
    return [...merged.values()];
  }
  const identifiers = new Set(incoming.map((note) => note.id));
  return [
    ...received,
    ...previous.filter(
      (note) =>
        !identifiers.has(note.id) && (note.newNote || note.id === selected),
    ),
  ];
}
