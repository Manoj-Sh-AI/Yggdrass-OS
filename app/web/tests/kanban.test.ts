import { describe, expect, it } from "vitest";
import type { PlanningTask } from "../src/lib/planning";
import {
  BOARD_BATCH,
  boardColumns,
  groupBoardTasks,
  isBoardState,
  planBoardMove,
} from "../src/lib/kanban";
const task = (overrides: Partial<PlanningTask> = {}): PlanningTask => ({
  id: "invented-task",
  title: "A synthetic commitment",
  objective: "Keep this outcome exactly.",
  description: "",
  area: "work",
  due_date: null,
  deadline_at: null,
  timezone: "Europe/Berlin",
  priority: 2,
  estimated_minutes: 25,
  effort: "medium",
  tags: [],
  goal_id: null,
  project_id: null,
  parent_id: null,
  template_id: null,
  occurrence_date: null,
  occurrence_edited: false,
  routine_window_start: null,
  routine_window_end: null,
  state: "todo",
  progress: 0,
  done: false,
  completed_at: null,
  version: 7,
  actual_seconds: 0,
  next_scheduled_at: null,
  last_scheduled_end: null,
  scheduled_block_count: 0,
  created_at: "2030-01-01T00:00:00Z",
  updated_at: "2030-01-01T00:00:00Z",
  ...overrides,
});
describe("Kanban execution boundaries", () => {
  it("requires explicit timing confirmation for both start and resume", () => {
    expect(planBoardMove(task(), "in_progress")).toEqual({
      kind: "execute",
      action: "start",
      confirmation: "timer",
    });
    expect(
      planBoardMove(task({ state: "paused", progress: 45 }), "in_progress"),
    ).toEqual({ kind: "execute", action: "resume", confirmation: "timer" });
  });
  it("does not pause work that never started, or silently restart completed work", () => {
    expect(planBoardMove(task(), "paused").kind).toBe("invalid");
    expect(
      planBoardMove(
        task({ done: true, state: "completed", progress: 100 }),
        "in_progress",
      ).kind,
    ).toBe("invalid");
  });
  it("warns about the progress reset before any return to To do", () => {
    for (const state of ["in_progress", "paused", "completed"] as const)
      expect(
        planBoardMove(
          task({ state, done: state === "completed", progress: 64 }),
          "todo",
        ),
      ).toEqual({ kind: "execute", action: "reopen", confirmation: "reset" });
  });
  it("reuses pause and complete actions without inventing an execution state", () => {
    expect(planBoardMove(task({ state: "in_progress" }), "paused")).toEqual({
      kind: "execute",
      action: "pause",
    });
    expect(planBoardMove(task(), "completed")).toEqual({
      kind: "execute",
      action: "complete",
    });
    expect(planBoardMove(task(), "todo")).toEqual({ kind: "none" });
    expect(planBoardMove(task({ state: "skipped" }), "todo").kind).toBe(
      "invalid",
    );
    expect(isBoardState("blocked")).toBe(false);
  });
  it("moves only the visual grouping while preserving the original goal and version", () => {
    const original = task({ progress: 23 });
    const before = JSON.stringify(original);
    const groups = groupBoardTasks([original], { [original.id]: "completed" });
    expect(groups.completed[0]).toBe(original);
    expect(JSON.stringify(original)).toBe(before);
    expect(groups.todo).toHaveLength(0);
  });
  it("counts 10,000 tasks accurately while the first visible batch stays bounded", () => {
    const items = Array.from({ length: 10000 }, (_, i) =>
      task({
        id: `synthetic-${i}`,
        state: boardColumns[i % 4].id,
        done: i % 4 === 3,
      }),
    );
    const groups = groupBoardTasks(items);
    expect(Object.values(groups).map((group) => group.length)).toEqual([
      2500, 2500, 2500, 2500,
    ]);
    expect(
      Object.values(groups).flatMap((group) => group.slice(0, BOARD_BATCH)),
    ).toHaveLength(160);
  });
});
