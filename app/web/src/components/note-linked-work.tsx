"use client";
import { useRef, useState } from "react";
import type { BrainNote } from "@/lib/brain-adapter";
import { workspaceRetry } from "@/lib/workspace-retry";
import {
  connectionsApi,
  connectionsChanged,
  type LinkedEvent,
  type NoteWork,
  type Relation,
  type WorkKind,
} from "@/lib/workspace-connections";
import { useWorkspaceContext } from "./use-workspace-context";
import { usePlanning } from "./planning-provider";
import { TaskForm, TimeForm } from "./planning-ui";
import { Modal } from "./ui";
import { CalendarDateForm, AvailabilityForm } from "./calendar-date-form";
import type { CalendarDateItem, AvailabilityWindow } from "@/lib/planning";

export function NoteLinkedWork({ note }: { note: BrainNote }) {
  const planning = usePlanning();
  const saved = note.version !== "new";
  const { data, error, loading, enabled, refresh } =
    useWorkspaceContext<NoteWork>(
      `notes/${encodeURIComponent(note.slug)}`,
      saved,
      note.version,
    );
  const [creating, setCreating] = useState<{
    kind: WorkKind;
    revision: string;
  } | null>(null);
  const [editingEvent, setEditingEvent] = useState<LinkedEvent | null>(null);
  const [editingDate, setEditingDate] = useState<CalendarDateItem | null>(null);
  const [editingAvailability, setEditingAvailability] =
    useState<AvailabilityWindow | null>(null);
  const [busy, setBusy] = useState(false),
    [failure, setFailure] = useState(""),
    [notice, setNotice] = useState("");
  const [kind, setKind] = useState<"task" | "event">("task"),
    [query, setQuery] = useState(""),
    [target, setTarget] = useState("");
  const retries = useRef(new Map<string, string>()),
    locked = useRef(false);
  async function mutate(
    identity: string,
    action: (key: string) => Promise<unknown>,
  ) {
    if (locked.current)
      throw new Error("Please wait for this change to finish.");
    locked.current = true;
    setBusy(true);
    setFailure("");
    setNotice("");
    try {
      const retry = await workspaceRetry(
        note.slug + ":" + identity,
        retries.current.get(identity),
      );
      retries.current.set(identity, retry.key);
      const result = await action(retry.key);
      retry.complete();
      retries.current.delete(identity);
      connectionsChanged();
      refresh();
      setNotice("Linked work saved.");
      return result;
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Could not save linked work.";
      setFailure(message);
      throw error;
    } finally {
      locked.current = false;
      setBusy(false);
    }
  }
  const create = async (draft: Record<string, unknown>) => {
    if (!creating) throw new Error("Choose which work to create.");
    return (await mutate(JSON.stringify({ creating, draft }), (key) =>
      connectionsApi.create(
        key,
        creating.kind,
        note.slug,
        creating.revision,
        draft,
      ),
    )) as { id?: string; version: number };
  };
  const attach = async () => {
    const record = (
      kind === "task" ? planning.data?.tasks : planning.data?.events
    )?.find((item) => item.id === target);
    if (!record) {
      setFailure("Choose an existing task or event.");
      return;
    }
    await mutate(
      JSON.stringify({ kind, target, version: record.version }),
      (key) =>
        connectionsApi.link(key, kind, target, record.version, note.slug),
    );
    setTarget("");
    setQuery("");
  };
  const unlink = (
    kind: WorkKind,
    id: string,
    version: number,
    relation: Relation,
  ) =>
    mutate(
      JSON.stringify({ kind, id, version, relation, remove: true }),
      (key) =>
        connectionsApi.link(key, kind, id, version, note.slug, relation, true),
    );
  const openTask = async (id: string) => {
    try {
      await planning.refresh();
      planning.select(id);
    } catch (error) {
      setFailure(
        error instanceof Error ? error.message : "Could not open this task.",
      );
    }
  };
  const choices =
    (kind === "task" ? planning.data?.tasks : planning.data?.events)
      ?.filter(
        (item) =>
          item.title.toLowerCase().includes(query.toLowerCase()) &&
          !(kind === "event" && "cancelled" in item && item.cancelled),
      )
      .slice(0, 20) || [];
  return (
    <section className="context-section linked-work" aria-label="Linked work">
      <h3>Linked work</h3>
      {!saved ? (
        <p className="muted">Save this note before linking work.</p>
      ) : (
        <>
          {loading && !data && <p role="status">Loading linked work…</p>}
          {!enabled && (
            <p className="muted">
              Linked work is not enabled on this server yet.
            </p>
          )}
          {error && (
            <div role="alert">
              <p>{error}</p>
              <button className="button small-button" onClick={refresh}>
                Retry linked work
              </button>
            </div>
          )}
          {data && (
            <>
              <p className="settings-footnote">
                Context from the saved note. Note edits do not update work
                automatically yet.
              </p>
              <ul className="linked-work-list">
                {data.tasks.map((task) => (
                  <li key={`${task.id}:${task.kind}`}>
                    <button
                      className="text-link"
                      onClick={() => void openTask(task.id)}
                    >
                      {task.title}
                    </button>
                    <small>
                      {task.state.replaceAll("_", " ")}
                      {task.due_date ? ` · due ${task.due_date}` : ""}
                    </small>
                    {task.kind === "source" &&
                      task.source_revision &&
                      task.source_revision !== note.version && (
                        <small>Source note changed — review this task.</small>
                      )}
                    <button
                      className="text-link linked-work-unlink"
                      disabled={busy}
                      aria-label={`Unlink ${task.title} from this note`}
                      onClick={() =>
                        void unlink(
                          "task",
                          task.id,
                          task.version,
                          task.kind,
                        ).catch(() => {})
                      }
                    >
                      Unlink
                    </button>
                  </li>
                ))}
                {data.events.map((event) => (
                  <li key={`${event.id}:${event.kind}`}>
                    <button
                      className="text-link"
                      onClick={() => setEditingEvent(event)}
                    >
                      {event.title}
                    </button>
                    <small>
                      {event.cancelled
                        ? "Removed event"
                        : new Date(event.starts_at).toLocaleString("en", {
                            timeZone: event.timezone,
                            dateStyle: "medium",
                            timeStyle: "short",
                          })}
                    </small>
                    {event.kind === "source" &&
                      event.source_revision &&
                      event.source_revision !== note.version && (
                        <small>Source note changed — review this event.</small>
                      )}
                    <button
                      className="text-link linked-work-unlink"
                      disabled={busy}
                      aria-label={`Unlink ${event.title} from this note`}
                      onClick={() =>
                        void unlink(
                          "event",
                          event.id,
                          event.version,
                          event.kind,
                        ).catch(() => {})
                      }
                    >
                      Unlink
                    </button>
                  </li>
                ))}
              </ul>
              <ul className="linked-work-list">
                {[
                  ...(data.date_items || []).map((item) => ({
                    ...item,
                    workKind: "date_item" as const,
                  })),
                  ...(data.availability || []).map((item) => ({
                    ...item,
                    workKind: "availability" as const,
                  })),
                ].map((item) => (
                  <li key={`${item.workKind}:${item.id}:${item.relation}`}>
                    <button
                      className="text-link"
                      onClick={() =>
                        item.workKind === "date_item"
                          ? setEditingDate(item)
                          : setEditingAvailability(item)
                      }
                    >
                      {item.title}
                    </button>
                    <small>
                      {item.cancelled
                        ? "Removed calendar item"
                        : item.workKind === "date_item"
                          ? `${item.starts_on} · calendar dates`
                          : "Available time"}
                    </small>
                    {item.source_revision &&
                      item.source_revision !== note.version && (
                        <small>Source note changed — review this item.</small>
                      )}
                    <button
                      className="text-link linked-work-unlink"
                      disabled={busy}
                      onClick={() =>
                        void unlink(
                          item.workKind,
                          item.id,
                          item.version,
                          item.relation,
                        ).catch(() => {})
                      }
                      aria-label={`Unlink ${item.title} from this note`}
                    >
                      Unlink
                    </button>
                  </li>
                ))}
              </ul>
              {!data.tasks.length &&
                !data.events.length &&
                !data.date_items?.length &&
                !data.availability?.length && (
                  <p className="muted">No linked work yet.</p>
                )}
              {(data.truncated.tasks || data.truncated.events) && (
                <p className="muted">
                  Showing the first 40 of each kind. Other connections are
                  preserved.
                </p>
              )}
              <div className="linked-work-actions">
                <button
                  className="button small-button"
                  disabled={busy}
                  onClick={() =>
                    setCreating({ kind: "task", revision: note.version })
                  }
                >
                  Create task
                </button>
                <button
                  className="button small-button"
                  disabled={busy}
                  onClick={() =>
                    setCreating({ kind: "event", revision: note.version })
                  }
                >
                  Create event
                </button>
              </div>
              <details>
                <summary>Other calendar items</summary>
                <div className="linked-work-actions">
                  <button
                    className="button small-button"
                    disabled={busy}
                    onClick={() =>
                      setCreating({ kind: "date_item", revision: note.version })
                    }
                  >
                    Create date item
                  </button>
                  <button
                    className="button small-button"
                    disabled={busy}
                    onClick={() =>
                      setCreating({
                        kind: "availability",
                        revision: note.version,
                      })
                    }
                  >
                    Create availability
                  </button>
                </div>
              </details>
              <details>
                <summary>Link existing work</summary>
                <div className="form-stack">
                  <label>
                    Work type
                    <select
                      value={kind}
                      onChange={(event) => {
                        setKind(event.target.value as "task" | "event");
                        setTarget("");
                      }}
                    >
                      <option value="task">Task</option>
                      <option value="event">Event</option>
                    </select>
                  </label>
                  <label>
                    Find work
                    <input
                      value={query}
                      onChange={(event) => {
                        setQuery(event.target.value);
                        setTarget("");
                      }}
                    />
                  </label>
                  <label>
                    Existing work
                    <select
                      value={target}
                      onChange={(event) => setTarget(event.target.value)}
                    >
                      <option value="">Choose work</option>
                      {choices.map((item) => (
                        <option key={item.id} value={item.id}>
                          {item.title}
                        </option>
                      ))}
                    </select>
                  </label>
                  <small>
                    Showing up to 20 matches from the loaded planning range.
                  </small>
                  <button
                    className="button small-button"
                    disabled={busy || !target}
                    onClick={() => void attach().catch(() => {})}
                  >
                    Link to note
                  </button>
                </div>
              </details>
            </>
          )}
          {failure && (
            <div role="alert" className="error">
              <p>{failure}</p>
              <button
                className="button small-button"
                disabled={busy}
                onClick={refresh}
              >
                Refresh linked work
              </button>
            </div>
          )}
          {notice && <p role="status">{notice}</p>}
        </>
      )}
      <Modal
        open={!!creating}
        onOpenChange={(open) => {
          if (!open && !busy) setCreating(null);
        }}
        preventDismiss={busy}
        title={
          creating?.kind === "date_item"
            ? "Create date item from note"
            : creating?.kind === "availability"
              ? "Create availability from note"
              : creating?.kind === "event"
                ? "Create event from note"
                : "Create task from note"
        }
        description={`Source: ${note.title || note.slug}. Uses the saved note revision.`}
      >
        {creating?.kind === "task" && (
          <TaskForm createWith={create} onSaved={() => setCreating(null)} />
        )}
        {creating?.kind === "event" && (
          <TimeForm createWith={create} onSaved={() => setCreating(null)} />
        )}
        {creating?.kind === "date_item" && (
          <CalendarDateForm
            createWith={create}
            onSaved={() => setCreating(null)}
          />
        )}
        {creating?.kind === "availability" && (
          <AvailabilityForm
            createWith={create}
            onSaved={() => setCreating(null)}
          />
        )}
      </Modal>
      <Modal
        open={!!editingDate || !!editingAvailability}
        preventDismiss={busy}
        onOpenChange={(open) => {
          if (!open) {
            setEditingDate(null);
            setEditingAvailability(null);
          }
        }}
        title="Linked calendar item"
      >
        {(editingDate || editingAvailability)?.cancelled ? (
          <p>
            This calendar item was removed. Its source connection is preserved.
          </p>
        ) : editingDate ? (
          <CalendarDateForm
            item={editingDate}
            onPendingChange={setBusy}
            onSaved={() => {
              setEditingDate(null);
              refresh();
            }}
          />
        ) : editingAvailability ? (
          <AvailabilityForm
            item={editingAvailability}
            onPendingChange={setBusy}
            onSaved={() => {
              setEditingAvailability(null);
              refresh();
            }}
          />
        ) : null}
      </Modal>
      <Modal
        open={!!editingEvent}
        onOpenChange={(open) => {
          if (!open && !planning.busy) setEditingEvent(null);
        }}
        preventDismiss={planning.busy}
        title="Linked event"
      >
        {editingEvent &&
          (editingEvent.cancelled ? (
            <p>This event was removed. Its source connection is preserved.</p>
          ) : (
            <TimeForm
              key={editingEvent.id}
              event={editingEvent}
              onSaved={() => setEditingEvent(null)}
            />
          ))}
      </Modal>
    </section>
  );
}
