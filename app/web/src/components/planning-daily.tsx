"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import {
  addDays,
  dateInZone,
  wallTime,
  onLocalDay,
  type PlanningTask,
} from "@/lib/planning";
import { usePlanning, usePlanningClock } from "./planning-provider";
import {
  CommandButton,
  FocusControls,
  PlanningFeedback,
  TaskRow,
} from "./planning-ui";
import { Icon, Panel, Progress } from "./ui";
import { RoutineExecutionCard } from "./routine-execution-card";
import { planningTabsKeyDown } from "@/lib/planning-accessibility";

export function Capacity({ day }: { day: string }) {
  const { data, timezone } = usePlanning();
  const summary = data?.summaries.find((s) => s.day === day),
    plan = data?.plans.find((p) => p.day === day && p.timezone === timezone);
  const scheduled =
      (summary?.scheduled_minutes || 0) + (summary?.event_minutes || 0),
    available = plan?.available_minutes;
  return (
    <div className="planning-capacity">
      <div>
        <span>Daily capacity</span>
        <strong>
          {Math.round(scheduled)} min planned
          {available !== undefined
            ? ` / ${available} available`
            : " · set your availability"}
        </strong>
      </div>
      <Progress
        label={`${day} planned workload`}
        value={
          available
            ? Math.min(100, (scheduled / available) * 100)
            : scheduled
              ? 100
              : 0
        }
        color={
          available !== undefined && scheduled > available
            ? "#f2b465"
            : "#75d9b5"
        }
      />
      <small>
        {Math.round(summary?.scheduled_minutes || 0)} min task blocks ·{" "}
        {Math.round(summary?.event_minutes || 0)} min fixed events ·{" "}
        {summary?.estimated_minutes || 0} min estimated task effort
      </small>
      {available !== undefined && scheduled > available && (
        <p role="status" className="planning-warning">
          {Math.round(scheduled - available)} min over your capacity. Choose
          what to move; all commitments are preserved.
        </p>
      )}
    </div>
  );
}
export function DailyPlanning({ compact = false }: { compact?: boolean }) {
  const { data, day, timezone, run, busy, select } = usePlanning();
  const [mode, setMode] = useState<"plan" | "review">("plan");
  const plan = data?.plans.find(
    (p) => p.day === day && p.timezone === timezone,
  );
  const summary = data?.summaries.find((s) => s.day === day);
  const tasks =
    data?.tasks.filter(
      (t) =>
        !t.done &&
        t.state !== "skipped" &&
        (t.due_date === day ||
          data.blocks.some(
            (b) => b.task_id === t.id && onLocalDay(b, day, timezone),
          )),
    ) || [];
  const leftovers =
    data?.tasks.filter(
      (t) =>
        !t.done &&
        t.state !== "skipped" &&
        ((t.due_date && t.due_date < day) ||
          data.blocks.some(
            (b) => b.task_id === t.id && dateInZone(b.ends_at, timezone) < day,
          )),
    ) || [];
  const events =
    data?.events.filter((e) => dateInZone(e.starts_at, timezone) === day) || [];
  const week =
    data?.summaries.filter((s) => s.day >= addDays(day, -6) && s.day <= day) ||
    [];
  return (
    <Panel
      className="planning-daily"
      title={compact ? "Make room for today" : "Daily planning & review"}
      action={
        compact ? (
          <Link className="text-link" href="/tasks?tab=plan">
            Open planner
          </Link>
        ) : undefined
      }
    >
      <Capacity day={day} />
      {!compact && (
        <div
          className="planning-tabs"
          role="tablist"
          aria-label="Daily ritual"
          onKeyDown={planningTabsKeyDown}
        >
          <button
            role="tab"
            tabIndex={mode === "plan" ? 0 : -1}
            aria-selected={mode === "plan"}
            onClick={() => setMode("plan")}
          >
            Morning plan
          </button>
          <button
            role="tab"
            tabIndex={mode === "review" ? 0 : -1}
            aria-selected={mode === "review"}
            onClick={() => setMode("review")}
          >
            Evening review
          </button>
        </div>
      )}
      <div className="planning-summary-grid">
        <div>
          <strong>{summary?.completed || 0}</strong>
          <span>completed today</span>
        </div>
        <div>
          <strong>{Math.round(summary?.actual_minutes || 0)}m</strong>
          <span>actual focus time</span>
        </div>
        <div>
          <strong>{tasks.length}</strong>
          <span>unfinished today</span>
        </div>
        <div>
          <strong>{leftovers.length}</strong>
          <span>earlier commitments</span>
        </div>
      </div>
      {!compact && (
        <>
          <DailyForm key={day + timezone} day={day} mode={mode} />
          <h3 className="section-label">
            {mode === "plan"
              ? "Today’s priorities & routines"
              : "Work still open · choose its next window"}
          </h3>
          {tasks.map((t) => (
            <TaskRow key={t.id} task={t} />
          ))}
          {events.map((e) => (
            <div className="planning-review-line" key={e.id}>
              <span>Fixed event · {e.title}</span>
              <small>
                {wallTime(e.starts_at, timezone)}–
                {wallTime(e.ends_at, timezone)}
              </small>
            </div>
          ))}
          {leftovers.length > 0 && (
            <details>
              <summary>
                {leftovers.length} earlier commitments · manual rollover
              </summary>
              {leftovers.slice(0, 30).map((t) => (
                <button
                  className="planning-related"
                  key={t.id}
                  onClick={() => select(t.id)}
                >
                  {t.title}
                  <small>Open to schedule another execution block</small>
                </button>
              ))}
            </details>
          )}
          {mode === "review" && (
            <>
              <h3 className="section-label">
                Completed today · estimate versus actual task time
              </h3>
              {data?.tasks
                .filter(
                  (t) =>
                    t.completed_at &&
                    dateInZone(t.completed_at, timezone) === day,
                )
                .map((t) => (
                  <div className="planning-review-line" key={t.id}>
                    <button className="text-link" onClick={() => select(t.id)}>
                      {t.title}
                    </button>
                    <small>
                      {t.estimated_minutes} min estimated /{" "}
                      {Math.round(t.actual_seconds / 60)} min actual
                    </small>
                  </div>
                ))}
              <p className="muted">
                Unfinished work is context for your next plan. It stays
                available until you choose what comes next.
              </p>
              <h3 className="section-label">Last seven days</h3>
              <div className="planning-review-line">
                <span>
                  {week.reduce((n, s) => n + s.completed, 0)} tasks completed
                </span>
                <span>
                  {Math.round(week.reduce((n, s) => n + s.actual_minutes, 0))}{" "}
                  min actual /{" "}
                  {Math.round(
                    week.reduce((n, s) => n + s.scheduled_minutes, 0),
                  )}{" "}
                  min planned task time
                </span>
              </div>
            </>
          )}
          <ReminderReadiness />
        </>
      )}
      {compact && tasks.length === 0 && (
        <p className="muted">
          Capture an intention or schedule something from{" "}
          <Link href="/tasks">Tasks</Link>.
        </p>
      )}
      {compact && (
        <p className="muted">
          {plan?.confirmed_at
            ? "Your daily plan is confirmed."
            : "Review your workload and set availability in the planner."}{" "}
          Energy stays yours to report; automatic adaptation is off.
        </p>
      )}
    </Panel>
  );
}
function ReminderReadiness() {
  const { data, day, timezone, run, select } = usePlanning();
  const now = usePlanningClock();
  const requests =
    data?.reminders
      .filter((r) => dateInZone(r.eligible_at, timezone) <= addDays(day, 1))
      .slice(0, 12) || [];
  return (
    <details>
      <summary>Deadline & start readiness · {requests.length} requests</summary>
      <p className="muted">
        Planning records only. No notifications or calls are delivered.
        Acknowledgment is recorded in PostgreSQL.
      </p>
      {requests.map((r) => {
        const task = data!.tasks.find((t) => t.id === r.task_id),
          block = data!.blocks.find((b) => b.id === r.block_id);
        const missed =
          block &&
          Date.parse(block.ends_at) < now &&
          !data!.sessions.some((s) => s.block_id === block.id);
        return (
          <div className="planning-review-line" key={r.id}>
            <button className="text-link" onClick={() => select(r.task_id)}>
              {task?.title} ·{" "}
              {r.kind === "deadline"
                ? Date.parse(r.eligible_at) < now
                  ? "Overdue deadline"
                  : "Upcoming deadline"
                : missed
                  ? "Unstarted execution window"
                  : "Scheduled task start"}
            </button>
            <CommandButton
              className="button small-button"
              action={() => run("reminder.ack", { reminder_id: r.id })}
            >
              Acknowledge
            </CommandButton>
          </div>
        );
      })}
      {!requests.length && (
        <p className="muted">No pending readiness records for this period.</p>
      )}
    </details>
  );
}
function DailyForm({ day, mode }: { day: string; mode: "plan" | "review" }) {
  const { data, timezone, run, busy } = usePlanning();
  const initial = data?.plans.find(
    (p) => p.day === day && p.timezone === timezone,
  );
  const [baseVersion, setBaseVersion] = useState(initial?.version),
    [available, setAvailable] = useState(initial?.available_minutes ?? 0),
    [energy, setEnergy] = useState(initial?.energy || ""),
    [focus, setFocus] = useState(initial?.focus || ""),
    [sleep, setSleep] = useState(initial?.sleep || ""),
    [intention, setIntention] = useState(initial?.intention || ""),
    [reflection, setReflection] = useState(initial?.reflection || ""),
    [error, setError] = useState("");
  return (
    <form
      className="form-stack planning-form"
      onSubmit={async (e) => {
        e.preventDefault();
        setError("");
        try {
          await run(
            "daily.save",
            {
              day,
              timezone,
              available_minutes: available,
              energy,
              focus,
              sleep,
              intention,
              reflection,
              confirm: mode === "plan",
              review: mode === "review",
            },
            undefined,
            baseVersion,
          );
          setBaseVersion((baseVersion || 0) + 1);
        } catch (e) {
          setError((e as Error).message);
        }
      }}
    >
      <div className="form-row">
        <label>
          Available time (minutes)
          <input
            type="number"
            min={0}
            max={1440}
            required
            value={available}
            onChange={(e) => setAvailable(Number(e.target.value))}
          />
        </label>
        <label>
          Energy · optional
          <select value={energy} onChange={(e) => setEnergy(e.target.value)}>
            <option value="">Prefer not to report</option>
            <option>Low</option>
            <option>Steady</option>
            <option>High</option>
            <option>Variable</option>
          </select>
        </label>
      </div>
      <details>
        <summary>Optional focus and sleep context</summary>
        <label>
          Focus / attention
          <input
            maxLength={100}
            value={focus}
            onChange={(e) => setFocus(e.target.value)}
            placeholder="How is your attention today?"
          />
        </label>
        <label>
          Sleep context
          <input
            maxLength={200}
            value={sleep}
            onChange={(e) => setSleep(e.target.value)}
            placeholder="Only what you choose to share"
          />
        </label>
        <p className="muted">
          Stored only as application planning context. It does not trigger
          health assumptions or automatic decisions.
        </p>
      </details>
      {mode === "plan" ? (
        <label>
          Today’s intention
          <textarea
            maxLength={2000}
            value={intention}
            onChange={(e) => setIntention(e.target.value)}
          />
        </label>
      ) : (
        <label>
          Evening reflection
          <textarea
            maxLength={2000}
            value={reflection}
            onChange={(e) => setReflection(e.target.value)}
          />
        </label>
      )}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <button className="button primary" disabled={busy}>
        {mode === "plan" ? "Confirm daily plan" : "Save evening review"}
      </button>
    </form>
  );
}

export function TodayPlanning() {
  const { data, setDay, timezone, select } = usePlanning();
  const today = dateInZone(new Date(), timezone);
  useEffect(() => setDay(today), [setDay, today]);
  const routines =
    data?.tasks.filter(
      (t) =>
        t.template_id && t.occurrence_date === today && t.state !== "skipped",
    ) || [];
  return (
    <div className="today-planning">
      <PlanningFeedback />
      <DailyPlanning compact />
      {routines.slice(0, 6).map((task) => (
        <OccurrenceCard key={task.id} task={task} />
      ))}
      {routines.length > 6 && (
        <Link className="text-link" href="/tasks">
          View all {routines.length} routines
        </Link>
      )}
    </div>
  );
}
export function OccurrenceCard({ task }: { task: PlanningTask }) {
  const { data, run, busy, select } = usePlanning();
  const template = data?.routines.find((r) => r.id === task.template_id);
  if (!template) return null;
  const first = data?.sessions.find((s) => s.task_id === task.id);
  return (
    <RoutineExecutionCard
      eyebrow={template.essential ? "ESSENTIAL ROUTINE" : "RECURRING ROUTINE"}
      statusLabel={task.state === "paused" ? "Paused" : undefined}
      definition={{
        id: task.id,
        title: task.title,
        description: task.description,
        goal: task.objective,
        scheduledDate: task.occurrence_date!,
        windowStart: (task.routine_window_start || template.window_start).slice(
          0,
          5,
        ),
        windowEnd: (task.routine_window_end || template.window_end).slice(0, 5),
        timezone: task.timezone,
        expectedMinutes: task.estimated_minutes,
      }}
      execution={{
        status: task.done
          ? "completed"
          : task.state === "todo"
            ? "not_started"
            : "in_progress",
        progress: task.progress,
        startedAt: first?.started_at || null,
        completedAt: task.completed_at,
        updatedAt: task.updated_at,
        progressHistory: [],
      }}
      pending={busy}
      onAction={async (action) => {
        try {
          await run(
            "task.execute",
            {
              action: action.type === "progress" ? "progress" : action.type,
              ...("percent" in action ? { percent: action.percent } : {}),
            },
            task.id,
            task.version,
          );
          return true;
        } catch {
          return false;
        }
      }}
      controls={
        <>
          <FocusControls task={task} />
          <button className="text-link" onClick={() => select(task.id)}>
            Progress, scheduling & history{" "}
            <Icon name="ArrowUpRight" size={13} />
          </button>
        </>
      }
    />
  );
}
