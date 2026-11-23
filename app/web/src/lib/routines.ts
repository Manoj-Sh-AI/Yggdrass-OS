/** Application-only prototype types. Nothing here imports or calls the Brain. */
export type RoutineDefinition = Readonly<{
  id: string;
  title: string;
  description?: string;
  goal: string;
  scheduledDate: string;
  windowStart: string;
  windowEnd: string;
  timezone: string;
  expectedMinutes: number;
}>;
export type RoutineProgress = Readonly<{ percent: number; at: string }>;
export type RoutineExecution = Readonly<{
  status: "not_started" | "in_progress" | "completed";
  progress: number;
  startedAt: string | null;
  completedAt: string | null;
  updatedAt: string | null;
  progressHistory: readonly RoutineProgress[];
}>;
export type RoutineStore = Readonly<{
  version: 1;
  definition: RoutineDefinition;
  execution: RoutineExecution;
}>;
export type RoutineAction =
  | { type: "start" }
  | { type: "progress"; percent: number }
  | { type: "complete" };

export function createRoutineStore(
  now = new Date(),
  timezone = "Europe/Berlin",
): RoutineStore {
  const scheduledDate = new Intl.DateTimeFormat("en-CA", {
    timeZone: timezone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(now);
  return {
    version: 1,
    definition: {
      id: "sample-reading",
      title: "A little space to learn",
      goal: "Read one chapter and capture three takeaways.",
      scheduledDate,
      windowStart: "18:00",
      windowEnd: "18:30",
      timezone,
      expectedMinutes: 30,
    },
    execution: {
      status: "not_started",
      progress: 0,
      startedAt: null,
      completedAt: null,
      updatedAt: null,
      progressHistory: [],
    },
  };
}

export function applyRoutineAction(
  store: RoutineStore,
  action: RoutineAction,
  at = new Date().toISOString(),
): RoutineStore {
  if (!Number.isFinite(Date.parse(at)))
    throw new Error("Could not record the execution time.");
  const execution = store.execution;
  if (action.type === "start") {
    if (execution.status !== "not_started") return store;
    return {
      ...store,
      execution: {
        ...execution,
        status: "in_progress",
        startedAt: at,
        updatedAt: at,
      },
    };
  }
  if (execution.status === "not_started")
    throw new Error(
      "Start the routine before recording progress or completion.",
    );
  if (execution.status === "completed")
    throw new Error("This routine is already completed.");
  if (action.type === "progress") {
    if (
      !Number.isInteger(action.percent) ||
      action.percent < 0 ||
      action.percent > 100
    )
      throw new Error(
        "Enter a whole-number progress percentage from 0 to 100.",
      );
    return {
      ...store,
      execution: {
        ...execution,
        progress: action.percent,
        updatedAt: at,
        progressHistory: [
          ...execution.progressHistory,
          { percent: action.percent, at },
        ],
      },
    };
  }
  return {
    ...store,
    execution: {
      ...execution,
      status: "completed",
      progress: 100,
      completedAt: at,
      updatedAt: at,
      progressHistory:
        execution.progress === 100
          ? execution.progressHistory
          : [...execution.progressHistory, { percent: 100, at }],
    },
  };
}

const isTimestamp = (v: unknown): v is string =>
  typeof v === "string" && Number.isFinite(Date.parse(v));
export function isRoutineStore(value: unknown): value is RoutineStore {
  if (!value || typeof value !== "object") return false;
  const s = value as RoutineStore,
    d = s.definition,
    e = s.execution;
  if (s.version !== 1 || !d || !e) return false;
  if (
    ![d.id, d.title, d.goal].every(
      (v) => typeof v === "string" && v.trim().length > 0,
    ) ||
    typeof d.scheduledDate !== "string" ||
    !/^\d{4}-\d{2}-\d{2}$/.test(d.scheduledDate) ||
    !Number.isFinite(Date.parse(`${d.scheduledDate}T12:00:00Z`))
  )
    return false;
  if (
    ![d.windowStart, d.windowEnd].every(
      (v) => typeof v === "string" && /^([01]\d|2[0-3]):[0-5]\d$/.test(v),
    ) ||
    d.windowEnd <= d.windowStart ||
    !Number.isInteger(d.expectedMinutes) ||
    d.expectedMinutes <= 0
  )
    return false;
  if (typeof d.timezone !== "string") return false;
  try {
    new Intl.DateTimeFormat("en", { timeZone: d.timezone });
  } catch {
    return false;
  }
  if (
    !Number.isInteger(e.progress) ||
    e.progress < 0 ||
    e.progress > 100 ||
    !Array.isArray(e.progressHistory) ||
    !e.progressHistory.every(
      (p) =>
        p &&
        Number.isInteger(p.percent) &&
        p.percent >= 0 &&
        p.percent <= 100 &&
        isTimestamp(p.at),
    )
  )
    return false;
  if (e.status === "not_started")
    return (
      e.progress === 0 &&
      e.startedAt === null &&
      e.completedAt === null &&
      e.updatedAt === null &&
      e.progressHistory.length === 0
    );
  if (!isTimestamp(e.startedAt) || !isTimestamp(e.updatedAt)) return false;
  if ((e.progressHistory.at(-1)?.percent ?? 0) !== e.progress) return false;
  if (e.status === "in_progress") return e.completedAt === null;
  return (
    e.status === "completed" && e.progress === 100 && isTimestamp(e.completedAt)
  );
}
