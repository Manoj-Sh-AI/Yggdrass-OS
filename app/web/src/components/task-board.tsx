"use client";
import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
} from "react";
import {
  DragDropProvider,
  DragOverlay,
  useDraggable,
  useDroppable,
} from "@dnd-kit/react";
import { areaOf } from "@/lib/data";
import type { PlanningTask } from "@/lib/planning";
import {
  BOARD_BATCH,
  boardColumns,
  groupBoardTasks,
  isBoardState,
  planBoardMove,
  type BoardState,
  type MovePlan,
} from "@/lib/kanban";
import { usePlanning } from "./planning-provider";
import { useApp } from "./provider";
import { Icon, Modal, rememberFocus } from "./ui";

type Confirmation = {
  task: PlanningTask;
  target: BoardState;
  plan: Extract<MovePlan, { kind: "execute" }>;
};
type Move = {
  id: string;
  target: BoardState;
  baseVersion: number;
  saved: boolean;
};

function Card({
  task,
  state,
  goal,
  blocked,
  moving,
  requestMove,
  open,
}: {
  task: PlanningTask;
  state: BoardState;
  goal?: string;
  blocked: boolean;
  moving?: Move | null;
  requestMove: (task: PlanningTask, target: BoardState) => void;
  open: () => void;
}) {
  const { ref, handleRef, isDragSource } = useDraggable({
    id: task.id,
    type: "task",
    data: { taskId: task.id },
    disabled: blocked,
  });
  const area = areaOf(task.area);
  const pending = moving?.id === task.id;
  return (
    <article
      ref={ref}
      className={`kanban-card ${isDragSource ? "drag-source" : ""} ${pending ? "moving" : ""}`}
      role="listitem"
      aria-label={task.title}
      aria-busy={pending || undefined}
    >
      <div className="kanban-card-top">
        <span
          className="kanban-area"
          style={{ "--area-color": area.color } as CSSProperties}
        >
          <i />
          {area.name}
        </span>
        <button
          ref={handleRef}
          className="kanban-drag"
          aria-label={`Drag ${task.title}`}
          disabled={blocked}
          title="Drag to another column"
        >
          <Icon name="Menu" size={14} />
        </button>
      </div>
      <button
        className="kanban-open"
        id={`kanban-open-${task.id}`}
        aria-label={`Open ${task.title}`}
        onClick={open}
      >
        <strong>{task.title}</strong>
        {task.objective !== task.title && <span>{task.objective}</span>}
      </button>
      {goal && (
        <div className="kanban-goal">
          <Icon name="CornerDownRight" size={12} />
          {goal}
        </div>
      )}
      <div className="kanban-meta">
        <span className={`priority p${task.priority}`}>
          <i />
          {task.priority === 1
            ? "High"
            : task.priority === 2
              ? "Medium"
              : "Low"}
        </span>
        <span>{task.estimated_minutes} min</span>
        {(task.due_date || task.occurrence_date) && (
          <span className="kanban-due">
            <Icon name="Calendar" size={12} />
            {new Date(
              (task.due_date || task.occurrence_date) + "T12:00:00Z",
            ).toLocaleDateString("en", {
              month: "short",
              day: "numeric",
              timeZone: "UTC",
            })}
          </span>
        )}
      </div>
      {task.tags.length > 0 && (
        <div className="kanban-tags">
          {task.tags.slice(0, 2).map((tag) => (
            <span key={tag}>{tag}</span>
          ))}
          {task.tags.length > 2 && <span>+{task.tags.length - 2}</span>}
        </div>
      )}
      {task.progress > 0 && state !== "completed" && (
        <div
          className="kanban-progress"
          role="progressbar"
          aria-label={`${task.title} progress`}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={task.progress}
        >
          <i style={{ width: `${task.progress}%` }} />
        </div>
      )}
      <div className="kanban-card-bottom">
        <span>
          {pending
            ? moving.saved
              ? "Saved · refreshing"
              : "Saving move…"
            : state === "completed"
              ? "Completed"
              : task.progress
                ? `${task.progress}% complete`
                : ""}
        </span>
        <label>
          <span className="sr-only">Move task</span>
          <select
            aria-label={`Move ${task.title}`}
            value={state}
            disabled={blocked}
            onChange={(event) => {
              event.currentTarget.focus();
              if (isBoardState(event.target.value))
                requestMove(task, event.target.value);
            }}
          >
            <option value={state}>
              {boardColumns.find((c) => c.id === state)!.title}
            </option>
            {boardColumns
              .filter((c) => c.id !== state)
              .map((column) => (
                <option
                  key={column.id}
                  value={column.id}
                  disabled={planBoardMove(task, column.id).kind === "invalid"}
                >
                  {column.title}
                </option>
              ))}
          </select>
        </label>
      </div>
    </article>
  );
}
function Column({
  column,
  tasks,
  count,
  limit,
  blocked,
  moving,
  goalNames,
  requestMove,
  open,
  more,
}: {
  column: (typeof boardColumns)[number];
  tasks: PlanningTask[];
  count: number;
  limit: number;
  blocked: boolean;
  moving: Move | null;
  goalNames: Map<string, string>;
  requestMove: (task: PlanningTask, target: BoardState) => void;
  open: (id: string) => void;
  more: () => void;
}) {
  const { ref, isDropTarget } = useDroppable({
    id: column.id,
    type: "task-column",
    accept: "task",
    disabled: blocked,
  });
  return (
    <section
      ref={ref}
      className={`kanban-column ${isDropTarget ? "drop-target" : ""}`}
      aria-label={`${column.title} column`}
      style={{ "--column-color": column.color } as CSSProperties}
    >
      <header>
        <h3>
          <i />
          {column.title}
        </h3>
        <span>{count}</span>
      </header>
      <div
        className="kanban-cards"
        role="list"
        aria-label={`${column.title} tasks`}
      >
        {tasks.slice(0, limit).map((task) => (
          <Card
            key={task.id}
            task={task}
            state={column.id}
            goal={
              goalNames.get(task.goal_id || "") ||
              goalNames.get(task.project_id || "")
            }
            blocked={blocked}
            moving={moving}
            requestMove={requestMove}
            open={() => open(task.id)}
          />
        ))}
        {!count && <p className="kanban-empty">No tasks here</p>}
        {count > limit && (
          <button className="kanban-more" onClick={more}>
            Show {Math.min(BOARD_BATCH, count - limit)} more{" "}
            <span>
              {limit} of {count}
            </span>
          </button>
        )}
      </div>
    </section>
  );
}
export function TaskBoard({ tasks }: { tasks: PlanningTask[] }) {
  const { data, busy, run, select, refresh } = usePlanning();
  const { state } = useApp();
  const [confirmation, setConfirmation] = useState<Confirmation | null>(null);
  const [move, setMove] = useState<Move | null>(null);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [limits, setLimits] = useState<Record<BoardState, number>>({
    todo: BOARD_BATCH,
    in_progress: BOARD_BATCH,
    paused: BOARD_BATCH,
    completed: BOARD_BATCH,
  });
  const [snapshot, setSnapshot] = useState<PlanningTask[] | null>(null);
  const dragSnapshot = useRef<PlanningTask[]>([]);
  const lock = useRef(false);
  const [systemQuiet, setSystemQuiet] = useState(false);
  useEffect(() => {
    const media = matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setSystemQuiet(media.matches);
    update();
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);
  useEffect(() => {
    if (!move || !data) return;
    const current = data.tasks.find((task) => task.id === move.id);
    if (
      current &&
      (current.version > move.baseVersion ||
        (current.done ? "completed" : current.state) === move.target)
    )
      setMove(null);
  }, [data, move]);
  const overrides = useMemo(
    () => (move ? { [move.id]: move.target } : {}),
    [move],
  );
  const groups = useMemo(
    () => groupBoardTasks(snapshot || tasks, overrides),
    [snapshot, tasks, overrides],
  );
  const goalNames = useMemo(
    () =>
      new Map(
        [...(data?.goals || []), ...(data?.projects || [])].map((group) => [
          group.id,
          group.title,
        ]),
      ),
    [data?.goals, data?.projects],
  );
  const blocked = busy || !!move;
  const focusTask = (id: string) =>
    requestAnimationFrame(() => {
      (
        document.getElementById(`kanban-open-${id}`) ||
        document.getElementById("kanban-workspace")
      )?.focus();
    });
  async function execute(
    task: PlanningTask,
    target: BoardState,
    plan: Extract<MovePlan, { kind: "execute" }>,
  ) {
    if (lock.current || busy || move) return;
    lock.current = true;
    setError("");
    setNotice(`Moving “${task.title}”…`);
    setMove({ id: task.id, target, baseVersion: task.version, saved: false });
    try {
      await run("task.execute", { action: plan.action }, task.id, task.version);
      setMove((current) => (current ? { ...current, saved: true } : null));
      setNotice(
        `“${task.title}” saved in ${boardColumns.find((column) => column.id === target)!.title}.`,
      );
    } catch (failure) {
      setMove(null);
      setNotice("");
      setError(
        failure instanceof Error
          ? failure.message
          : "The move could not be saved. The card has been returned.",
      );
    } finally {
      lock.current = false;
      focusTask(task.id);
    }
  }
  function requestMove(task: PlanningTask, target: BoardState) {
    if (lock.current || busy || move) return;
    const plan = planBoardMove(task, target);
    if (plan.kind === "none") return;
    if (plan.kind === "invalid") {
      setError(plan.message);
      return;
    }
    setError("");
    if (plan.confirmation) {
      rememberFocus();
      setConfirmation({ task, target, plan });
    } else void execute(task, target, plan);
  }
  return (
    <div className="kanban-workspace" id="kanban-workspace" tabIndex={-1}>
      <div className="kanban-feedback" role="status" aria-live="polite">
        {notice}
      </div>
      {error && (
        <div className="kanban-error" role="alert">
          {error}
          <button
            className="text-link"
            onClick={() =>
              void refresh()
                .then(() => setError(""))
                .catch(() =>
                  setError("The board could not refresh. Please try again."),
                )
            }
          >
            Refresh board
          </button>
        </div>
      )}
      {move?.saved && (
        <p className="kanban-refresh">
          The move was saved. Refresh the board to load the latest view.
          <button
            className="text-link"
            onClick={() =>
              void refresh().catch(() =>
                setError("The move is saved, but the board could not refresh."),
              )
            }
          >
            Refresh board
          </button>
        </p>
      )}
      <p className="kanban-touch-hint">
        Swipe across columns, or use a card’s move menu.
      </p>
      <DragDropProvider
        onDragStart={() => {
          dragSnapshot.current = tasks;
          setSnapshot(tasks);
          setNotice("");
        }}
        onDragEnd={(event) => {
          const { source, target } = event.operation;
          const task = dragSnapshot.current.find(
            (task) => task.id === source?.id,
          );
          setSnapshot(null);
          if (event.canceled) {
            setNotice("Move cancelled.");
            return;
          }
          if (task && target && isBoardState(target.id))
            requestMove(task, target.id);
        }}
      >
        <div className="kanban-scroll">
          <div className="kanban-columns">
            {boardColumns.map((column) => (
              <Column
                key={column.id}
                column={column}
                tasks={groups[column.id]}
                count={groups[column.id].length}
                limit={limits[column.id]}
                blocked={blocked}
                moving={move}
                goalNames={goalNames}
                requestMove={requestMove}
                open={select}
                more={() =>
                  setLimits((current) => ({
                    ...current,
                    [column.id]: current[column.id] + BOARD_BATCH,
                  }))
                }
              />
            ))}
          </div>
        </div>
        <DragOverlay
          dropAnimation={
            systemQuiet || state.preferences.reducedMotion
              ? null
              : { duration: 160, easing: "cubic-bezier(.2,.8,.2,1)" }
          }
        >
          {(source) => {
            const task = (snapshot || tasks).find(
              (task) => task.id === source.id,
            );
            return task ? (
              <div className="kanban-drag-preview">
                <Icon name="Menu" size={15} />
                <span>{task.title}</span>
              </div>
            ) : null;
          }}
        </DragOverlay>
      </DragDropProvider>
      <Modal
        open={!!confirmation}
        onOpenChange={(open) => {
          if (!open) setConfirmation(null);
        }}
        title={
          confirmation?.plan.confirmation === "reset"
            ? "Return this task to To do?"
            : confirmation?.plan.action === "resume"
              ? "Resume the focus timer?"
              : "Start the focus timer?"
        }
        description={
          confirmation?.plan.confirmation === "reset"
            ? "This stops any running timer and resets progress. The original outcome and history stay unchanged."
            : "Moving into In progress starts time tracking. Your original outcome stays unchanged."
        }
      >
        {confirmation && (
          <div className="kanban-confirm">
            <h3>{confirmation.task.title}</h3>
            <p className="kanban-objective">{confirmation.task.objective}</p>
            <p className="muted">
              {confirmation.task.estimated_minutes} minute estimate ·{" "}
              {confirmation.task.progress}% progress
            </p>
            <div className="modal-actions">
              <button className="button" onClick={() => setConfirmation(null)}>
                Cancel move
              </button>
              <button
                className="button primary"
                disabled={busy}
                onClick={() => {
                  const next = confirmation;
                  setConfirmation(null);
                  void execute(next.task, next.target, next.plan);
                }}
              >
                {confirmation.plan.confirmation === "reset"
                  ? "Return to To do"
                  : confirmation.plan.action === "resume"
                    ? "Resume timer"
                    : "Start timer"}
              </button>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}
