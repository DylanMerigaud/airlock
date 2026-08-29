"use client";

import * as React from "react";
import { cn } from "@/lib/utils";

export type SwitchProps = Omit<React.ComponentProps<"button">, "onChange"> & {
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
};

/**
 * A breaker switch, not a pill: square knob, hairline track, ember only when
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
        "disabled:pointer-events-none disabled:opacity-45",
        checked ? "text-ember" : "text-ink-soft hover:text-ink",
        className,
      )}
    >
      <span
        aria-hidden="true"
        className={cn(
          "flex h-[15px] w-[27px] shrink-0 items-center rounded-[2px] border transition-colors",
          checked ? "border-ember-line bg-ember-wash" : "border-line bg-card-sunk group-hover:border-ink-soft",
        )}
      >
        <span
          className={cn(
            "block h-[9px] w-[9px] transition-transform duration-150",
            checked ? "translate-x-[14px] bg-ember" : "translate-x-[2px] bg-ink-soft",
          )}
        />
      </span>
      {children}
    </button>
  );
}
