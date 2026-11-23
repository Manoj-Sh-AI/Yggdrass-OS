import { describe, expect, it } from "vitest";
import type { PlanningSnapshot, PlanningTask } from "../src/lib/planning";
import { todayWork } from "../src/lib/today-workspace";
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

const day = "2030-01-02";
const snapshot = (tasks: PlanningTask[]): PlanningSnapshot =>
  ({ tasks, events: [], blocks: [] }) as unknown as PlanningSnapshot;
describe("Today uses saved commitments without assigning priorities", () => {
  it("does not invent items for an empty day", () => {
    expect(todayWork(snapshot([]), day, "Europe/Berlin")).toEqual({
      schedule: [],
      due: [],
    });
  });
  it("shows due tasks once and excludes finished, skipped and unrelated work", () => {
    const data = snapshot([
      task({ id: "scheduled", due_date: day }),
      task({ id: "due", due_date: day }),
      task({ id: "done", due_date: day, done: true, state: "completed" }),
      task({ id: "skip", due_date: day, state: "skipped" }),
      task({ id: "tomorrow", due_date: "2030-01-03" }),
    ]);
    data.blocks = [
      {
        id: "block",
        task_id: "scheduled",
        starts_at: "2030-01-02T09:00:00Z",
        ends_at: "2030-01-02T09:25:00Z",
        timezone: "Europe/Berlin",
        reason: "",
        automatic: false,
        version: 1,
      },
    ];
    const before = JSON.stringify(data);
    const result = todayWork(data, day, "Europe/Berlin");
    expect(result.schedule.map((item) => item.task?.id)).toEqual(["scheduled"]);
    expect(result.due.map((item) => item.id)).toEqual(["due"]);
    expect(JSON.stringify(data)).toBe(before);
  });
  it("uses the selected timezone and exclusive midnight boundaries for events", () => {
    const data = snapshot([]);
    data.events = [
      {
        id: "overnight",
        title: "Overnight",
        starts_at: "2030-01-01T22:30:00Z",
        ends_at: "2030-01-01T23:30:00Z",
        description: "",
        timezone: "Europe/Berlin",
        version: 1,
      },
      {
        id: "ends-at-midnight",
        title: "Earlier",
        starts_at: "2030-01-01T22:00:00Z",
        ends_at: "2030-01-01T23:00:00Z",
        description: "",
        timezone: "Europe/Berlin",
        version: 1,
      },
    ];
    expect(
      todayWork(data, day, "Europe/Berlin").schedule.map((item) => item.id),
    ).toEqual(["overnight"]);
    expect(todayWork(data, day, "UTC").schedule).toHaveLength(0);
  });
});
