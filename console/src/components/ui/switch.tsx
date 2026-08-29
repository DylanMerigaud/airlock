"use client";

import * as React from "react";
import { cn } from "@/lib/utils";

export type SwitchProps = Omit<React.ComponentProps<"button">, "onChange"> & {
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
};

/**
 * A breaker switch, not a pill: square knob, hairline track, amber only when
 * it is armed. The children are the visible label and the accessible name.
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
        "group inline-flex items-center gap-2 text-left transition-colors",
        "font-mono text-[10.5px] uppercase leading-none tracking-[0.12em]",
        "disabled:pointer-events-none disabled:opacity-40",
        checked ? "text-amber" : "text-ink-faint hover:text-ink-dim",
        className,
      )}
    >
      <span
        aria-hidden="true"
        className={cn(
          "flex h-[14px] w-[26px] shrink-0 items-center rounded-[2px] border transition-colors",
          checked
            ? "border-amber/60 bg-amber-shade"
            : "border-line bg-panel-2 group-hover:border-[#39404b]",
        )}
      >
        <span
          className={cn(
            "block h-[8px] w-[8px] transition-transform duration-150",
            checked ? "translate-x-[14px] bg-amber" : "translate-x-[2px] bg-ink-faint",
          )}
        />
      </span>
      {children}
    </button>
  );
}
