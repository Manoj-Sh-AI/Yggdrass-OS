import { BrainExplorer } from "@/components/brain-explorer";
import { NotesBrainProvider } from "@/components/notes-brain-provider";
export default async function Notes({
  searchParams,
}: {
  searchParams: Promise<{ note?: string; new?: string }>;
}) {
  const { note, new: newNote } = await searchParams;
  const initialNoteId =
    typeof note === "string" && /^[a-zA-Z0-9_-]{1,200}$/.test(note)
      ? note
      : undefined;
  return (
    <NotesBrainProvider
      key={newNote === "1" ? "new-note" : initialNoteId || "notes"}
      initialNoteId={initialNoteId}
    >
      <BrainExplorer
        initialNoteId={initialNoteId}
        initialCreate={newNote === "1"}
      />
    </NotesBrainProvider>
  );
}
