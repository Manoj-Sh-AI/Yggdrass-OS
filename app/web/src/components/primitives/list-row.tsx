"use client";
/**
 * One row of a dense navigation list (Phase D). Anatomy [derived, brief D]:
 *   [ icon 18px ] [ title: flex 1, one line, truncated ] [ status ~16px | hover actions ]
 * Title only: no description, no area, no dates. State is an icon in the status slot,
 * never a subtitle. Hover actions replace the status in the same slot, so nothing shifts.
 * Hover and active are foreground alpha (--state-hover / --state-active), so they work
 * unchanged on dark surfaces; active adds weight 600; focus is a 2px inset ring with no
 * background change; no left accent bar.
 */
import type { ReactNode } from "react";

type Props = {
  title: string;
  icon?: ReactNode;
  status?: ReactNode; // one icon, only when the state is not the default
  actions?: ReactNode; // revealed on hover / focus, in the status slot
  active?: boolean;
  depth?: number; // indentation level, 16px each [derived, 4px grid]
  onSelect?: () => void;
  children?: ReactNode; // optional second content (search snippet), one muted line
};

export function ListRow({
  title,
  icon,
  status,
  actions,
  active,
  depth = 0,
  onSelect,
  children,
}: Props) {
  return (
    <button
      type="button"
      title={title}
      aria-current={active ? "page" : undefined}
      onClick={onSelect}
      style={{ paddingInlineStart: `calc(var(--spacing) * ${4 * depth + 1})` }}
      className={`group/row flex w-full min-w-0 items-center gap-1.5 rounded-sm pe-1 text-left text-sm motion-xshort transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring ${
        children ? "min-h-(--row-h) flex-wrap py-1" : "h-(--row-h)"
      } ${active ? "bg-(--state-active) font-semibold text-text-1" : "text-text-1 hover:bg-(--state-hover)"}`}
    >
      <span
        aria-hidden
        className="grid size-4.5 shrink-0 place-items-center text-text-2"
      >
        {icon}
      </span>
      <span className="min-w-0 flex-1 truncate">{title}</span>
      <span className="relative grid h-4 w-4 shrink-0 place-items-center text-text-2">
        <span
          className={
            actions
              ? "group-hover/row:invisible group-focus-visible/row:invisible"
              : ""
          }
        >
          {status}
        </span>
        {actions ? (
          <span className="invisible absolute inset-0 grid place-items-center group-hover/row:visible group-focus-visible/row:visible">
            {actions}
          </span>
        ) : null}
      </span>
      {children ? (
        <span className="w-full truncate ps-6 text-xs text-text-3">
          {children}
        </span>
      ) : null}
    </button>
  );
}

/** Group header: carries the area name once, so rows never repeat it. */
export function ListGroupLabel({
  children,
  count,
}: {
  children: ReactNode;
  count?: number;
}) {
  return (
    <div className="flex h-(--row-h) items-center justify-between px-1 text-xs font-medium text-text-2">
      <span className="truncate">{children}</span>
      {count ? <span className="text-text-3">{count}</span> : null}
    </div>
  );
}
