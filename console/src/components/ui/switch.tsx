"use client";

import * as React from "react";
import { cn } from "@/lib/utils";

export type SwitchProps = Omit<React.ComponentProps<"button">, "onChange"> & {
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
};

/**
 * A square breaker, not a pill: hairline track, accent only when it is armed.
 * The children are the visible label and the accessible name.
 */
export function Switch({
  checked,
  onCheckedChange,
  className,
  children,
  disabled,
  onClick,
  ...props
}: SwitchProps) {
  return (
    <button
      {...props}
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      // Composed, never replaced: a Tooltip trigger passes its own onClick down
      // through Slot, and a plain spread would silently swallow the toggle.
      onClick={(event) => {
        onClick?.(event);
        if (event.defaultPrevented) return;
        onCheckedChange(!checked);
      }}
      className={cn(
        "group inline-flex items-center gap-2 text-left text-[12px] leading-none transition-colors",
        "disabled:pointer-events-none disabled:opacity-45",
        checked ? "text-accent" : "text-ink-soft hover:text-ink",
        className,
      )}
    >
      <span
        aria-hidden="true"
        className={cn(
          "flex h-[14px] w-[26px] shrink-0 items-center rounded-[2px] border transition-colors",
          checked ? "border-accent bg-accent-wash" : "border-line-strong bg-sunk",
        )}
      >
        <span
          className={cn(
            "block h-[8px] w-[8px] transition-transform duration-150",
            checked ? "translate-x-[15px] bg-accent" : "translate-x-[3px] bg-ink-soft",
          )}
        />
      </span>
      {children}
    </button>
  );
}
