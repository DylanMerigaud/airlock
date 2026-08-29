import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center gap-1.5 rounded-[2px] border font-mono uppercase leading-none",
  {
    variants: {
      tone: {
        neutral: "border-line bg-card-sunk text-ink-mid",
        ink: "border-line bg-card text-ink",
        ember: "border-ember-line bg-ember-wash text-ember",
        amber: "border-warn-line bg-warn-wash text-warn",
        block: "border-block-line bg-block-wash text-block",
        pass: "border-pass-line bg-pass-wash text-pass",
        quiet: "border-transparent bg-transparent text-ink-soft",
      },
      size: {
        xs: "px-1.5 py-[3px] text-[9.5px] tracking-[0.14em]",
        sm: "px-2 py-1 text-[10.5px] tracking-[0.12em]",
      },
    },
    defaultVariants: { tone: "neutral", size: "sm" },
  },
);

export type BadgeProps = React.ComponentProps<"span"> & VariantProps<typeof badgeVariants>;

export function Badge({ className, tone, size, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ tone, size }), className)} {...props} />;
}
