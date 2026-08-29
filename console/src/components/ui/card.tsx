import * as React from "react";
import { cn } from "@/lib/utils";

/** A white surface on the ground, held by a hairline. No shadow, no fill. */
export function Panel({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      className={cn("relative rounded-[4px] border border-line bg-surface", className)}
      {...props}
    />
  );
}

export function PanelHeader({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      className={cn(
        "flex items-center justify-between gap-3 border-b border-line px-3 py-2",
        className,
      )}
      {...props}
    />
  );
}

export function PanelTitle({ className, ...props }: React.ComponentProps<"h2">) {
  return <h2 className={cn("label-micro text-ink-soft", className)} {...props} />;
}

export function PanelBody({ className, ...props }: React.ComponentProps<"div">) {
  return <div className={cn("px-3 py-3", className)} {...props} />;
}
