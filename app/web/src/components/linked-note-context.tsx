"use client";
import Link from "next/link";
import { useState } from "react";
import type { WorkContext } from "@/lib/workspace-connections";
import { useWorkspaceContext } from "./use-workspace-context";
import { usePlanning } from "./planning-provider";

export function LinkedNoteContext({
  kind,
  id,
  version,
}: {
  kind: "task" | "event" | "date_item" | "availability";
  id: string;
  version: number;
}) {
  const [open, setOpen] = useState(false);
  const { select } = usePlanning();
  const { data, error, loading, enabled, refresh } =
    useWorkspaceContext<WorkContext>(
      kind === "task" || kind === "event"
        ? `${kind}s/${id}`
        : `calendar-context/${kind}/${id}`,
      open,
      String(version),
    );
  return (
    <details
      className="linked-work-disclosure"
      open={open}
      onToggle={(event) => setOpen(event.currentTarget.open)}
    >
      <summary>Linked context</summary>
      {loading && !data && <p role="status">Loading linked context…</p>}
      {!enabled && (
        <p className="muted">Linked work is not enabled on this server yet.</p>
      )}
      {error && (
        <div role="alert">
          <p>{error}</p>
          <button className="button small-button" onClick={refresh}>
            Retry linked context
          </button>
        </div>
      )}
      {data && (
        <>
          {!data.notes.length &&
            !(data.tasks?.length || data.events?.length) && (
              <p className="muted">
                No linked context. You can attach this work from a saved note.
              </p>
            )}
          <ul className="linked-work-list">
            {data.notes.map((note) => (
              <li key={`${note.id}:${note.kind}`}>
                <Link
                  href={`/notes?note=${encodeURIComponent(note.external_id)}`}
                  onClick={() => select(null)}
                >
                  {note.observed_title || note.external_id}
                </Link>
                <small>
                  {note.kind === "source"
                    ? "Source note"
                    : note.kind === "result"
                      ? "Result note"
                      : "Context note"}
                </small>
              </li>
            ))}
            {data.tasks?.map((task) => (
              <li key={task.id}>
                <button className="text-link" onClick={() => select(task.id)}>
                  {task.title}
                </button>
                <small>{task.state.replaceAll("_", " ")}</small>
              </li>
            ))}
            {data.events?.map((event) => (
              <li key={event.id}>
                <Link href="/calendar" onClick={() => select(null)}>
                  {event.title}
                </Link>
                <small>
                  {event.cancelled ? "Removed event" : "Calendar event"}
                </small>
              </li>
            ))}
          </ul>
          {Object.values(data.truncated).some(Boolean) && (
            <p className="muted">
              Showing the first 40 connections. Other connections are preserved.
            </p>
          )}
        </>
      )}
    </details>
  );
}
