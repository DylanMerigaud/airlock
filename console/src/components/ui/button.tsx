"use client";

import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap font-medium transition-colors duration-150 disabled:pointer-events-none disabled:opacity-40 [&_svg]:pointer-events-none [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        // The only filled accent in the product. Reserved for Run airlock.
        accent:
          "rounded-[3px] bg-amber text-void hover:bg-[#ffbe57] active:bg-amber-deep shadow-[0_1px_0_0_rgba(255,255,255,0.18)_inset]",
        outline:
          "rounded-[3px] border border-line bg-panel text-ink hover:border-[#39404b] hover:bg-panel-2",
        ghost: "rounded-[3px] text-ink-dim hover:bg-panel-2 hover:text-ink",
        danger:
          "rounded-[3px] border border-block-deep/60 bg-block-shade text-block hover:bg-[#4a1c1e]",
      },
      size: {
        sm: "h-7 px-2.5 text-[11px] tracking-[0.1em] uppercase font-mono",
        md: "h-9 px-4 text-[13px]",
        lg: "h-11 px-6 text-[13px] tracking-[0.12em] uppercase font-mono font-semibold",
        icon: "h-8 w-8",
      },
    },
    defaultVariants: { variant: "outline", size: "md" },
  },
);

export type ButtonProps = React.ComponentProps<"button"> &
  VariantProps<typeof buttonVariants> & { asChild?: boolean };

export function Button({ className, variant, size, asChild = false, ...props }: ButtonProps) {
  const Comp = asChild ? Slot : "button";
  return <Comp className={cn(buttonVariants({ variant, size }), className)} {...props} />;
}

export { buttonVariants };
