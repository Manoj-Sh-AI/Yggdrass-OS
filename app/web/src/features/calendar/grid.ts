/**
 * Week-grid geometry (Phase C), as pure functions so every rule is tested.
 * Provenance per rule: [cited] Google's 12-15 visible hours; everything else [derived]
 * or [proposal] as the brief labels it. No Google pixel values exist publicly.
 */

export const VISIBLE_HOURS = 13; // inside Google's cited 12-15 hour range
export const HOUR_MIN = 44; // [derived] floor: a 15-min event stays >= 11px
export const HOUR_MAX = 72; // [derived] ceiling on tall screens
export const EVENT_MIN_PX = 20; // [proposal] a 15-minute event never collapses below a row
export const CASCADE_INDENT_PX = 24; // [proposal] > 3 overlaps cascade
export const MAX_SIDE_BY_SIDE = 3; // [proposal]

/** --hour-h from the grid's visible height: 13 hours fill it, clamped 44-72px. */
export function hourHeight(visiblePx: number): number {
  if (!Number.isFinite(visiblePx) || visiblePx <= 0) return 56;
  return Math.round(
    Math.min(HOUR_MAX, Math.max(HOUR_MIN, visiblePx / VISIBLE_HOURS)),
  );
}

export const minuteTop = (minute: number, hourPx: number) =>
  (minute * hourPx) / 60;

/** scrollTop that puts `minute` about a third of the way down [proposal]. */
export function scrollToNow(
  minute: number,
  hourPx: number,
  visiblePx: number,
): number {
  return Math.max(0, Math.round(minuteTop(minute, hourPx) - visiblePx / 3));
}

export type BlockMode = "two-line" | "one-line" | "compact";

/** What fits in a block of this height [proposal, brief C]. */
export function blockMode(heightPx: number): BlockMode {
  if (heightPx >= 44) return "two-line"; // time, then title
  if (heightPx >= 28) return "one-line"; // title; time on hover
  return "compact"; // title only, clipped, min-height kept
}

export function blockHeight(minutes: number, hourPx: number): number {
  return Math.max(EVENT_MIN_PX, (minutes * hourPx) / 60);
}

export type Lane = { lane: number; lanes: number };

/**
 * Horizontal placement of one block in its overlap cluster. Up to 3 side by side at
 * 100%/n; more cascade with a fixed indent, full remaining width. A 1px inset on each
 * side means adjacent blocks never share an edge.
 */
export function placement({ lane, lanes }: Lane): {
  left: string;
  width: string;
  cascade: boolean;
} {
  if (lanes <= MAX_SIDE_BY_SIDE) {
    const share = 100 / Math.max(1, lanes);
    return {
      left: `calc(${lane * share}% + 1px)`,
      width: `calc(${share}% - 2px)`,
      cascade: false,
    };
  }
  const indent = lane * CASCADE_INDENT_PX;
  return {
    left: `${indent + 1}px`,
    width: `calc(100% - ${indent + 2}px)`,
    cascade: true,
  };
}

/** Milliseconds until the next minute boundary (the now line ticks on the minute). */
export function msToNextMinute(now: Date): number {
  return 60_000 - (now.getSeconds() * 1000 + now.getMilliseconds());
}

/** Mini month: the 6x7 days (Monday first) around `day`, as YYYY-MM-DD. */
export function monthGrid(day: string): string[] {
  const [y, m] = day.split("-").map(Number);
  const first = new Date(Date.UTC(y, m - 1, 1));
  const offset = (first.getUTCDay() + 6) % 7;
  return Array.from({ length: 42 }, (_, i) =>
    new Date(Date.UTC(y, m - 1, 1 - offset + i)).toISOString().slice(0, 10),
  );
}

/** Monday of the week containing `day`. */
export function weekStart(day: string): string {
  const d = new Date(`${day}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() - ((d.getUTCDay() + 6) % 7));
  return d.toISOString().slice(0, 10);
}

export function addDays(day: string, n: number): string {
  const d = new Date(`${day}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}
