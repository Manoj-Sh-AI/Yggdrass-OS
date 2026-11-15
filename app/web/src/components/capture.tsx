"use client";
import { useEffect, useState } from "react";
import { areas, localDate } from "@/lib/data";
import { capture } from "@/lib/repository";
import type { Activity } from "@/lib/types";
import { useApp } from "./provider";
import { Icon, Modal } from "./ui";
export type CaptureKind = Activity["kind"];
export function CaptureDialog({
  kind,
  onClose,
  initialTitle = "",
}: {
  kind: CaptureKind | null;
  onClose: () => void;
  initialTitle?: string;
}) {
  const { update, toast, createNote, shelves, brainMode, brainError } =
    useApp();
  const [title, setTitle] = useState(initialTitle),
    [content, setContent] = useState(""),
    [area, setArea] = useState("projects"),
    [shelfId, setShelfId] = useState("14-inbox"),
    [tags, setTags] = useState(""),
    [date, setDate] = useState(localDate()),
    [filename, setFilename] = useState(""),
    [pending, setPending] = useState(false),
    [error, setError] = useState("");
  useEffect(() => {
    if (kind) {
      setTitle(initialTitle);
      setContent("");
      setTags("");
      setFilename("");
      setError("");
    }
  }, [kind, initialTitle]);
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!title.trim()) {
      setError("Give your capture a title.");
      return;
    }
    if (kind === "file" && !filename) {
      setError("Choose a file to capture its name.");
      return;
    }
    setPending(true);
    const input = {
      kind: kind!,
      title,
      content,
      area,
      tags: tags
        .split(",")
        .map((t) => t.trim())
        .filter(Boolean),
      date,
      filename,
      shelfId,
    };
    const ok =
      kind === "task"
        ? await update((s) => capture(s, input))
        : await createNote(input);
    setPending(false);
    if (ok) {
      toast(
        kind === "task"
          ? "Task saved to PostgreSQL."
          : "Synthetic note saved through the mock Brain adapter.",
      );
      onClose();
    } else
      setError(
        "Could not save. Your capture is still here; check service availability and try again.",
      );
  }
  return (
    <Modal
      open={!!kind}
      onOpenChange={(v) => {
        if (!v && !pending) onClose();
      }}
      title={`Capture ${kind === "idea" ? "an idea" : kind === "file" ? "a file" : `a ${kind || "note"}`}`}
      description={
        kind === "task"
          ? "Application task · PostgreSQL storage"
          : "Synthetic mock Brain · real Lia integration is blocked"
      }
    >
      <form onSubmit={submit} className="form-stack">
        {kind !== "task" && (
          <label>
            Brain shelf
            <select
              aria-label="Brain shelf"
              value={shelfId}
              onChange={(e) => setShelfId(e.target.value)}
            >
              {shelves.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
            {brainMode === "unavailable" && (
              <small role="alert">
                {brainError || "Lia unavailable. Notes cannot be saved."}
              </small>
            )}
          </label>
        )}
        <label>
          Title
          <input
            autoFocus
            value={title}
            maxLength={180}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="What’s on your mind?"
          />
        </label>
        <label>
          Details
          <textarea
            rows={5}
            value={content}
            onChange={(e) => setContent(e.target.value)}
            placeholder="Let it out. You can connect the dots later."
          />
        </label>
        {kind === "file" && (
          <label>
            File
            <input
              type="file"
              onChange={(e) => {
                const name = e.target.files?.[0]?.name || "";
                setFilename(name);
                if (!title) setTitle(name);
              }}
            />
            <small>
              Only the filename is saved. File contents stay on your device.
            </small>
          </label>
        )}
        <div className="form-row">
          {kind === "task" && (
            <label>
              Life area
              <select value={area} onChange={(e) => setArea(e.target.value)}>
                {areas.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.name}
                  </option>
                ))}
              </select>
            </label>
          )}
          {kind === "task" ? (
            <label>
              Due date
              <input
                type="date"
                required
                value={date}
                onChange={(e) => setDate(e.target.value)}
              />
            </label>
          ) : (
            <label>
              Tags
              <input
                value={tags}
                onChange={(e) => setTags(e.target.value)}
                placeholder="ideas, learning"
              />
            </label>
          )}
        </div>
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        <button disabled={pending} className="button primary" type="submit">
          <Icon name={pending ? "LoaderCircle" : "Plus"} />
          {pending ? "Saving…" : "Capture"}
        </button>
      </form>
    </Modal>
  );
}
