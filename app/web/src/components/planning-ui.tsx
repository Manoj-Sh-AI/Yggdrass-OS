"use client";
import Link from "next/link";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { areas } from "@/lib/data";
import {
  addDays,
  dateInZone,
  elapsedLabel,
  localInput,
  foldForInstant,
  minutesBetween,
  taskInput,
  wallTime,
  type PlanningTask,
  type PlanningBlock,
  type CalendarEvent,
  type PlanningGroup,
} from "@/lib/planning";
import { usePlanning, usePlanningClock } from "./planning-provider";
import { Empty, Icon, Modal, Panel, Progress } from "./ui";
import { LinkedNoteContext } from "./linked-note-context";

export function PlanningFeedback() {
  const { error, notice, refresh, busy } = usePlanning();
  return (
    <div className="planning-feedback">
      {error ? (
        <div role="alert" className="planning-error">
          {error}
          <button
            className="button small-button"
            disabled={busy}
            onClick={() => void refresh().catch(() => {})}
          >
            Refresh planning data
          </button>
        </div>
      ) : (
        <span role="status">
          {notice === "Saved to PostgreSQL." ? "Saved" : notice}
        </span>
      )}
    </div>
  );
}
export function CommandButton({
  children,
  action,
  className = "button",
  disabled = false,
  label,
}: {
  children: ReactNode;
  action: () => Promise<unknown>;
  className?: string;
  disabled?: boolean;
  label?: string;
}) {
  const { busy } = usePlanning();
  return (
    <button
      type="button"
      aria-label={label}
      className={className}
      disabled={disabled || busy}
      onClick={() => void action().catch(() => {})}
    >
      {children}
    </button>
  );
}
export function FocusControls({ task }: { task: PlanningTask }) {
  const { run, data } = usePlanning();
  const now = usePlanningClock();
  const [timer, setTimer] = useState(25);
  const [blockId, setBlockId] = useState("");
  useEffect(() => {
    try {
      const value = Number(
        localStorage.getItem(`yggdress.focus.interval:${task.id}`),
      );
      if (
        [0, 15, 25, 50].includes(value) &&
        localStorage.getItem(`yggdress.focus.interval:${task.id}`) !== null
      )
        setTimer(value);
    } catch {
      /* Timer accuracy comes from PostgreSQL, not this optional display preference. */
    }
  }, [task.id]);
  const blocks = data?.blocks.filter((b) => b.task_id === task.id) || [];
  const running = task.state === "in_progress";
  const otherFocus = data?.tasks.find(
    (item) => item.state === "in_progress" && item.id !== task.id,
  );
  const elapsed =
    task.actual_seconds +
    (running && data
      ? Math.max(0, (now - Date.parse(data.server_now)) / 1000)
      : 0);
  const execute = (action: string) =>
    run(
      "task.execute",
      {
        action,
        ...(blockId && ["start", "resume", "push"].includes(action)
          ? { block_id: blockId }
          : {}),
      },
      task.id,
      task.version,
    );
  return (
    <div className="planning-focus" aria-label={`${task.title} execution`}>
      <div className="planning-clock">
        <span className="eyebrow">ACTUAL FOCUS TIME</span>
        <strong role="timer" aria-label="Elapsed execution time">
          {elapsedLabel(elapsed)}
        </strong>
        <small>
          {Math.max(0, Math.ceil(task.estimated_minutes - elapsed / 60))} min
          remaining estimate · {task.state.replace("_", " ")}
        </small>
      </div>
      {!running && !task.done && blocks.length > 0 && (
        <label className="planning-timer-choice">
          Execution window
          <select value={blockId} onChange={(e) => setBlockId(e.target.value)}>
            <option value="">Unscheduled focus</option>
            {blocks.map((b) => (
              <option key={b.id} value={b.id}>
                {dateInZone(b.starts_at, b.timezone)}{" "}
                {wallTime(b.starts_at, b.timezone)}
              </option>
            ))}
          </select>
        </label>
      )}
      {!task.done && task.state !== "skipped" && (
        <div className="planning-actions">
          {otherFocus ? (
            <CommandButton
              className="button primary"
              action={() =>
                run(
                  "focus.switch",
                  {
                    from_task_id: otherFocus.id,
                    from_version: otherFocus.version,
                  },
                  task.id,
                  task.version,
                )
              }
            >
              Switch focus here
            </CommandButton>
          ) : (
            <CommandButton
              className="button primary"
              action={() =>
                execute(
                  running
                    ? "pause"
                    : task.state === "paused"
                      ? "resume"
                      : "start",
                )
              }
            >
              {running
                ? "Pause"
                : task.state === "paused"
                  ? "Resume"
                  : "Start focus"}
            </CommandButton>
          )}
          {running && (
            <CommandButton action={() => execute("push")}>
              Push · continue
            </CommandButton>
          )}
          <CommandButton action={() => execute("complete")}>
            Complete task
          </CommandButton>
        </div>
      )}
      {task.done && (
        <CommandButton action={() => execute("reopen")}>
          Reopen task
        </CommandButton>
      )}
      <label className="planning-timer-choice">
        Focus interval{" "}
        <select
          value={timer}
          onChange={(e) => {
            const value = Number(e.target.value);
            setTimer(value);
            try {
              localStorage.setItem(
                `yggdress.focus.interval:${task.id}`,
                String(value),
              );
            } catch {
              /* Optional display preference only. */
            }
          }}
        >
          <option value={0}>Off</option>
          <option value={15}>15 min</option>
          <option value={25}>25 min</option>
          <option value={50}>50 min</option>
        </select>
        {timer > 0 && (
          <span role="timer" aria-label="Focus interval remaining">
            {elapsedLabel(Math.max(0, timer * 60 - elapsed))}
            {elapsed >= timer * 60
              ? " · interval reached; choose your next step"
              : ""}
          </span>
        )}
      </label>
      <p className="muted">
        Timers continue from server timestamps while you are away. Pausing stops
        tracked time. The goal stays fixed.
      </p>
      {data?.sessions
        .filter((s) => s.task_id === task.id && s.scheduled_start)
        .slice(-3)
        .map((s) => (
          <p key={s.id} className="muted">
            Scheduled {wallTime(s.scheduled_start!, task.timezone)} · actually
            started {wallTime(s.started_at, task.timezone)} ·{" "}
            {Math.max(
              0,
              Math.round(
                (Date.parse(s.started_at) - Date.parse(s.scheduled_start!)) /
                  60000,
              ),
            )}{" "}
            min initiation delay
          </p>
        ))}
    </div>
  );
}

export function TaskForm({
  task,
  onSaved,
  parentId,
  createWith,
}: {
  task?: PlanningTask;
  onSaved: () => void;
  parentId?: string;
  createWith?: (data: Record<string, unknown>) => Promise<{ id?: string }>;
}) {
  const { data, run, timezone, busy: planningBusy } = usePlanning();
  const [pending, setPending] = useState(false);
  const saving = useRef(false);
  const busy = planningBusy || pending;
  const [draft, setDraft] = useState(() =>
    task && data
      ? taskInput(task, data.dependencies)
      : {
          title: "",
          objective: "",
          description: "",
          area: "work",
          due_date: null as string | null,
          deadline_at: null as string | null,
          timezone,
          priority: 2,
          estimated_minutes: 30,
          effort: "unspecified",
          tags: [] as string[],
          goal_id: null as string | null,
          project_id: null as string | null,
          parent_id: parentId || null,
          dependencies: [] as string[],
        },
  );
  const [baseVersion] = useState(task?.version),
    [error, setError] = useState(""),
    [exactDeadline, setExactDeadline] = useState(task?.deadline_at || ""),
    [tagText, setTagText] = useState(draft.tags.join(", "));
  const change = (key: string, value: unknown) =>
    setDraft((d) => ({ ...d, [key]: value }));
  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (saving.current) return;
    saving.current = true;
    setPending(true);
    setError("");
    try {
      const payload = {
        ...draft,
        tags: tagText
          .split(",")
          .map((t) => t.trim())
          .filter(Boolean),
        deadline_at: exactDeadline.trim() || null,
      };
      const result =
        createWith && !task
          ? await createWith(payload)
          : await run(
              task ? "task.update" : "task.create",
              payload,
              task?.id,
              baseVersion,
            );
      if (result.id) onSaved();
    } catch (e) {
      setError(
        e instanceof Error
          ? e.message
          : "Could not save. Your draft is preserved.",
      );
    } finally {
      saving.current = false;
      setPending(false);
    }
  }
  return (
    <form className="form-stack planning-form" onSubmit={save}>
      {task?.template_id && (
        <p className="planning-callout">
          Editing this occurrence only. The routine definition and other dates
          stay as they are.
        </p>
      )}
      <label>
        Task title
        <input
          required
          maxLength={180}
          value={draft.title}
          onChange={(e) => change("title", e.target.value)}
        />
      </label>
      <label>
        Required outcome · fixed objective
        <textarea
          required
          maxLength={2000}
          rows={2}
          value={draft.objective}
          onChange={(e) => change("objective", e.target.value)}
        />
        <small>
          Only this explicit edit changes the objective. Scheduling controls
          never change it.
        </small>
      </label>
      <label>
        Description
        <textarea
          value={draft.description}
          maxLength={10000}
          onChange={(e) => change("description", e.target.value)}
        />
      </label>
      <div className="form-row">
        <label>
          Due date
          <input
            type="date"
            value={draft.due_date || ""}
            onChange={(e) => change("due_date", e.target.value || null)}
          />
        </label>
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
      </div>
      <details>
        <summary>Exact deadline (optional)</summary>
        <label>
          Deadline with UTC offset
          <input
            value={exactDeadline}
            onChange={(e) => setExactDeadline(e.target.value)}
            placeholder="2026-11-12T17:00:00+01:00"
          />
          <small>
            Use an explicit offset for an exact instant. Its date is shown in
            the task timezone.
          </small>
        </label>
      </details>
      <div className="form-row">
        <label>
          Estimate (minutes)
          <input
            type="number"
            required
            min={1}
            max={1440}
            value={draft.estimated_minutes}
            onChange={(e) =>
              change("estimated_minutes", Number(e.target.value))
            }
          />
        </label>
        <label>
          Estimated effort
          <select
            value={draft.effort}
            onChange={(e) => change("effort", e.target.value)}
          >
            {["unspecified", "light", "moderate", "demanding"].map((v) => (
              <option key={v}>{v}</option>
            ))}
          </select>
        </label>
      </div>
      <div className="form-row">
        <label>
          Life area
          <select
            value={draft.area}
            onChange={(e) => change("area", e.target.value)}
          >
            {areas.map((a) => (
              <option value={a.id} key={a.id}>
                {a.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Task timezone
          <input
            value={draft.timezone}
            onChange={(e) => change("timezone", e.target.value)}
            required
          />
        </label>
      </div>
      <label>
        Tags (comma separated)
        <input value={tagText} onChange={(e) => setTagText(e.target.value)} />
      </label>
      <div className="form-row">
        <label>
          Goal
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
        <label>
          Project
          <select
            value={draft.project_id || ""}
            onChange={(e) => change("project_id", e.target.value || null)}
          >
            <option value="">No project</option>
            {data?.projects.map((g) => (
              <option key={g.id} value={g.id}>
                {g.title}
              </option>
            ))}
          </select>
        </label>
      </div>
      <label>
        Parent task
        <select
          value={draft.parent_id || ""}
          onChange={(e) => change("parent_id", e.target.value || null)}
        >
          <option value="">Top-level task</option>
          {data?.tasks
            .filter((t) => t.id !== task?.id)
            .map((t) => (
              <option key={t.id} value={t.id}>
                {t.title}
              </option>
            ))}
        </select>
      </label>
      <label>
        Dependencies (select any required tasks)
        <select
          multiple
          size={Math.min(4, Math.max(2, data?.tasks.length || 0))}
          value={draft.dependencies}
          onChange={(e) =>
            change(
              "dependencies",
              Array.from(e.target.selectedOptions, (o) => o.value),
            )
          }
        >
          {data?.tasks
            .filter((t) => t.id !== task?.id)
            .map((t) => (
              <option key={t.id} value={t.id}>
                {t.title}
              </option>
            ))}
        </select>
        <small>
          Use Ctrl/⌘ to select several. Cycles and starting before dependencies
          finish are rejected.
        </small>
      </label>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      <button className="button primary" disabled={busy}>
        {busy ? "Saving…" : task ? "Save task changes" : "Create task"}
      </button>
    </form>
  );
}

export function TimeForm({
  task,
  block,
  event,
  initialStart,
  onSaved,
  createWith,
  submitWith,
}: {
  task?: PlanningTask;
  block?: PlanningBlock;
  event?: CalendarEvent;
  initialStart?: string;
  onSaved: () => void;
  createWith?: (data: Record<string, unknown>) => Promise<{ id?: string }>;
  submitWith?: (data: Record<string, unknown>) => Promise<{ id?: string }>;
}) {
  const { run, busy: planningBusy, timezone, day } = usePlanning();
  const [pending, setPending] = useState(false);
  const saving = useRef(false);
  const busy = planningBusy || pending;
  const item = block || event;
  const [zone, setZone] = useState(item?.timezone || timezone),
    [start, setStart] = useState(
      item
        ? localInput(item.starts_at, item.timezone)
        : initialStart || day + "T09:00",
    ),
    [end, setEnd] = useState(
      item ? localInput(item.ends_at, item.timezone) : day + "T10:00",
    ),
    [reason, setReason] = useState(block?.reason || "Manually scheduled"),
    [title, setTitle] = useState(event?.title || ""),
    [description, setDescription] = useState(event?.description || ""),
    [fold, setFold] = useState(
      item ? foldForInstant(item.starts_at, item.timezone) : 0,
    ),
    [endFold, setEndFold] = useState(
      item ? foldForInstant(item.ends_at, item.timezone) : 0,
    ),
    [error, setError] = useState("");
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (saving.current) return;
    saving.current = true;
    setPending(true);
    setError("");
    try {
      const payload = {
        start,
        end,
        timezone: zone,
        fold,
        end_fold: endFold,
        reason,
        title,
        description,
        ...(task ? { task_id: task.id } : {}),
      };
      if (submitWith) await submitWith(payload);
      else if (createWith && !item && !task) await createWith(payload);
      else
        await run(
          task || block
            ? block
              ? "block.update"
              : "block.create"
            : event
              ? "event.update"
              : "event.create",
          payload,
          item?.id,
          item?.version,
        );
      onSaved();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save.");
    } finally {
      saving.current = false;
      setPending(false);
    }
  }
  return (
    <form className="form-stack planning-form" onSubmit={submit}>
      {task ? (
        <div className="planning-callout">
          <strong>{task.title}</strong>
          <p>Fixed outcome: {task.objective}</p>
          <small>
            Deadline: {task.due_date || "None"} · schedule changes preserve it.
          </small>
        </div>
      ) : (
        <>
          <label>
            Event title
            <input
              required
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />
          </label>
          <label>
            Event description
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </label>
        </>
      )}
      <label>
        Start
        <input
          type="datetime-local"
          required
          value={start}
          onChange={(e) => setStart(e.target.value)}
        />
      </label>
      <label>
        End
        <input
          type="datetime-local"
          required
          value={end}
          onChange={(e) => setEnd(e.target.value)}
        />
      </label>
      <label>
        Calendar timezone
        <input
          required
          value={zone}
          onChange={(e) => setZone(e.target.value)}
        />
      </label>
      <details>
        <summary>Clock-change options</summary>
        <p className="muted">
          During the repeated autumn hour, choose the first or second
          occurrence. Nonexistent spring times need correction.
        </p>
        <div className="form-row">
          <label>
            Start occurrence
            <select
              value={fold}
              onChange={(e) => setFold(Number(e.target.value))}
            >
              <option value={0}>First</option>
              <option value={1}>Second</option>
            </select>
          </label>
          <label>
            End occurrence
            <select
              value={endFold}
              onChange={(e) => setEndFold(Number(e.target.value))}
            >
              <option value={0}>First</option>
              <option value={1}>Second</option>
            </select>
          </label>
        </div>
      </details>
      {(task || block) && (
        <label>
          Why this time?
          <input
            required
            maxLength={1000}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />
        </label>
      )}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      <button className="button primary" disabled={busy}>
        {busy
          ? "Saving…"
          : item
            ? "Save calendar changes"
            : task
              ? "Schedule block"
              : "Create event"}
      </button>
    </form>
  );
}

export function PlanningTaskSheet() {
  const { selected, select, data, run, timezone, busy } = usePlanning();
  const task = data?.tasks.find((t) => t.id === selected);
  return (
    <Modal
      open={!!task}
      onOpenChange={(open) => {
        if (!open && !busy) select(null);
      }}
      title={task?.title || "Task"}
      preventDismiss={busy}
      description="Fixed Goals, Adaptive Execution · application planning"
      sheet
    >
      {task && (
        <TaskDetail
          key={task.id}
          task={task}
          timezone={timezone}
          onClose={() => select(null)}
          run={run}
        />
      )}
    </Modal>
  );
}
function TaskDetail({
  task,
  timezone,
}: {
  task: PlanningTask;
  timezone: string;
  onClose: () => void;
  run: ReturnType<typeof usePlanning>["run"];
}) {
  const { data, run, busy, select } = usePlanning();
  const [editing, setEditing] = useState(false),
    [schedule, setSchedule] = useState(false),
    [editBlock, setEditBlock] = useState<PlanningBlock | null>(null),
    [child, setChild] = useState(false),
    [percent, setPercent] = useState(String(task.progress));
  const blocks = data?.blocks.filter((b) => b.task_id === task.id) || [];
  return (
    <div className="planning-detail">
      <PlanningFeedback />
      {editing ? (
        <>
          <TaskForm task={task} onSaved={() => setEditing(false)} />
          <button className="button" onClick={() => setEditing(false)}>
            Cancel edit
          </button>
        </>
      ) : (
        <>
          <div className="planning-callout">
            <span className="eyebrow">FIXED OUTCOME</span>
            <p>{task.objective}</p>
          </div>
          <p>{task.description}</p>
          <LinkedNoteContext kind="task" id={task.id} version={task.version} />
          <div className="planning-detail-meta">
            <span>Due {task.due_date || "No deadline"}</span>
            <span>{task.estimated_minutes} min estimate</span>
            <span>{["", "High", "Medium", "Low"][task.priority]} priority</span>
            <span>{task.tags.join(" · ") || "No tags"}</span>
          </div>
          <button className="button" onClick={() => setEditing(true)}>
            Edit task / objective / deadline
          </button>
          <FocusControls task={task} />
          <Progress
            value={task.progress}
            color="#8dafff"
            label={`${task.title} progress`}
          />
          {!task.done && (
            <form
              className="planning-inline"
              onSubmit={(e) => {
                e.preventDefault();
                void run(
                  "task.execute",
                  { action: "progress", percent: Number(percent) },
                  task.id,
                  task.version,
                ).catch(() => {});
              }}
            >
              <label>
                Task progress (%)
                <input
                  type="number"
                  min={0}
                  max={100}
                  required
                  value={percent}
                  onChange={(e) => setPercent(e.target.value)}
                />
              </label>
              <button className="button" disabled={busy}>
                Save progress
              </button>
            </form>
          )}
          <div className="planning-section-title">
            <h3>Execution blocks</h3>
            <button
              className="button small-button"
              disabled={task.done}
              onClick={() => {
                setSchedule(!schedule);
                setEditBlock(null);
              }}
            >
              Schedule / reschedule
            </button>
          </div>
          <p className="muted">
            Split adds sessions for this same objective. Removing a block keeps
            the task.
          </p>
          {schedule && (
            <TimeForm
              key={editBlock?.id || "new"}
              task={task}
              block={editBlock || undefined}
              onSaved={() => {
                setSchedule(false);
                setEditBlock(null);
              }}
            />
          )}
          {blocks.map((b) => (
            <div className="planning-block-detail" key={b.id}>
              <strong>
                {dateInZone(b.starts_at, timezone)} ·{" "}
                {wallTime(b.starts_at, timezone)}–
                {wallTime(b.ends_at, timezone)}
              </strong>
              <p>{b.reason}</p>
              <div className="planning-actions">
                <button
                  className="button small-button"
                  onClick={() => {
                    setEditBlock(b);
                    setSchedule(true);
                  }}
                >
                  Move / resize
                </button>
                <CommandButton
                  className="button small-button"
                  action={() =>
                    run(
                      "block.split",
                      {
                        at: new Date(
                          (Date.parse(b.starts_at) + Date.parse(b.ends_at)) / 2,
                        ).toISOString(),
                      },
                      b.id,
                      b.version,
                    )
                  }
                >
                  Split in two
                </CommandButton>
                <CommandButton
                  className="button small-button"
                  action={() => run("block.remove", {}, b.id, b.version)}
                >
                  Remove block
                </CommandButton>
              </div>
            </div>
          ))}
          {!blocks.length && (
            <p className="muted">
              No blocks in this calendar range.{" "}
              <Link href="/calendar">Open Calendar</Link> to choose another
              date.
            </p>
          )}
          <div className="planning-section-title">
            <h3>Subtasks & dependencies</h3>
            <button
              className="button small-button"
              onClick={() => setChild(!child)}
            >
              Add subtask
            </button>
          </div>
          {child && (
            <TaskForm parentId={task.id} onSaved={() => setChild(false)} />
          )}
          {data?.tasks
            .filter(
              (t) =>
                t.parent_id === task.id ||
                data.dependencies.some(
                  (d) => d.task_id === task.id && d.depends_on === t.id,
                ),
            )
            .map((t) => (
              <button
                className="planning-related"
                key={t.id}
                onClick={() => select(t.id)}
              >
                {t.done ? "✓" : "○"} {t.title}
                <small>
                  {t.parent_id === task.id ? "Subtask" : "Required first"}
                </small>
              </button>
            ))}
          <details>
            <summary>Execution & change history</summary>
            {data?.history
              .filter((h) => h.task_id === task.id)
              .slice(0, 60)
              .map((h) => (
                <div className="planning-history" key={h.id}>
                  <strong>{h.kind.replaceAll(".", " · ")}</strong>
                  <time>
                    {new Date(h.at).toLocaleString("en", {
                      timeZone: timezone,
                    })}
                  </time>
                  <details>
                    <summary>Inspect recorded change</summary>
                    <pre>{JSON.stringify(h.detail, null, 2)}</pre>
                  </details>
                </div>
              ))}
            <small>
              Latest 1,000 workspace history records loaded. Full history is
              retained in PostgreSQL.
            </small>
          </details>
        </>
      )}
    </div>
  );
}

export function GroupManager() {
  const { data, run } = usePlanning();
  const [kind, setKind] = useState<"goal" | "project">("goal"),
    [editing, setEditing] = useState<PlanningGroup | null>(null),
    [open, setOpen] = useState(false);
  return (
    <div className="planning-group-grid">
      {(["goal", "project"] as const).map((type) => (
        <Panel
          key={type}
          title={type === "goal" ? "Goals · fixed commitments" : "Projects"}
          action={
            <button
              className="button small-button"
              onClick={() => {
                setKind(type);
                setEditing(null);
                setOpen(true);
              }}
            >
              Add {type}
            </button>
          }
        >
          {(type === "goal" ? data?.goals : data?.projects)?.map((g) => {
            const tasks =
                data?.tasks.filter(
                  (t) => (type === "goal" ? t.goal_id : t.project_id) === g.id,
                ) || [],
              done = tasks.filter((t) => t.done).length;
            return (
              <div className="planning-group" key={g.id}>
                <button
                  onClick={() => {
                    setKind(type);
                    setEditing(g);
                    setOpen(true);
                  }}
                >
                  <strong>{g.title}</strong>
                  <Icon name="Pencil" size={14} />
                </button>
                <p>{g.description}</p>
                <Progress
                  label={g.title}
                  value={tasks.length ? (done / tasks.length) * 100 : 0}
                  color="#8fb0f1"
                />
                <small>
                  {done}/{tasks.length} linked tasks complete
                </small>
              </div>
            );
          })}
          {!(type === "goal" ? data?.goals.length : data?.projects.length) && (
            <Empty
              title={`Make room for a ${type}`}
              detail="Link tasks to see your progress here."
            />
          )}
        </Panel>
      ))}
      <Modal
        open={open}
        onOpenChange={setOpen}
        title={`${editing ? "Edit" : "New"} ${kind}`}
        description="Commitments change only through your explicit edits."
      >
        <GroupForm
          key={editing?.id || kind}
          kind={kind}
          group={editing || undefined}
          onSaved={() => setOpen(false)}
          run={run}
        />
      </Modal>
    </div>
  );
}
function GroupForm({
  kind,
  group,
  onSaved,
}: {
  kind: "goal" | "project";
  group?: PlanningGroup;
  onSaved: () => void;
  run: ReturnType<typeof usePlanning>["run"];
}) {
  const { data, run, busy } = usePlanning();
  const [title, setTitle] = useState(group?.title || ""),
    [description, setDescription] = useState(group?.description || ""),
    [goal, setGoal] = useState(group?.goal_id || ""),
    [error, setError] = useState("");
  return (
    <form
      className="form-stack"
      onSubmit={async (e) => {
        e.preventDefault();
        try {
          await run(
            `${kind}.${group ? "update" : "create"}`,
            {
              title,
              description,
              ...(kind === "project" ? { goal_id: goal || null } : {}),
            },
            group?.id,
            group?.version,
          );
          onSaved();
        } catch (e) {
          setError((e as Error).message);
        }
      }}
    >
      <label>
        {kind === "goal" ? "Goal title" : "Project title"}
        <input
          required
          value={title}
          onChange={(e) => setTitle(e.target.value)}
        />
      </label>
      <label>
        Description
        <textarea
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />
      </label>
      {kind === "project" && (
        <label>
          Associated goal
          <select value={goal} onChange={(e) => setGoal(e.target.value)}>
            <option value="">No goal</option>
            {data?.goals.map((g) => (
              <option key={g.id} value={g.id}>
                {g.title}
              </option>
            ))}
          </select>
        </label>
      )}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <button className="button primary" disabled={busy}>
        Save {kind}
      </button>
    </form>
  );
}

export function TaskRow({
  task,
  scheduling = false,
}: {
  task: PlanningTask;
  scheduling?: boolean;
}) {
  const { select, run, data, timezone } = usePlanning();
  const blocks = data?.blocks.filter((b) => b.task_id === task.id) || [];
  return (
    <div
      className={`planning-task-row ${task.done ? "done" : ""}`}
      draggable={scheduling && !task.done}
      onDragStart={(e) => {
        e.dataTransfer.setData("application/yggdress-task", task.id);
        e.dataTransfer.effectAllowed = "copy";
      }}
    >
      {scheduling && !task.done && (
        <button
          className="planning-task-drag"
          type="button"
          aria-label={`Drag to schedule ${task.title}`}
          onClick={(e) => e.preventDefault()}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              select(task.id);
            }
          }}
          onPointerDown={(e) => {
            e.preventDefault();
            e.stopPropagation();
            window.dispatchEvent(
              new CustomEvent("yggdress:planning-drag-task", {
                detail: { taskId: task.id, x: e.clientX, y: e.clientY },
              }),
            );
          }}
        >
          ⠿
        </button>
      )}
      <CommandButton
        className="planning-check"
        label={`${task.done ? "Reopen" : "Complete"} ${task.title}`}
        action={() =>
          run(
            "task.execute",
            { action: task.done ? "reopen" : "complete" },
            task.id,
            task.version,
          )
        }
      >
        {task.done ? "✓" : "○"}
      </CommandButton>
      <button className="planning-task-main" onClick={() => select(task.id)}>
        <strong>{task.title}</strong>
        <span>
          {task.template_id ? "↻ Routine · " : ""}
          {task.due_date
            ? `Due ${task.due_date}`
            : "Inbox · no deadline"} · {task.estimated_minutes} min
          {blocks[0]
            ? ` · ${dateInZone(blocks[0].starts_at, timezone)} ${wallTime(blocks[0].starts_at, timezone)}`
            : ""}
        </span>
        {task.tags.length > 0 && (
          <small>{task.tags.map((t) => "#" + t).join(" ")}</small>
        )}
      </button>
      <span className={`planning-priority priority-${task.priority}`}>
        {["", "High", "Med", "Low"][task.priority]}
      </span>
      <button
        className="icon-button"
        aria-label={`Open ${task.title}`}
        onClick={() => select(task.id)}
      >
        <Icon name="ChevronRight" size={16} />
      </button>
    </div>
  );
}
