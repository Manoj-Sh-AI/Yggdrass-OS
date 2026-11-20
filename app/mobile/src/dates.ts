export function dayKey(date = new Date(), timezone?: string) {
  if (timezone) {
    const parts = new Intl.DateTimeFormat("en-CA", {
      timeZone: timezone,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).formatToParts(date);
    return ["year", "month", "day"]
      .map((k) => parts.find((p) => p.type === k)!.value)
      .join("-");
  }
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}
export function addDays(day: string, days: number) {
  const d = new Date(`${day}T12:00:00`);
  d.setDate(d.getDate() + days);
  return dayKey(d);
}
export function monthRange(month: string) {
  const first = `${month}-01`;
  const d = new Date(`${first}T12:00:00`);
  const offset = (d.getDay() + 6) % 7;
  const start = addDays(first, -offset);
  return {
    start,
    end: addDays(start, 41),
    days: Array.from({ length: 42 }, (_, i) => addDays(start, i)),
  };
}
export function shiftMonth(month: string, offset: number) {
  const d = new Date(`${month}-01T12:00:00`);
  d.setMonth(d.getMonth() + offset);
  return dayKey(d).slice(0, 7);
}
export function clock(instant: string, timezone: string) {
  return new Date(instant).toLocaleTimeString([], {
    timeZone: timezone,
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function overlapsDay(
  item: { starts_at: string; ends_at: string },
  day: string,
  timezone: string,
) {
  return (
    dayKey(new Date(item.starts_at), timezone) <= day &&
    dayKey(new Date(Date.parse(item.ends_at) - 1), timezone) >= day
  );
}
export function taskDay(
  task: { due_date: string | null; deadline_at: string | null },
  timezone: string,
) {
  return task.deadline_at
    ? dayKey(new Date(task.deadline_at), timezone)
    : task.due_date;
}
/** Missing and ambiguous daylight-saving wall times require another explicit choice. */
export function zonedInstant(day: string, time: string, timezone: string) {
  if (
    !/^\d{4}-\d{2}-\d{2}$/.test(day) ||
    !/^([01]\d|2[0-3]):[0-5]\d$/.test(time)
  )
    throw new Error("Enter a date as YYYY-MM-DD and time as HH:mm.");
  const target = `${day}T${time}`;
  const format = (value: number) => {
    const parts = new Intl.DateTimeFormat("en-GB", {
      timeZone: timezone,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hourCycle: "h23",
    }).formatToParts(new Date(value));
    const p = (k: string) => parts.find((x) => x.type === k)!.value;
    return `${p("year")}-${p("month")}-${p("day")}T${p("hour")}:${p("minute")}`;
  };
  const nominal = Date.parse(target + ":00Z");
  let candidate = nominal;
  if (!Number.isFinite(candidate)) throw new Error("Choose a valid date.");
  for (let i = 0; i < 4; i++)
    candidate += nominal - Date.parse(format(candidate) + ":00Z");
  if (format(candidate) !== target)
    throw new Error(
      "This local time does not exist because the clocks change. Choose another time.",
    );
  if (
    [
      candidate - 3600000,
      candidate + 3600000,
      candidate - 1800000,
      candidate + 1800000,
    ].some((v) => format(v) === target)
  )
    throw new Error(
      "This time occurs twice when the clocks change. Choose an unambiguous time.",
    );
  return new Date(candidate).toISOString();
}
export function wallClock(instant: string, timezone: string) {
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: timezone,
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).format(new Date(instant));
}
