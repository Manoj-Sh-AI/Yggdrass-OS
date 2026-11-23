"use client";
/**
 * The current-time line [proposal, brief C]: only in today's column, 2px with a dot at
 * its left edge, above event blocks. It ticks on the minute boundary (not every 60s from
 * mount) and recomputes when the tab becomes visible again, because a throttled
 * background timer is the known cause of lines that stop advancing. Its colour is the
 * danger token, which no category may use.
 */
import { useEffect, useState } from "react";
import { minuteTop, msToNextMinute } from "./grid";

export function useNow(): Date {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout>;
    const tick = () => {
      setNow(new Date());
      timer = setTimeout(tick, msToNextMinute(new Date()));
    };
    timer = setTimeout(tick, msToNextMinute(new Date()));
    const visible = () => {
      if (document.visibilityState === "visible") {
        clearTimeout(timer);
        tick();
      }
    };
    document.addEventListener("visibilitychange", visible);
    return () => {
      clearTimeout(timer);
      document.removeEventListener("visibilitychange", visible);
    };
  }, []);
  return now;
}

export function NowLine({
  minute,
  hourPx,
}: {
  minute: number;
  hourPx: number;
}) {
  return (
    <div
      role="presentation"
      data-now-line
      className="pointer-events-none absolute inset-x-0 z-10 h-0.5 bg-danger"
      style={{ top: minuteTop(minute, hourPx) - 1 }}
    >
      <span className="absolute top-1/2 -left-1 size-2.5 -translate-y-1/2 rounded-full bg-danger" />
    </div>
  );
}
