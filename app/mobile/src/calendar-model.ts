/** Pure calendar layout helpers (no React): which items fall on a day, where a timed item
 * sits on the timeline, and how a month or schedule groups them. Tested on their own. */
import { addDays, dayKey, overlapsDay, taskDay, wallClock } from "./dates";
import type { DateItem, Snapshot, Task, TimedItem } from "./types";

export type CalendarView = "schedule" | "day" | "3day" | "month";
export type Kinds = { events: boolean; tasks: boolean; availability: boolean };
export const ALL_KINDS: Kinds = { events: true, tasks: true, availability: true };

export type Entry =
  | { kind: "event"; id: string; title: string; item: TimedItem }
  | { kind: "availability"; id: string; title: string; item: TimedItem }
  | { kind: "allday"; id: string; title: string; item: DateItem }
  | { kind: "task"; id: string; title: string; item: Task; done: boolean };

/** Snapshots for neighbouring months, merged without duplicates. */
export function merge(...snapshots: (Snapshot | null | undefined)[]): Snapshot | null {
  const present = snapshots.filter(Boolean) as Snapshot[];
  if (!present.length) return null;
  const unique = <T extends { id: string }>(lists: T[][]) => {
    const seen = new Map<string, T>();
    for (const list of lists) for (const item of list || []) seen.set(item.id, item);
    return [...seen.values()];
  };
  return {
    ...present[0],
    tasks: unique(present.map((s) => s.tasks)),
    events: unique(present.map((s) => s.events)),
    date_items: unique(present.map((s) => s.date_items || [])),
    availability: unique(present.map((s) => s.availability || [])),
    blocks: unique(present.map((s) => s.blocks || [])),
  };
}

/** Everything on one day, all-day items first, then timed items by start, then tasks. */
export function entriesOn(
  snapshot: Snapshot | null,
  day: string,
  timezone: string,
  kinds: Kinds = ALL_KINDS,
): Entry[] {
  if (!snapshot) return [];
  const out: Entry[] = [];
  if (kinds.events)
    for (const item of snapshot.date_items || [])
      if (item.starts_on <= day && item.ends_before > day)
        out.push({ kind: "allday", id: item.id, title: item.title, item });
  const timed: Entry[] = [];
  if (kinds.events)
    for (const item of snapshot.events || [])
      if (overlapsDay(item, day, timezone))
        timed.push({ kind: "event", id: item.id, title: item.title, item });
  if (kinds.availability)
    for (const item of snapshot.availability || [])
      if (overlapsDay(item, day, timezone))
        timed.push({ kind: "availability", id: item.id, title: item.title, item });
  timed.sort((a, b) =>
    (a.item as TimedItem).starts_at.localeCompare((b.item as TimedItem).starts_at),
  );
  out.push(...timed);
  if (kinds.tasks)
    for (const task of snapshot.tasks || [])
      if (taskDay(task, timezone) === day)
        out.push({ kind: "task", id: task.id, title: task.title, item: task, done: task.done });
  return out;
}

/** Minutes after local midnight where a timed item starts and ends on `day`, clipped. */
export function span(item: TimedItem, day: string, timezone: string) {
  const startDay = dayKey(new Date(item.starts_at), timezone);
  const endDay = dayKey(new Date(item.ends_at), timezone);
  const minutes = (instant: string) => {
    const [h, m] = wallClock(instant, timezone).split(":").map(Number);
    return h * 60 + m;
  };
  const start = startDay < day ? 0 : minutes(item.starts_at);
  const end = endDay > day ? 24 * 60 : minutes(item.ends_at);
  return { start, end: Math.max(end, start + 15) };
}

/** Lays overlapping timed items side by side: each gets a column and the group width. */
export function lanes<T extends { start: number; end: number }>(items: T[]) {
  const sorted = [...items].sort((a, b) => a.start - b.start || b.end - a.end);
  const placed: (T & { lane: number; lanes: number })[] = [];
  let group: (T & { lane: number; lanes: number })[] = [];
  let groupEnd = -1;
  const close = () => {
    const width = Math.max(0, ...group.map((g) => g.lane)) + 1;
    for (const g of group) g.lanes = width;
    group = [];
  };
  for (const item of sorted) {
    if (item.start >= groupEnd) {
      close();
      groupEnd = -1;
    }
    const used = new Set(group.filter((g) => g.end > item.start).map((g) => g.lane));
    let lane = 0;
    while (used.has(lane)) lane++;
    const entry = { ...item, lane, lanes: 1 };
    group.push(entry);
    placed.push(entry);
    groupEnd = Math.max(groupEnd, item.end);
  }
  close();
  return placed;
}

/** The days a view shows around `selected`. */
export function visibleDays(view: CalendarView, selected: string) {
  if (view === "3day") return [selected, addDays(selected, 1), addDays(selected, 2)];
  return [selected];
}

/** Schedule view: the days from `from` that have something on them, up to `limit` days. */
export function schedule(
  snapshot: Snapshot | null,
  from: string,
  timezone: string,
  kinds: Kinds = ALL_KINDS,
  limit = 45,
) {
  const days: { day: string; entries: Entry[] }[] = [];
  for (let i = 0; i < limit; i++) {
    const day = addDays(from, i);
    const entries = entriesOn(snapshot, day, timezone, kinds);
    if (entries.length) days.push({ day, entries });
  }
  return days;
}

/** How far each swipe moves in each view. */
export function step(view: CalendarView) {
  return view === "3day" ? 3 : 1;
}
