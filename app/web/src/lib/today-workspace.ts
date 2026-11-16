import {
  onLocalDay,
  type PlanningSnapshot,
  type PlanningTask,
} from "./planning";

export function todayWork(
  data: PlanningSnapshot,
  day: string,
  timezone: string,
) {
  const tasks = new Map(data.tasks.map((task) => [task.id, task]));
  const schedule = [
    ...data.events
      .filter((event) => onLocalDay(event, day, timezone))
      .map((event) => ({
        id: event.id,
        title: event.title,
        starts_at: event.starts_at,
        ends_at: event.ends_at,
        event,
        task: undefined as PlanningTask | undefined,
      })),
    ...data.blocks
      .filter((block) => {
        const task = tasks.get(block.task_id);
        return (
          task &&
          !task.done &&
          task.state !== "skipped" &&
          onLocalDay(block, day, timezone)
        );
      })
      .map((block) => ({
        id: block.id,
        title: tasks.get(block.task_id)!.title,
        starts_at: block.starts_at,
        ends_at: block.ends_at,
        task: tasks.get(block.task_id),
        event: undefined,
      })),
  ].sort(
    (a, b) =>
      a.starts_at.localeCompare(b.starts_at) || a.id.localeCompare(b.id),
  );
  const scheduled = new Set(
    schedule.flatMap((item) => (item.task ? [item.task.id] : [])),
  );
  const due = data.tasks.filter(
    (task) =>
      !task.done &&
      task.state !== "skipped" &&
      !scheduled.has(task.id) &&
      (task.due_date === day || task.occurrence_date === day),
  );
  return { schedule, due };
}
