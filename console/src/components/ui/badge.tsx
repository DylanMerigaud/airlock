import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

/**
 * A chip, the way a status sits beside a title in a media tool: hairline box,
 * no fill except the muted grey, no colour behind coloured text. Green never
 * carries small text here, so a pass chip is ink beside a green rule.
 */
const badgeVariants = cva(
  "inline-flex items-center gap-1.5 rounded-[2px] border font-mono uppercase leading-none",
  {
    variants: {
      tone: {
        neutral: "border-line bg-sunk text-ink-soft",
        ink: "border-line bg-surface text-ink",
        accent: "border-line bg-accent-wash text-accent",
        amber: "border-line bg-surface text-warn",
        block: "border-line bg-surface text-block",
        pass: "border-line bg-surface text-ink",
        quiet: "border-transparent bg-transparent text-ink-soft",
      },
      size: {
        xs: "px-1.5 py-[3px] text-[10px] tracking-[0.08em]",
        sm: "px-2 py-1 text-[11px] tracking-[0.07em]",
      },
    },
    defaultVariants: { tone: "neutral", size: "sm" },
  },
);

export type BadgeProps = React.ComponentProps<"span"> & VariantProps<typeof badgeVariants>;

export function Badge({ className, tone, size, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ tone, size }), className)} {...props} />;
}
