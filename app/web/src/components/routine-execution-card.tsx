"use client";
import {
  useEffect,
  useId,
  useState,
  type CSSProperties,
  type ReactNode,
} from "react";
import type {
  RoutineAction,
  RoutineDefinition,
  RoutineExecution,
} from "@/lib/routines";
import { Icon, Progress } from "./ui";

export type RoutineExecutionCardProps = {
  definition: RoutineDefinition;
  execution: RoutineExecution;
  onAction: (action: RoutineAction) => Promise<boolean>;
  pending?: boolean;
  error?: string;
  controls?: ReactNode;
  eyebrow?: string;
  statusLabel?: string;
};

/** Controlled UI: its host owns persistence, routing and clock decisions. */
export function RoutineExecutionCard({
  definition,
  execution,
  onAction,
  pending = false,
  error = "",
  controls,
  eyebrow = "SAMPLE ROUTINE",
  statusLabel,
}: RoutineExecutionCardProps) {
  const titleId = useId(),
    progressId = useId(),
    hintId = useId(),
    errorId = useId();
  const [draft, setDraft] = useState(String(execution.progress)),
    [validation, setValidation] = useState("");
  useEffect(() => {
    setDraft(String(execution.progress));
    setValidation("");
  }, [definition.id, definition.scheduledDate, execution.progress]);
  const inProgress = execution.status === "in_progress",
    completed = execution.status === "completed";
  const timestamp = (iso: string) =>
    new Intl.DateTimeFormat("en", {
      timeZone: definition.timezone,
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      hourCycle: "h23",
    }).format(new Date(iso));
  async function recordProgress(e: React.FormEvent) {
    e.preventDefault();
    if (pending) return;
    const percent = Number(draft);
    if (
      !draft.trim() ||
      !Number.isInteger(percent) ||
      percent < 0 ||
      percent > 100
    ) {
      setValidation("Enter a whole-number percentage from 0 to 100.");
      return;
    }
    setValidation("");
    await onAction({ type: "progress", percent });
  }
  const shownError = validation || error;
  return (
    <section
      className="panel routine-card"
      aria-labelledby={titleId}
      aria-busy={pending}
      style={
        {
          "--routine-accent": completed ? "#69dbaa" : "#91b4f3",
        } as CSSProperties
      }
    >
      <div className="routine-heading">
        <div className="routine-heading-title">
          <span className="routine-symbol">
            <Icon name={completed ? "CircleCheck" : "BookOpen"} size={21} />
          </span>
          <div>
            <span className="routine-eyebrow">{eyebrow}</span>
            <h2 id={titleId}>{definition.title}</h2>
          </div>
        </div>
        <span
          className={`routine-status ${completed ? "completed" : ""}`}
          role="status"
        >
          {pending
            ? "Saving…"
            : statusLabel ||
              (completed
                ? "Completed"
                : inProgress
                  ? "In progress"
                  : "Ready to begin")}
        </span>
      </div>
      <div className="routine-layout">
        <div className="routine-definition">
          <span className="routine-goal-label">
            <Icon name="BookmarkPlus" size={13} />
            Fixed goal
          </span>
          <p className="routine-goal">{definition.goal}</p>
          {definition.description && (
            <p className="muted">{definition.description}</p>
          )}
          <dl className="routine-metadata">
            <div>
              <dt>Scheduled window</dt>
              <dd>
                <time
                  dateTime={`${definition.scheduledDate}T${definition.windowStart}`}
                >
                  {definition.windowStart}
                </time>{" "}
                –{" "}
                <time
                  dateTime={`${definition.scheduledDate}T${definition.windowEnd}`}
                >
                  {definition.windowEnd}
                </time>
              </dd>
              <dd className="routine-date">
                {new Intl.DateTimeFormat("en", {
                  month: "short",
                  day: "numeric",
                  year: "numeric",
                  timeZone: "UTC",
                }).format(
                  new Date(`${definition.scheduledDate}T12:00:00Z`),
                )}{" "}
                · {definition.timezone}
              </dd>
            </div>
            <div>
              <dt>Expected duration</dt>
              <dd>{definition.expectedMinutes} min</dd>
            </div>
          </dl>
        </div>
        <div className="routine-execution">
          <div className="routine-progress-label">
            <span>Reported progress</span>
            <strong>{execution.progress}%</strong>
          </div>
          <Progress
            label={`${definition.title} reported progress`}
            value={execution.progress}
            color={completed ? "#69dbaa" : "#91b4f3"}
          />
          <p id={hintId} className="routine-progress-hint">
            Self-reported progress · duration is an estimate.
          </p>
          {controls || (
            <>
              {execution.status === "not_started" && (
                <button
                  className="button primary routine-start"
                  onClick={() => void onAction({ type: "start" })}
                  disabled={pending}
                >
                  <Icon name="ArrowRight" size={16} />
                  Start routine
                </button>
              )}
              {inProgress && (
                <div className="routine-controls">
                  <form onSubmit={recordProgress} noValidate>
                    <label htmlFor={progressId}>Progress (%)</label>
                    <div className="routine-progress-input">
                      <input
                        id={progressId}
                        type="number"
                        inputMode="numeric"
                        min={0}
                        max={100}
                        step={1}
                        required
                        value={draft}
                        disabled={pending}
                        aria-describedby={`${hintId}${shownError ? ` ${errorId}` : ""}`}
                        aria-invalid={!!validation}
                        onChange={(e) => {
                          setDraft(e.target.value);
                          setValidation("");
                        }}
                      />
                      <button
                        className="button"
                        type="submit"
                        disabled={pending}
                      >
                        Save progress
                      </button>
                    </div>
                  </form>
                  <button
                    className="button primary"
                    disabled={pending}
                    onClick={() => void onAction({ type: "complete" })}
                  >
                    <Icon name="Check" size={15} />
                    Complete routine
                  </button>
                </div>
              )}
              {completed && (
                <p className="routine-finished">
                  <Icon name="CircleCheck" size={16} />
                  Goal marked complete.
                </p>
              )}
            </>
          )}
          {shownError && (
            <p id={errorId} className="error routine-error" role="alert">
              {shownError}
            </p>
          )}
          <div className="routine-execution-times">
            {execution.startedAt && (
              <span>
                Started{" "}
                <time dateTime={execution.startedAt}>
                  {timestamp(execution.startedAt)}
                </time>
              </span>
            )}
            {execution.completedAt ? (
              <span>
                Completed{" "}
                <time dateTime={execution.completedAt}>
                  {timestamp(execution.completedAt)}
                </time>
              </span>
            ) : (
              execution.progressHistory.length > 0 &&
              execution.updatedAt && (
                <span>
                  Progress saved{" "}
                  <time dateTime={execution.updatedAt}>
                    {timestamp(execution.updatedAt)}
                  </time>
                </span>
              )
            )}
          </div>
        </div>
      </div>
    </section>
  );
}
