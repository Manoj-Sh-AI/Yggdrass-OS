"use client";
import { useRef, useState } from "react";
import {
  addDays,
  type AvailabilityWindow,
  type CalendarDateItem,
} from "@/lib/planning";
import { temporalWrite } from "@/lib/temporal-api";
import { usePlanning } from "./planning-provider";
import { TimeForm } from "./planning-ui";

type Create = (data: Record<string, unknown>) => Promise<{ id?: string }>;
export function CalendarDateForm({
  item,
  onSaved,
  createWith,
  onPendingChange,
}: {
  item?: CalendarDateItem;
  onSaved: () => void;
  createWith?: Create;
  onPendingChange?: (busy: boolean) => void;
}) {
  const { day } = usePlanning();
  const [title, setTitle] = useState(item?.title || ""),
    [description, setDescription] = useState(item?.description || "");
  const [kind, setKind] = useState(item?.kind || "event"),
    [start, setStart] = useState(item?.starts_on || day),
    [end, setEnd] = useState(item ? addDays(item.ends_before, -1) : day);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const lock = useRef(false);
  return (
    <form
      className="form-stack planning-form"
      onSubmit={async (event) => {
        event.preventDefault();
        if (lock.current) return;
        lock.current = true;
        setBusy(true);
        onPendingChange?.(true);
        setError("");
        try {
          if (end < start)
            throw new Error("The end date must be on or after the start date.");
          const data = {
            title,
            description,
            kind,
            starts_on: start,
            ends_before: addDays(end, 1),
          };
          if (createWith && !item) await createWith(data);
          else
            await temporalWrite(
              item ? "date_item.update" : "date_item.create",
              data,
              item?.id,
              item?.version,
            );
          onSaved();
        } catch (error) {
          setError(
            error instanceof Error
              ? error.message
              : "Could not save these dates. Your draft is preserved.",
          );
        } finally {
          lock.current = false;
          setBusy(false);
          onPendingChange?.(false);
        }
      }}
    >
      <label>
        Calendar item title
        <input
          required
          maxLength={180}
          value={title}
          onChange={(event) => setTitle(event.target.value)}
        />
      </label>
      <label>
        Purpose
        <select
          value={kind}
          onChange={(event) =>
            setKind(event.target.value as CalendarDateItem["kind"])
          }
        >
          <option value="event">All-day event</option>
          <option value="availability">Available days</option>
          <option value="review">Review date</option>
        </select>
      </label>
      <div className="form-row">
        <label>
          Start date
          <input
            required
            type="date"
            value={start}
            onChange={(event) => {
              setStart(event.target.value);
              if (event.target.value > end) setEnd(event.target.value);
            }}
          />
        </label>
        <label>
          End date
          <input
            required
            type="date"
            value={end}
            min={start}
            onChange={(event) => setEnd(event.target.value)}
          />
        </label>
      </div>
      <small className="muted">
        Includes the end date. These are calendar dates, without a scheduled
        hour.
      </small>
      <label>
        Description
        <textarea
          maxLength={2000}
          value={description}
          onChange={(event) => setDescription(event.target.value)}
        />
      </label>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      <button className="button primary" disabled={busy}>
        {busy ? "Saving…" : item ? "Save date changes" : "Create date item"}
      </button>
    </form>
  );
}

export function AvailabilityForm({
  item,
  onSaved,
  createWith,
  onPendingChange,
}: {
  item?: AvailabilityWindow;
  onSaved: () => void;
  createWith?: Create;
  onPendingChange?: (busy: boolean) => void;
}) {
  return (
    <TimeForm
      event={item}
      onSaved={onSaved}
      submitWith={async (data) => {
        onPendingChange?.(true);
        try {
          return await (createWith && !item
            ? createWith(data)
            : temporalWrite(
                item ? "availability.update" : "availability.create",
                data,
                item?.id,
                item?.version,
              ));
        } finally {
          onPendingChange?.(false);
        }
      }}
    />
  );
}
