"use client";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { todayWork } from "@/lib/today-workspace";
import {
  dateInZone,
  elapsedLabel,
  wallTime,
  type CalendarEvent,
  type PlanningTask,
} from "@/lib/planning";
import { usePlanning, usePlanningClock } from "./planning-provider";
import {
  CommandButton,
  PlanningFeedback,
  TaskForm,
  TimeForm,
} from "./planning-ui";
import { Icon, Modal } from "./ui";
import { LinkedNoteContext } from "./linked-note-context";
import { BackgroundRuns } from "./background-runs";

function CurrentTask({ task }: { task: PlanningTask }) {
  const { data, run, select } = usePlanning();
  const now = usePlanningClock();
  const running = task.state === "in_progress";
  const elapsed =
    task.actual_seconds +
    (running && data
      ? Math.max(0, (now - Date.parse(data.server_now)) / 1000)
      : 0);
  const execute = (action: string) =>
    run("task.execute", { action }, task.id, task.version);
  return (
    <section className="current-task" aria-labelledby="current-task-title">
      <div className="current-task-meta">
        <span>
          {running
            ? "In progress"
            : task.state === "paused"
              ? "Paused"
              : "Selected task"}
        </span>
        <span>{task.estimated_minutes} min estimate</span>
      </div>
      <h2 id="current-task-title" tabIndex={-1}>
        {task.title}
      </h2>
      {task.objective && <p>{task.objective}</p>}
      <div className="current-task-actions">
        <CommandButton
          className="button primary"
          action={() =>
            execute(
              running ? "pause" : task.state === "paused" ? "resume" : "start",
            )
          }
        >
          {running
            ? "Pause timer"
            : task.state === "paused"
              ? "Resume timer"
              : "Start timer"}
        </CommandButton>
        <CommandButton
          action={async () => {
            await execute("complete");
            requestAnimationFrame(() =>
              document.getElementById("schedule-title")?.focus(),
            );
          }}
        >
          Complete
        </CommandButton>
        <button className="text-link" onClick={() => select(task.id)}>
          Details
        </button>
        {(running || elapsed > 0) && (
          <span role="timer" aria-label="Time spent" aria-live="off">
            {elapsedLabel(elapsed)}
          </span>
        )}
      </div>
    </section>
  );
}
export function TodayPage() {
  const { data, timezone, setDay, select, error, run, busy } = usePlanning();
  const now = usePlanningClock();
  const today = now ? dateInZone(new Date(now), timezone) : "";
  const [choice, setChoice] = useState<{ key: string; id: string | null }>({
    key: "",
    id: null,
  });
  const [event, setEvent] = useState<CalendarEvent | null>(null);
  const [create, setCreate] = useState(false);
  const [limit, setLimit] = useState(8);
  const key = `yggdress.today.focus.v1:${timezone}:${today}`;
  useEffect(() => {
    if (today) setDay(today);
  }, [today, setDay]);
  useEffect(() => {
    let id: string | null = null;
    try {
      id = localStorage.getItem(key);
    } catch {
      /* Optional view preference. */
    }
    setChoice({ key, id });
    setLimit(8);
  }, [key]);
  async function choose(id: string) {
    const target = data?.tasks.find((task) => task.id === id);
    const running = data?.tasks.find((task) => task.state === "in_progress");
    if (!target) return;
    try {
      await run(
        "focus.switch",
        {
          from_task_id: running?.id || null,
          from_version: running?.version || null,
        },
        target.id,
        target.version,
      );
    } catch {
      return;
    }
    setChoice({ key, id });
    requestAnimationFrame(() =>
      document.getElementById("current-task-title")?.focus(),
    );
    try {
      localStorage.setItem(key, id);
    } catch {
      /* Execution remains server-backed. */
    }
  }
  const focus =
    data?.tasks.find((task) => task.state === "in_progress") ||
    data?.tasks.find(
      (task) =>
        task.id === (choice.key === key ? choice.id : null) &&
        !task.done &&
        task.state !== "skipped",
    );
  const work = useMemo(
    () =>
      data && today && data.range.start <= today && data.range.end >= today
        ? todayWork(data, today, timezone)
        : null,
    [data, today, timezone],
  );
  return (
    <div className="today-workspace">
      <header className="quiet-page-heading">
        <div>
          <h1>Today</h1>
          {today && (
            <p>
              {new Intl.DateTimeFormat("en", {
                timeZone: timezone,
                weekday: "long",
                month: "long",
                day: "numeric",
              }).format(new Date(now))}
            </p>
          )}
        </div>
        <button className="button primary" onClick={() => setCreate(true)}>
          <Icon name="Plus" size={16} />
          New task
        </button>
      </header>
      <PlanningFeedback />
      <BackgroundRuns />
      {!work ? (
        !error && <p role="status">Loading today…</p>
      ) : (
        <>
          {focus && <CurrentTask task={focus} />}
          {(data?.date_items || []).some(
            (item) =>
              item.kind !== "availability" &&
              item.starts_on <= today &&
              item.ends_before > today,
          ) && (
            <section
              className="today-date-items"
              aria-label="All-day commitments"
            >
              <ul className="quiet-agenda">
                {(data?.date_items || [])
                  .filter(
                    (item) =>
                      item.kind !== "availability" &&
                      item.starts_on <= today &&
                      item.ends_before > today,
                  )
                  .map((item) => (
                    <li key={item.id}>
                      <span className="quiet-agenda-time">All day</span>
                      <Link className="quiet-agenda-title" href="/calendar">
                        <strong>{item.title}</strong>
                        <small>
                          {item.kind === "review"
                            ? "Review date"
                            : "Calendar date"}
                        </small>
                      </Link>
                    </li>
                  ))}
              </ul>
            </section>
          )}
          <section className="today-schedule" aria-labelledby="schedule-title">
            <div className="quiet-section-heading">
              <h2 id="schedule-title" tabIndex={-1}>
                Schedule
              </h2>
              <Link href="/calendar" className="text-link">
                Calendar
                <Icon name="ArrowUpRight" size={14} />
              </Link>
            </div>
            {work.schedule.length ? (
              <ol className="quiet-agenda">
                {work.schedule.slice(0, limit).map((item) => (
                  <li key={item.id}>
                    <div className="quiet-agenda-time">
                      <time dateTime={item.starts_at}>
                        {dateInZone(item.starts_at, timezone) < today
                          ? "Continues"
                          : wallTime(item.starts_at, timezone)}
                      </time>
                      <span>
                        {dateInZone(item.ends_at, timezone) > today
                          ? "Overnight"
                          : wallTime(item.ends_at, timezone)}
                      </span>
                    </div>
                    <button
                      className="quiet-agenda-title"
                      onClick={() =>
                        item.task
                          ? select(item.task.id)
                          : setEvent(item.event || null)
                      }
                    >
                      <strong>{item.title}</strong>
                      <small>
                        {item.task
                          ? item.task.template_id
                            ? "Routine"
                            : "Task"
                          : "Event"}
                      </small>
                    </button>
                    {item.task && item.task.id !== focus?.id && (
                      <button
                        className="button small-button"
                        aria-label={`Focus on ${item.title}`}
                        disabled={busy}
                        onClick={() => void choose(item.task!.id)}
                      >
                        Focus
                      </button>
                    )}
                  </li>
                ))}
              </ol>
            ) : (
              <p className="quiet-empty">Nothing scheduled today.</p>
            )}
            {work.schedule.length > limit && (
              <button
                className="text-link"
                onClick={() => setLimit((value) => value + 8)}
              >
                Show more scheduled items
              </button>
            )}
          </section>
          {work.due.length > 0 && (
            <section className="today-due" aria-labelledby="due-title">
              <div className="quiet-section-heading">
                <h2 id="due-title">Tasks for today</h2>
                <Link href="/tasks" className="text-link">
                  All tasks
                  <Icon name="ArrowUpRight" size={14} />
                </Link>
              </div>
              <ul className="quiet-agenda">
                {work.due.slice(0, limit).map((task) => (
                  <li key={task.id}>
                    <button
                      className="quiet-agenda-title"
                      onClick={() => select(task.id)}
                    >
                      <strong>{task.title}</strong>
                      <small>
                        {task.estimated_minutes} min estimate
                        {task.deadline_at
                          ? ` · Due ${wallTime(task.deadline_at, timezone)}`
                          : ""}
                      </small>
                    </button>
                    {task.id !== focus?.id && (
                      <button
                        className="button small-button"
                        aria-label={`Focus on ${task.title}`}
                        disabled={busy}
                        onClick={() => void choose(task.id)}
                      >
                        Focus
                      </button>
                    )}
                  </li>
                ))}
              </ul>
              {work.due.length > limit && (
                <button
                  className="text-link"
                  onClick={() => setLimit((value) => value + 8)}
                >
                  Show more due tasks
                </button>
              )}
            </section>
          )}
        </>
      )}
      <Modal open={create} onOpenChange={setCreate} title="New task">
        <TaskForm onSaved={() => setCreate(false)} />
      </Modal>
      <Modal
        open={!!event}
        onOpenChange={(open) => {
          if (!open) setEvent(null);
        }}
        title="Event"
      >
        {event && (
          <>
            <LinkedNoteContext
              kind="event"
              id={event.id}
              version={event.version}
            />
            <TimeForm
              key={event.id}
              event={event}
              onSaved={() => setEvent(null)}
            />
          </>
        )}
      </Modal>
    </div>
  );
}
