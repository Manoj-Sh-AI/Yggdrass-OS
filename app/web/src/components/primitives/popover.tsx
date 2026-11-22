"use client";
import * as React from "react";
import { cn } from "cn";
import { Popover as PopoverPrimitive } from "radix-ui";

/** Popovers are the overlay level of the ladder: surface-3 + shadow-lg + 0.5px edge (B1). */
export const Popover = PopoverPrimitive.Root;
export const PopoverTrigger = PopoverPrimitive.Trigger;
export const PopoverClose = PopoverPrimitive.Close;

export function PopoverContent({
  className,
  align = "start",
  sideOffset = 6,
  ...props
}: React.ComponentProps<typeof PopoverPrimitive.Content>) {
  return (
    <PopoverPrimitive.Portal>
      <PopoverPrimitive.Content
        data-slot="popover-content"
        align={align}
        sideOffset={sideOffset}
        className={cn(
          "z-50 min-w-48 rounded-lg border-hairline border-hairline-strong bg-surface-3 p-1 text-text-1 shadow-lg outline-none",
          className,
        )}
        {...props}
      />
    </PopoverPrimitive.Portal>
  );
}

/** A row inside a popover menu: 28px, the row rhythm (--row-h). */
export function PopoverItem({ className, ...props }: React.ComponentProps<"button">) {
  return (
    <button
      type="button"
      className={cn(
        "flex h-7 w-full items-center gap-2 rounded-sm px-2 text-left text-sm text-text-1 hover:bg-surface-2 focus-visible:outline-2 focus-visible:outline-ring disabled:text-text-disabled",
        className,
      )}
      {...props}
    />
  );
}
