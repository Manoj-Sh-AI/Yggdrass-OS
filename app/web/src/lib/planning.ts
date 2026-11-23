export type PlanningTask = {
  id: string;
  title: string;
  objective: string;
  description: string;
  area: string;
  due_date: string | null;
  deadline_at: string | null;
  timezone: string;
  priority: number;
  estimated_minutes: number;
  effort: string;
  tags: string[];
  goal_id: string | null;
  project_id: string | null;
  parent_id: string | null;
  template_id: string | null;
  occurrence_date: string | null;
  occurrence_edited: boolean;
  routine_window_start: string | null;
  routine_window_end: string | null;
  state: "todo" | "in_progress" | "paused" | "completed" | "skipped";
  progress: number;
  done: boolean;
  completed_at: string | null;
  version: number;
  actual_seconds: number;
  next_scheduled_at: string | null;
  last_scheduled_end: string | null;
  scheduled_block_count: number;
  created_at: string;
  updated_at: string;
};
export type PlanningGroup = {
  id: string;
  title: string;
  description: string;
  goal_id?: string | null;
  version: number;
};
export type RoutineTemplate = {
  id: string;
  title: string;
  description: string;
  objective: string;
  area: string;
  frequency: "daily" | "weekly";
  interval_count: number;
  weekdays: number[];
  starts_on: string;
  ends_on: string | null;
  timezone: string;
  window_start: string;
  window_end: string;
  expected_minutes: number;
  priority: number;
  goal_id: string | null;
  essential: boolean;
  active: boolean;
  version: number;
};
export type PlanningBlock = {
  id: string;
  task_id: string;
  starts_at: string;
  ends_at: string;
  timezone: string;
  reason: string;
  automatic: boolean;
  version: number;
};
export type CalendarEvent = {
  id: string;
  title: string;
  description: string;
  starts_at: string;
  ends_at: string;
  timezone: string;
  version: number;
};
export type CalendarDateItem = { id: string; title: string; description: string; kind: "event" | "availability" | "review"; starts_on: string; ends_before: string; cancelled: boolean; version: number };
export type AvailabilityWindow = CalendarEvent & { cancelled: boolean };
export type ExecutionSession = {
  id: string;
  task_id: string;
  block_id: string | null;
  started_at: string;
  ended_at: string | null;
  outcome: string | null;
  expected_minutes: number;
  scheduled_start: string | null;
};
export type DailyPlan = {
  day: string;
  timezone: string;
  available_minutes: number;
  energy: string;
  focus: string;
  sleep: string;
  intention: string;
  reflection: string;
  confirmed_at: string | null;
  reviewed_at: string | null;
  version: number;
};
export type ReminderRequest = {
  id: string;
  task_id: string;
  block_id: string | null;
  kind: string;
  eligible_at: string;
};
export type PlanningSnapshot = {
  tasks: PlanningTask[];
  goals: PlanningGroup[];
  projects: PlanningGroup[];
  routines: RoutineTemplate[];
  dependencies: { task_id: string; depends_on: string }[];
  exceptions: { template_id: string; occurrence_date: string }[];
  blocks: PlanningBlock[];
  events: CalendarEvent[];
  date_items?: CalendarDateItem[];
  availability?: AvailabilityWindow[];
  sessions: ExecutionSession[];
  plans: DailyPlan[];
  history: {
    id: number;
    task_id: string;
    kind: string;
    detail: Record<string, unknown>;
    at: string;
  }[];
  reminders: ReminderRequest[];
  server_now: string;
  source: "postgresql";
  range: { start: string; end: string; timezone: string };
  summaries: {
    day: string;
    scheduled_minutes: number;
    event_minutes: number;
    estimated_minutes: number;
    actual_minutes: number;
    completed: number;
    unfinished: number;
  }[];
};
export type PlanningOperation =
  | "task.create"
  | "task.update"
  | "task.execute"
  | "focus.switch"
  | "goal.create"
  | "goal.update"
  | "project.create"
  | "project.update"
  | "routine.create"
  | "routine.update"
  | "routine.skip"
  | "ensure"
  | "block.create"
  | "block.update"
  | "block.remove"
  | "block.split"
  | "event.create"
  | "event.update"
  | "event.remove"
  | "daily.save"
  | "reminder.ack";
export type CommandResult = {
  id?: string;
  version?: number;
  generated?: number;
  saved?: boolean;
  timer_running?: boolean;
  previous_id?: string;
  previous_version?: number;
};
export function dateInZone(instant: string | Date, timezone: string) {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: timezone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date(instant));
}
export function addDays(day: string, amount: number) {
  const date = new Date(day + "T12:00:00Z");
  date.setUTCDate(date.getUTCDate() + amount);
  return date.toISOString().slice(0, 10);
}
export function monthDays(day: string) {
  const first = day.slice(0, 7) + "-01";
  const offset = (new Date(first + "T12:00:00Z").getUTCDay() + 6) % 7;
  return Array.from({ length: 42 }, (_, i) => addDays(first, i - offset));
}
export function weekDays(day: string) {
  const offset = (new Date(day + "T12:00:00Z").getUTCDay() + 6) % 7;
  return Array.from({ length: 7 }, (_, i) => addDays(day, i - offset));
}
export function wallTime(instant: string, timezone: string) {
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: timezone,
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).format(new Date(instant));
}
export function localInput(instant: string, timezone: string) {
  return dateInZone(instant, timezone) + "T" + wallTime(instant, timezone);
}
export function foldForInstant(instant: string, timezone: string) {
  const wall = localInput(instant, timezone),
    at = Date.parse(instant);
  return [30, 60, 90, 120, 150, 180].some(
    (minutes) =>
      localInput(new Date(at - minutes * 60000).toISOString(), timezone) ===
      wall,
  )
    ? 1
    : 0;
}
export function onLocalDay(
  item: { starts_at: string; ends_at: string },
  day: string,
  timezone: string,
) {
  return (
    dateInZone(item.starts_at, timezone) <= day &&
    dateInZone(new Date(Date.parse(item.ends_at) - 1), timezone) >= day
  );
}
export function minuteOfDay(instant: string, timezone: string) {
  const [h, m] = wallTime(instant, timezone).split(":").map(Number);
  return h * 60 + m;
}
export function minutesBetween(start: string, end: string) {
  return Math.max(0, (Date.parse(end) - Date.parse(start)) / 60000);
}
export function overlaps(
  a: { starts_at: string; ends_at: string },
  b: { starts_at: string; ends_at: string },
) {
  return (
    Date.parse(a.starts_at) < Date.parse(b.ends_at) &&
    Date.parse(b.starts_at) < Date.parse(a.ends_at)
  );
}
/** Interval partitioning keeps simultaneous commitments individually selectable. */
export function calendarLanes(
  items: { id: string; starts_at: string; ends_at: string }[],
) {
  const result = new Map<string, { lane: number; lanes: number }>();
  const sorted = [...items].sort(
    (a, b) => Date.parse(a.starts_at) - Date.parse(b.starts_at),
  );
  let cluster: typeof sorted = [],
    clusterEnd = 0;
  const flush = () => {
    const ends: number[] = [];
    const assignments: { id: string; lane: number }[] = [];
    for (const item of cluster) {
      const start = Date.parse(item.starts_at);
      let lane = ends.findIndex((end) => end <= start);
      if (lane < 0) lane = ends.length;
      ends[lane] = Date.parse(item.ends_at);
      assignments.push({ id: item.id, lane });
    }
    for (const item of assignments)
      result.set(item.id, { lane: item.lane, lanes: ends.length });
  };
  for (const item of sorted) {
    const start = Date.parse(item.starts_at);
    if (cluster.length && start >= clusterEnd) {
      flush();
      cluster = [];
    }
    cluster.push(item);
    clusterEnd = Math.max(
      cluster.length === 1 ? 0 : clusterEnd,
      Date.parse(item.ends_at),
    );
  }
  flush();
  return result;
}
export function conflicts(
  items: { id: string; starts_at: string; ends_at: string }[],
) {
  const ids = new Set<string>();
  const sorted = [...items].sort(
    (a, b) => Date.parse(a.starts_at) - Date.parse(b.starts_at),
  );
  for (let i = 0; i < sorted.length; i++)
    for (
      let j = i + 1;
      j < sorted.length &&
      Date.parse(sorted[j].starts_at) < Date.parse(sorted[i].ends_at);
      j++
    ) {
      if (overlaps(sorted[i], sorted[j])) {
        ids.add(sorted[i].id);
        ids.add(sorted[j].id);
      }
    }
  return ids;
}
export function sessionSeconds(session: ExecutionSession, now: number) {
  return Math.max(
    0,
    ((session.ended_at ? Date.parse(session.ended_at) : now) -
      Date.parse(session.started_at)) /
      1000,
  );
}
export function elapsedLabel(seconds: number) {
  const total = Math.max(0, Math.floor(seconds));
  return `${String(Math.floor(total / 3600)).padStart(2, "0")}:${String(Math.floor(total / 60) % 60).padStart(2, "0")}:${String(total % 60).padStart(2, "0")}`;
}
export function taskInput(
  task: PlanningTask,
  dependencies: PlanningSnapshot["dependencies"],
) {
  const {
    title,
    objective,
    description,
    area,
    due_date,
    deadline_at,
    timezone,
    priority,
    estimated_minutes,
    effort,
    tags,
    goal_id,
    project_id,
    parent_id,
  } = task;
  return {
    title,
    objective,
    description,
    area,
    due_date,
    deadline_at,
    timezone,
    priority,
    estimated_minutes,
    effort,
    tags,
    goal_id,
    project_id,
    parent_id,
    dependencies: dependencies
      .filter((d) => d.task_id === task.id)
      .map((d) => d.depends_on),
  };
}
