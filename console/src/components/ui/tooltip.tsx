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
          "z-50 max-w-[340px] rounded-[3px] border border-line bg-hull px-2.5 py-2",
          "font-mono text-[11px] leading-relaxed text-ink-dim shadow-[0_10px_30px_-12px_rgba(0,0,0,0.9)]",
          className,
        )}
        {...props}
      />
    </TooltipPrimitive.Portal>
  );
}
