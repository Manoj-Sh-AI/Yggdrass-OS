import * as React from "react";
import { cn } from "cn";

/**
 * The only way to put a background behind content. Hierarchy comes from the
 * surface ladder, not from borders: 0 canvas, 1 panel, 2 raised/hover,
 * 3 overlay (popover, menu), "sunken" for wells.
 */
export type SurfaceLevel = 0 | 1 | 2 | 3 | "sunken";
export type SurfaceRadius = "none" | "sm" | "md" | "lg" | "xl";

const LEVEL: Record<SurfaceLevel, string> = {
  0: "bg-surface-0",
  1: "bg-surface-1",
  2: "bg-surface-2",
  // Overlays are the one level that carries an edge and a shadow (B1).
  3: "bg-surface-3 shadow-lg border-hairline border-hairline-strong",
  sunken: "bg-surface-sunken",
};
const RADIUS: Record<SurfaceRadius, string> = {
  none: "rounded-none",
  sm: "rounded-sm",
  md: "rounded-md",
  lg: "rounded-lg",
  xl: "rounded-xl",
};

type SurfaceProps = React.HTMLAttributes<HTMLDivElement> & {
  level?: SurfaceLevel;
  radius?: SurfaceRadius;
  /** Frosted panel over the photograph. Panels (level 1) only. */
  glass?: boolean;
  /** Canvas over a scene photograph: adds the measured --scrim layer. Level 0 only. */
  scrim?: boolean;
  as?: "div" | "section" | "aside" | "nav" | "main" | "header" | "footer";
};

export function surfaceClass(level: SurfaceLevel, radius: SurfaceRadius, glass: boolean) {
  if (glass && level !== 1) throw new Error("Glass is for panels (level 1) only.");
  return cn(glass ? "surface-glass" : LEVEL[level], RADIUS[radius], "text-text-1");
}

export function Surface({
  level = 1,
  radius = "none",
  glass = false,
  scrim = false,
  as: Tag = "div",
  className,
  children,
  ...props
}: SurfaceProps) {
  if (scrim && level !== 0) throw new Error("The scrim belongs to the canvas (level 0).");
  return (
    <Tag
      data-slot="surface"
      data-level={level}
      className={cn(surfaceClass(level, radius, glass), scrim && "relative isolate", className)}
      {...props}
    >
      {scrim && <div aria-hidden className="surface-scrim -z-10" />}
      {children}
    </Tag>
  );
}

/** A panel: level 1, optionally glass. */
export function Panel(props: Omit<SurfaceProps, "level" | "scrim">) {
  return <Surface radius="xl" {...props} level={1} />;
}
