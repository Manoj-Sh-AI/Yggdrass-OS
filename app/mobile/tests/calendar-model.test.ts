import {
  entriesOn,
  lanes,
  merge,
  schedule,
  span,
  step,
  visibleDays,
} from "../src/calendar-model";
import type { Snapshot } from "../src/types";

const zone = "Europe/Berlin";
const task = (id: string, due: string, done = false) =>
  ({
    id,
    title: `Invented task ${id}`,
    due_date: due,
    deadline_at: null,
    done,
    version: 1,
  }) as unknown as Snapshot["tasks"][number];
const event = (id: string, start: string, end: string) => ({
  id,
  title: `Invented event ${id}`,
  description: "",
  starts_at: start,
  ends_at: end,
  timezone: zone,
  version: 1,
});
const snapshot = (over: Partial<Snapshot> = {}) =>
  ({
    tasks: [],
    events: [],
    date_items: [],
    availability: [],
    blocks: [],
    sessions: [],
    ...over,
  }) as unknown as Snapshot;

test("a day lists all-day items, then timed items by start, then tasks", () => {
  const s = snapshot({
    tasks: [task("t", "2030-04-10")],
    events: [
      event("late", "2030-04-10T14:00:00Z", "2030-04-10T15:00:00Z"),
      event("early", "2030-04-10T07:00:00Z", "2030-04-10T08:00:00Z"),
    ],
    date_items: [
      {
        id: "trip",
        title: "Invented trip",
        description: "",
        kind: "event",
        starts_on: "2030-04-09",
        ends_before: "2030-04-12",
        version: 1,
      } as unknown as Snapshot["date_items"][number],
    ],
  });
  expect(entriesOn(s, "2030-04-10", zone).map((e) => e.id)).toEqual([
    "trip",
    "early",
    "late",
    "t",
  ]);
  expect(
    entriesOn(s, "2030-04-10", zone, { events: false, tasks: true, availability: true }).map(
      (e) => e.id,
    ),
  ).toEqual(["t"]);
});

test("a timed item is placed in local minutes and clipped to the day", () => {
  // 09:30–10:15 Berlin (summer time) on the day itself.
  expect(span(event("a", "2030-06-10T07:30:00Z", "2030-06-10T08:15:00Z"), "2030-06-10", zone)).toEqual({
    start: 570,
    end: 615,
  });
  // An overnight item fills the rest of its first day and the start of the next.
  const night = event("n", "2030-06-10T20:00:00Z", "2030-06-11T05:00:00Z");
  expect(span(night, "2030-06-10", zone)).toEqual({ start: 22 * 60, end: 24 * 60 });
  expect(span(night, "2030-06-11", zone)).toEqual({ start: 0, end: 7 * 60 });
});

test("overlapping items share the width; separate ones get it all", () => {
  const placed = lanes([
    { id: "a", start: 60, end: 120 },
    { id: "b", start: 90, end: 150 },
    { id: "c", start: 200, end: 230 },
  ]);
  const by = Object.fromEntries(placed.map((p) => [p.id, p]));
  expect([by.a.lane, by.a.lanes, by.b.lane, by.b.lanes]).toEqual([0, 2, 1, 2]);
  expect([by.c.lane, by.c.lanes]).toEqual([0, 1]);
});

test("neighbouring months merge without duplicates", () => {
  const a = snapshot({ tasks: [task("x", "2030-04-30")] });
  const b = snapshot({ tasks: [task("x", "2030-04-30"), task("y", "2030-05-01")] });
  expect(merge(a, b)!.tasks.map((t) => t.id)).toEqual(["x", "y"]);
  expect(merge(null, undefined)).toBeNull();
});

test("the schedule skips empty days", () => {
  const s = snapshot({ tasks: [task("a", "2030-04-11"), task("b", "2030-04-14")] });
  expect(schedule(s, "2030-04-10", zone).map((d) => d.day)).toEqual([
    "2030-04-11",
    "2030-04-14",
  ]);
});

test("3-day shows three days and swipes by three", () => {
  expect(visibleDays("3day", "2030-04-30")).toEqual(["2030-04-30", "2030-05-01", "2030-05-02"]);
  expect(visibleDays("day", "2030-04-30")).toEqual(["2030-04-30"]);
  expect([step("3day"), step("day"), step("month")]).toEqual([3, 1, 1]);
});
