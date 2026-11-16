"use client";
import { useState } from "react";
import { usePlanning } from "./planning-provider";
import { CommandButton } from "./planning-ui";
import { Empty, Icon, Modal, Panel } from "./ui";
import type { RoutineTemplate } from "@/lib/planning";
import { areas } from "@/lib/data";
export function RoutineManager() {
  const { data, day, run } = usePlanning();
  const [open, setOpen] = useState(false),
    [editing, setEditing] = useState<RoutineTemplate | null>(null),
    [skip, setSkip] = useState(day);
  return (
    <Panel
      className="planning-routines"
      title="Routines that make room for life"
      action={
        <button
          className="button primary"
          onClick={() => {
            setEditing(null);
            setOpen(true);
          }}
        >
          <Icon name="Plus" size={15} />
          New routine
        </button>
      }
    >
      <p className="muted">
        Daily and weekly commitments generate once per local date. Individual
        edits stay with their occurrence.
      </p>
      <div className="planning-group-grid">
        {data?.routines.map((r) => (
          <div className="planning-group" key={r.id}>
            <div className="planning-section-title">
              <h3>{r.title}</h3>
              <span className="planning-kind routine">
                {r.active ? "Active" : "Inactive"}
                {r.essential ? " · essential" : ""}
              </span>
            </div>
            <p>{r.objective}</p>
            <small>
              Every {r.interval_count}{" "}
              {r.frequency === "daily"
                ? "day(s)"
                : `week(s) · ${r.weekdays.map((d) => ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][d]).join(", ")}`}{" "}
              · {r.window_start.slice(0, 5)}–{r.window_end.slice(0, 5)} ·{" "}
              {r.expected_minutes} min · {r.timezone}
            </small>
            <div className="planning-actions">
              <button
                className="button small-button"
                onClick={() => {
                  setEditing(r);
                  setOpen(true);
                }}
              >
                Edit future series
              </button>
            </div>
            <label className="planning-inline">
              Exception date
              <input
                aria-label={`Skip date for ${r.title}`}
                type="date"
                value={skip}
                onChange={(e) => setSkip(e.target.value)}
              />
              <CommandButton
                className="button small-button"
                action={() =>
                  run("routine.skip", { day: skip }, r.id, r.version)
                }
              >
                Skip this date
              </CommandButton>
            </label>
            <small>
              {data.exceptions
                .filter((e) => e.template_id === r.id)
                .map((e) => e.occurrence_date)
                .join(", ") || "No exceptions"}
            </small>
          </div>
        ))}
      </div>
      {!data?.routines.length && (
        <Empty
          title="Let your routines take care of the basics"
          detail="Create a daily or weekly routine. Its occurrences appear in Tasks, Today and Calendar."
        />
      )}
      <Modal
        open={open}
        onOpenChange={setOpen}
        title={
          editing ? "Edit future routine occurrences" : "New recurring routine"
        }
        description="Past, started and individually edited occurrences are preserved."
      >
        <RoutineForm
          key={editing?.id || "new"}
          routine={editing || undefined}
          onSaved={() => setOpen(false)}
        />
      </Modal>
    </Panel>
  );
}
function RoutineForm({
  routine,
  onSaved,
}: {
  routine?: RoutineTemplate;
  onSaved: () => void;
}) {
  const { data, day, timezone, run, busy } = usePlanning();
  const [draft, setDraft] = useState(() => {
    const { id, version, ...values } = routine || {
      id: "",
      version: 1,
      title: "",
      description: "",
      objective: "",
      area: "health",
      frequency: "daily" as const,
      interval_count: 1,
      weekdays: [0, 1, 2, 3, 4],
      starts_on: day,
      ends_on: null,
      timezone,
      window_start: "08:00",
      window_end: "09:00",
      expected_minutes: 30,
      priority: 2,
      goal_id: null,
      essential: false,
      active: true,
    };
    return values;
  });
  const [error, setError] = useState("");
  const change = (key: string, value: unknown) =>
    setDraft((d) => ({ ...d, [key]: value }));
  return (
    <form
      className="form-stack planning-form"
      onSubmit={async (e) => {
        e.preventDefault();
        setError("");
        try {
          await run(
            routine ? "routine.update" : "routine.create",
            draft,
            routine?.id,
            routine?.version,
          );
          onSaved();
        } catch (e) {
          setError((e as Error).message);
        }
      }}
    >
      {routine && (
        <p className="planning-callout">
          Changes apply to untouched occurrences after today and new dates.
          Today, past dates, edited blocks and execution history remain intact.
        </p>
      )}
      <label>
        Routine title
        <input
          required
          value={draft.title}
          onChange={(e) => change("title", e.target.value)}
        />
      </label>
      <label>
        Routine goal / required outcome
        <textarea
          required
          value={draft.objective}
          onChange={(e) => change("objective", e.target.value)}
        />
      </label>
      <label>
        Description
        <textarea
          value={draft.description}
          onChange={(e) => change("description", e.target.value)}
        />
      </label>
      <label>
        Life area
        <select
          value={draft.area}
          onChange={(e) => change("area", e.target.value)}
        >
          {areas.map((a) => (
            <option key={a.id} value={a.id}>
              {a.name}
            </option>
          ))}
        </select>
      </label>
      <div className="form-row">
        <label>
          Frequency
          <select
            value={draft.frequency}
            onChange={(e) => change("frequency", e.target.value)}
          >
            <option value="daily">Daily</option>
            <option value="weekly">Weekly</option>
          </select>
        </label>
        <label>
          Every N days / weeks
          <input
            type="number"
            min={1}
            max={52}
            required
            value={draft.interval_count}
            onChange={(e) => change("interval_count", Number(e.target.value))}
          />
        </label>
      </div>
      {draft.frequency === "weekly" && (
        <fieldset>
          <legend>Weekdays</legend>
          <div className="planning-weekdays">
            {["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((d, i) => (
              <label key={d}>
                <input
                  type="checkbox"
                  checked={draft.weekdays.includes(i)}
                  onChange={(e) =>
                    change(
                      "weekdays",
                      e.target.checked
                        ? [...draft.weekdays, i].sort()
                        : draft.weekdays.filter((v) => v !== i),
                    )
                  }
                />
                {d}
              </label>
            ))}
          </div>
        </fieldset>
      )}
      <div className="form-row">
        <label>
          Starts on
          <input
            type="date"
            required
            value={draft.starts_on}
            onChange={(e) => change("starts_on", e.target.value)}
          />
        </label>
        <label>
          Ends on (optional)
          <input
            type="date"
            value={draft.ends_on || ""}
            onChange={(e) => change("ends_on", e.target.value || null)}
          />
        </label>
      </div>
      <div className="form-row">
        <label>
          Preferred window start
          <input
            type="time"
            required
            value={draft.window_start.slice(0, 5)}
            onChange={(e) => change("window_start", e.target.value)}
          />
        </label>
        <label>
          Preferred window end
          <input
            type="time"
            required
            value={draft.window_end.slice(0, 5)}
            onChange={(e) => change("window_end", e.target.value)}
          />
        </label>
      </div>
      <div className="form-row">
        <label>
          Expected duration (minutes)
          <input
            type="number"
            min={1}
            max={1440}
            required
            value={draft.expected_minutes}
            onChange={(e) => change("expected_minutes", Number(e.target.value))}
          />
        </label>
        <label>
          Routine timezone
          <input
            required
            value={draft.timezone}
            onChange={(e) => change("timezone", e.target.value)}
          />
        </label>
      </div>
      <div className="form-row">
        <label>
          Priority
          <select
            value={draft.priority}
            onChange={(e) => change("priority", Number(e.target.value))}
          >
            <option value={1}>High</option>
            <option value={2}>Medium</option>
            <option value={3}>Low</option>
          </select>
        </label>
        <label>
          Associated goal
          <select
            value={draft.goal_id || ""}
            onChange={(e) => change("goal_id", e.target.value || null)}
          >
            <option value="">No goal</option>
            {data?.goals.map((g) => (
              <option key={g.id} value={g.id}>
                {g.title}
              </option>
            ))}
          </select>
        </label>
      </div>
      <label className="planning-checkbox">
        <input
          type="checkbox"
          checked={draft.essential}
          onChange={(e) => change("essential", e.target.checked)}
        />
        Health / essential routine
      </label>
      <label className="planning-checkbox">
        <input
          type="checkbox"
          checked={draft.active}
          onChange={(e) => change("active", e.target.checked)}
        />
        Active series
      </label>
      <p className="muted">
        Named timezone handles seasonal clock changes. A routine in a missing
        spring hour starts at the next valid local time; autumn uses the first
        occurrence. No automatic energy adjustments.
      </p>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <button className="button primary" disabled={busy}>
        {routine
          ? "Apply to future untouched occurrences"
          : "Create recurring routine"}
      </button>
    </form>
  );
}
