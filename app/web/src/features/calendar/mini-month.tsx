"use client";
/**
 * Mini month picker [proposal, brief C]: an orientation device, not a second data view.
 * Today is a filled circle; the week being viewed is a tinted band (the part most clones
 * omit); a day with any commitment has ONE dot (presence, never a count). Clicking a date
 * moves the main grid to that week without changing the view.
 */
import { ChevronLeft, ChevronRight } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/primitives";
import { addDays, monthGrid, weekStart } from "./grid";

type Props = {
  day: string; // the day the grid shows
  today: string;
  busy: ReadonlySet<string>;
  onPick: (day: string) => void;
};

const WEEKDAYS = ["M", "T", "W", "T", "F", "S", "S"];

export function MiniMonth({ day, today, busy, onPick }: Props) {
  const [month, setMonth] = useState(day.slice(0, 7) + "-01");
  const cells = monthGrid(month);
  const viewed = weekStart(day);
  const shift = (n: number) => {
    const [y, m] = month.split("-").map(Number);
    const d = new Date(Date.UTC(y, m - 1 + n, 1));
    setMonth(d.toISOString().slice(0, 10));
  };
  const title = new Intl.DateTimeFormat("en", {
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(`${month}T00:00:00Z`));
  return (
    <section aria-label="Month" className="flex flex-col gap-1 text-xs">
      <header className="flex items-center justify-between">
        <span className="font-medium text-text-1">{title}</span>
        <span className="flex">
          <Button
            size="icon"
            variant="ghost"
            className="size-6"
            aria-label="Previous month"
            onClick={() => shift(-1)}
          >
            <ChevronLeft className="size-3.5" />
          </Button>
          <Button
            size="icon"
            variant="ghost"
            className="size-6"
            aria-label="Next month"
            onClick={() => shift(1)}
          >
            <ChevronRight className="size-3.5" />
          </Button>
        </span>
      </header>
      <div role="grid" className="grid grid-cols-7 text-center">
        {WEEKDAYS.map((w, i) => (
          <span key={i} aria-hidden className="py-0.5 text-text-3">
            {w}
          </span>
        ))}
        {cells.map((cell) => {
          const inWeek = cell >= viewed && cell <= addDays(viewed, 6);
          const outside = cell.slice(0, 7) !== month.slice(0, 7);
          return (
            <button
              key={cell}
              type="button"
              data-in-week={inWeek || undefined}
              aria-label={cell}
              aria-current={cell === today ? "date" : undefined}
              onClick={() => onPick(cell)}
              className={`relative grid h-7 place-items-center ${inWeek ? "bg-(--state-active)" : "hover:bg-(--state-hover)"} ${
                outside ? "text-text-3" : "text-text-1"
              }`}
            >
              <span
                className={`grid size-6 place-items-center rounded-full ${cell === today ? "bg-primary text-primary-foreground" : ""}`}
              >
                {Number(cell.slice(8))}
              </span>
              {busy.has(cell) ? (
                <span
                  aria-label="has commitments"
                  className="absolute bottom-0.5 size-1 rounded-full bg-text-2"
                />
              ) : null}
            </button>
          );
        })}
      </div>
    </section>
  );
}
