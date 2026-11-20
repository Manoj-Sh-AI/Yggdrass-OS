import { addDays, dayKey, monthRange, zonedInstant } from "../src/dates";

test("calendar uses Monday-first weeks across year and leap-day boundaries", () => {
  const december = monthRange("2026-12");
  expect(december.days).toHaveLength(42);
  expect(december.start).toBe("2026-11-30");
  expect(december.end).toBe("2027-01-10");
  expect(addDays("2024-02-28", 1)).toBe("2024-02-29");
});
test("dates use the selected timezone rather than UTC midnight", () => {
  expect(dayKey(new Date("2030-01-01T00:30:00Z"), "America/Los_Angeles")).toBe(
    "2029-12-31",
  );
});
test("timed calendar saves preserve wall time with winter and summer offsets", () => {
  expect(zonedInstant("2026-11-16", "09:00", "Europe/Berlin")).toBe(
    "2026-11-16T08:00:00.000Z",
  );
  expect(zonedInstant("2026-06-16", "09:00", "Europe/Berlin")).toBe(
    "2026-06-16T07:00:00.000Z",
  );
});
test("clock changes never silently shift or choose ambiguous times", () => {
  expect(() => zonedInstant("2026-03-29", "02:30", "Europe/Berlin")).toThrow(
    "does not exist",
  );
  expect(() => zonedInstant("2026-10-25", "02:30", "Europe/Berlin")).toThrow(
    "occurs twice",
  );
});
