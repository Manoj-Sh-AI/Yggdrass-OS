// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  blockHeight, blockMode, hourHeight, monthGrid, msToNextMinute, placement, scrollToNow, weekStart,
} from "@/features/calendar/grid";
import { MiniMonth } from "@/features/calendar/mini-month";
import { NowLine, useNow } from "@/features/calendar/now-line";

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe("density (13 visible hours, clamped)", () => {
  it.each([[728, 56], [520, 44], [300, 44], [1200, 72], [0, 56]])("%ipx -> %ipx per hour", (h, px) =>
    expect(hourHeight(h)).toBe(px));
});

describe("scroll to now", () => {
  it("puts now a third of the way down", () => {
    expect(scrollToNow(14 * 60, 56, 600)).toBe(14 * 56 - 200);
    expect(scrollToNow(60, 56, 600)).toBe(0); // never negative
  });
});

describe("short blocks", () => {
  it("switch rendering by height and never collapse", () => {
    expect(blockMode(56)).toBe("two-line");
    expect(blockMode(30)).toBe("one-line");
    expect(blockMode(14)).toBe("compact");
    expect(blockHeight(15, 56)).toBe(20); // 14px -> held at 20px
    expect(blockHeight(60, 56)).toBe(56);
  });
});

describe("overlaps", () => {
  it("up to three sit side by side with a 1px inset", () => {
    expect(placement({ lane: 1, lanes: 3 })).toMatchObject({ cascade: false, width: `calc(${100 / 3}% - 2px)` });
  });
  it("more than three cascade with a 24px indent", () => {
    expect(placement({ lane: 2, lanes: 5 })).toEqual({ left: "49px", width: "calc(100% - 50px)", cascade: true });
  });
});

describe("now line", () => {
  it("waits for the minute boundary, not 60s from mount", () => {
    expect(msToNextMinute(new Date(2026, 10, 22, 10, 30, 45, 500))).toBe(14_500);
  });
  it("advances on the minute and recomputes when the tab becomes visible", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2026, 10, 22, 10, 30, 45));
    let seen: Date | null = null;
    function Probe() {
      seen = useNow();
      return null;
    }
    render(<Probe />);
    act(() => vi.advanceTimersByTime(15_000));
    expect(seen!.getMinutes()).toBe(31);
    vi.setSystemTime(new Date(2026, 10, 22, 12, 0, 5)); // throttled background tab
    act(() => document.dispatchEvent(new Event("visibilitychange")));
    expect(seen!.getHours()).toBe(12);
  });
  it("sits at the minute's position in danger colour", () => {
    const { container } = render(<NowLine minute={600} hourPx={60} />);
    const line = container.querySelector("[data-now-line]") as HTMLElement;
    expect(line.style.top).toBe("599px");
    expect(line.className).toContain("bg-danger");
  });
});

describe("mini month", () => {
  it("is a Monday-first 6x7 grid", () => {
    const cells = monthGrid("2026-11-22");
    expect(cells).toHaveLength(42);
    expect(cells[0]).toBe("2026-10-26"); // 1 Nov 2026 is a Sunday
    expect(weekStart("2026-11-22")).toBe("2026-11-16");
  });
  it("bands the viewed week, circles today, one dot per busy day, picks a week", () => {
    const onPick = vi.fn();
    const { container } = render(
      <MiniMonth day="2026-11-18" today="2026-11-22" busy={new Set(["2026-11-20", "2026-11-20"])} onPick={onPick} />,
    );
    expect(container.querySelectorAll("[data-in-week]")).toHaveLength(7);
    expect(screen.getByRole("button", { name: "2026-11-22" }).getAttribute("aria-current")).toBe("date");
    expect(screen.getAllByLabelText("has commitments")).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: "2026-11-03" }));
    expect(onPick).toHaveBeenCalledWith("2026-11-03");
  });
});
