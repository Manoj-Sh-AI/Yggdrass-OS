import type { PlanningTask } from "./planning";

export const boardColumns = [
  { id: "todo", title: "To do", color: "#c0cbd0" },
  { id: "in_progress", title: "In progress", color: "#ddc38f" },
  { id: "paused", title: "Paused", color: "#c4bacb" },
  { id: "completed", title: "Done", color: "#b8cba8" },
] as const;
export type BoardState = (typeof boardColumns)[number]["id"];
export type BoardAction = "start" | "resume" | "pause" | "complete" | "reopen";
export type MovePlan =
  | { kind: "none" }
  | { kind: "invalid"; message: string }
  | { kind: "execute"; action: BoardAction; confirmation?: "timer" | "reset" };

export function isBoardState(value: unknown): value is BoardState {
  return boardColumns.some((column) => column.id === value);
}
export function planBoardMove(
  task: PlanningTask,
  target: BoardState,
): MovePlan {
  const current = task.done ? "completed" : task.state;
  if (current === "skipped")
    return {
      kind: "invalid",
      message: "Manage skipped occurrences from Routines.",
    };
  if (current === target) return { kind: "none" };
  if (target === "todo")
    return { kind: "execute", action: "reopen", confirmation: "reset" };
  if (target === "in_progress") {
    if (current === "completed")
      return {
        kind: "invalid",
        message: "Return this task to To do before starting it again.",
      };
    return {
      kind: "execute",
      action: current === "paused" ? "resume" : "start",
      confirmation: "timer",
    };
  }
  if (target === "paused")
    return current === "in_progress"
      ? { kind: "execute", action: "pause" }
      : { kind: "invalid", message: "Only a running task can be paused." };
  return { kind: "execute", action: "complete" };
}
export function groupBoardTasks(
  tasks: PlanningTask[],
  overrides: Record<string, BoardState> = {},
) {
  const groups: Record<BoardState, PlanningTask[]> = {
    todo: [],
    in_progress: [],
    paused: [],
    completed: [],
  };
  for (const task of tasks) {
    const state = overrides[task.id] || (task.done ? "completed" : task.state);
    if (isBoardState(state)) groups[state].push(task);
  }
  return groups;
}
export const BOARD_BATCH = 40;
