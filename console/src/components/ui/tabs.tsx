"use client";

import * as React from "react";
import * as TabsPrimitive from "@radix-ui/react-tabs";
import { cn } from "@/lib/utils";

export const Tabs = TabsPrimitive.Root;

export function TabsList({ className, ...props }: React.ComponentProps<typeof TabsPrimitive.List>) {
  return <TabsPrimitive.List className={cn("flex items-stretch", className)} {...props} />;
}

/** The view switch in the top bar: underlined in the accent when active. */
export function TabsTrigger({
  className,
  ...props
}: React.ComponentProps<typeof TabsPrimitive.Trigger>) {
  return (
    <TabsPrimitive.Trigger
      className={cn(
        "relative -mb-px flex items-center gap-1.5 border-b-2 border-transparent px-3 py-2.5",
        "text-[13px] font-medium text-ink-soft transition-colors hover:text-ink",
        "data-[state=active]:border-accent data-[state=active]:text-ink",
        className,
      )}
      {...props}
    />
  );
}

/**
 * The segmented control inside the review column. Same underline vocabulary as
 * the view switch, one notch smaller, so a reviewer switches what they read
 * without the clip ever leaving the screen.
 */
export function SegmentTrigger({
  className,
  ...props
}: React.ComponentProps<typeof TabsPrimitive.Trigger>) {
  return (
    <TabsPrimitive.Trigger
      className={cn(
        "relative -mb-px flex items-center gap-1.5 border-b-2 border-transparent px-3 py-2",
        "text-[13px] font-medium text-ink-soft transition-colors hover:text-ink",
        "data-[state=active]:border-accent data-[state=active]:text-ink",
        className,
      )}
      {...props}
    />
  );
}

export function TabsContent({
  className,
  ...props
}: React.ComponentProps<typeof TabsPrimitive.Content>) {
  return <TabsPrimitive.Content className={cn("outline-none", className)} {...props} />;
}
