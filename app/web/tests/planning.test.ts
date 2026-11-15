import { describe, expect, it } from "vitest";
import {
  addDays,
  calendarLanes,
  conflicts,
  dateInZone,
  foldForInstant,
  onLocalDay,
  elapsedLabel,
  localInput,
  minutesBetween,
  monthDays,
  sessionSeconds,
  wallTime,
  weekDays,
  type ExecutionSession,
} from "../src/lib/planning";

describe("named-timezone calendar presentation", () => {
  it("preserves the existing autumn occurrence when reopening a time form", () => {
    expect(foldForInstant("2026-10-25T00:30:00Z", "Europe/Berlin")).toBe(0);
    expect(foldForInstant("2026-10-25T01:30:00Z", "Europe/Berlin")).toBe(1);
  });
  it("includes midnight-spanning blocks on both occupied days, with an exclusive end", () => {
    const item = {
      starts_at: "2026-11-09T22:30:00Z",
      ends_at: "2026-11-09T23:30:00Z",
    };
    expect(onLocalDay(item, "2026-11-09", "Europe/Berlin")).toBe(true);
    expect(onLocalDay(item, "2026-11-10", "Europe/Berlin")).toBe(true);
    expect(
      onLocalDay(
        { ...item, ends_at: "2026-11-09T23:00:00Z" },
        "2026-11-10",
        "Europe/Berlin",
      ),
    ).toBe(false);
  });
  it("keeps late UTC tasks on their Berlin local date", () => {
    expect(dateInZone("2026-03-28T23:30:00Z", "Europe/Berlin")).toBe(
      "2026-03-29",
    );
    expect(localInput("2026-03-28T23:30:00Z", "Europe/Berlin")).toBe(
      "2026-03-29T00:30",
    );
  });
  it("shows both autumn occurrences at the same wall clock time while retaining distinct instants", () => {
    expect(wallTime("2026-10-25T00:30:00Z", "Europe/Berlin")).toBe("02:30");
    expect(wallTime("2026-10-25T01:30:00Z", "Europe/Berlin")).toBe("02:30");
    expect(minutesBetween("2026-10-25T00:30:00Z", "2026-10-25T01:30:00Z")).toBe(
      60,
    );
  });
  it("measures spring elapsed time independently from wall-clock labels", () => {
    expect(localInput("2026-03-29T01:30:00Z", "Europe/Berlin")).toBe(
      "2026-03-29T03:30",
    );
    expect(minutesBetween("2026-03-29T00:30:00Z", "2026-03-29T01:30:00Z")).toBe(
      60,
    );
  });
  it("builds Monday-based calendar ranges across year boundaries without device-timezone arithmetic", () => {
    expect(weekDays("2027-01-01")).toEqual([
      "2026-12-28",
      "2026-12-29",
      "2026-12-30",
      "2026-12-31",
      "2027-01-01",
      "2027-01-02",
      "2027-01-03",
    ]);
    expect(monthDays("2026-11-09")).toHaveLength(42);
    expect(addDays("2026-03-29", 1)).toBe("2026-03-30");
  });
});
describe("calendar integrity and execution", () => {
  const item = (id: string, start: string, end: string) => ({
    id,
    starts_at: `2026-11-09T${start}:00Z`,
    ends_at: `2026-11-09T${end}:00Z`,
  });
  it("detects overlapping commitments without treating adjacent blocks as conflicts", () => {
    const entries = [
      item("a", "09:00", "10:00"),
      item("b", "09:30", "11:00"),
      item("c", "11:00", "12:00"),
    ];
    expect([...conflicts(entries)].sort()).toEqual(["a", "b"]);
    expect(entries).toHaveLength(3);
  });
  it("assigns separate selectable lanes within overlap clusters", () => {
    const lanes = calendarLanes([
      item("a", "09:00", "10:00"),
      item("b", "09:30", "11:00"),
      item("c", "10:00", "10:30"),
      item("d", "12:00", "13:00"),
    ]);
    expect(lanes.get("a")).toEqual({ lane: 0, lanes: 2 });
    expect(lanes.get("b")).toEqual({ lane: 1, lanes: 2 });
    expect(lanes.get("c")).toEqual({ lane: 0, lanes: 2 });
    expect(lanes.get("d")).toEqual({ lane: 0, lanes: 1 });
  });
  it("restores elapsed execution from timestamps after interruptions and excludes paused time", () => {
    const running = {
      started_at: "2026-11-09T09:00:00Z",
      ended_at: null,
    } as ExecutionSession;
    expect(sessionSeconds(running, Date.parse("2026-11-09T09:12:00Z"))).toBe(
      720,
    );
    expect(
      sessionSeconds(
        { ...running, ended_at: "2026-11-09T09:05:00Z" },
        Date.parse("2026-11-09T10:00:00Z"),
      ),
    ).toBe(300);
    expect(elapsedLabel(720)).toBe("00:12:00");
  });
  it("keeps conflict and lane processing bounded for 10,000 nonoverlapping blocks", () => {
    const entries = Array.from({ length: 10000 }, (_, i) => ({
      id: String(i),
      starts_at: new Date(i * 3600000).toISOString(),
      ends_at: new Date(i * 3600000 + 1800000).toISOString(),
    }));
    expect(conflicts(entries).size).toBe(0);
    expect(calendarLanes(entries).size).toBe(10000);
  });
});
