import type { KeyboardEvent } from "react";
/** Horizontal tab groups use one tab stop, arrow navigation and Home/End. */
export function planningTabsKeyDown(event: KeyboardEvent<HTMLElement>) {
  if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
  const tabs = Array.from(
    event.currentTarget.querySelectorAll<HTMLButtonElement>('[role="tab"]'),
  );
  if (!tabs.length) return;
  const index = tabs.indexOf(document.activeElement as HTMLButtonElement);
  const next =
    event.key === "Home"
      ? 0
      : event.key === "End"
        ? tabs.length - 1
        : (Math.max(0, index) +
            (event.key === "ArrowRight" ? 1 : -1) +
            tabs.length) %
          tabs.length;
  event.preventDefault();
  tabs[next].focus();
  tabs[next].click();
}
