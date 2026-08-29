"use client";

import * as React from "react";
import * as TooltipPrimitive from "@radix-ui/react-tooltip";
import { cn } from "@/lib/utils";

export const TooltipProvider = TooltipPrimitive.Provider;
export const Tooltip = TooltipPrimitive.Root;
export const TooltipTrigger = TooltipPrimitive.Trigger;

export function TooltipContent({
  className,
  sideOffset = 6,
  ...props
}: React.ComponentProps<typeof TooltipPrimitive.Content>) {
  return (
    <TooltipPrimitive.Portal>
      <TooltipPrimitive.Content
        sideOffset={sideOffset}
        className={cn(
          "z-50 max-w-[340px] rounded-[3px] border border-line bg-card px-2.5 py-2",
          "font-mono text-[11px] leading-relaxed text-ink-mid shadow-[0_12px_28px_-14px_rgba(23,21,15,0.45)]",
          className,
        )}
        {...props}
      />
    </TooltipPrimitive.Portal>
  );
}
