"use client";

import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap font-medium transition-colors duration-150 disabled:pointer-events-none disabled:opacity-45 [&_svg]:pointer-events-none [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        // The only filled accent in the product. Reserved for Run airlock.
        accent: "rounded-[3px] bg-ember text-card hover:bg-ember-deep active:bg-ember-deep",
        outline: "rounded-[3px] border border-line bg-card text-ink hover:border-ink-soft hover:bg-card-sunk",
        ghost: "rounded-[3px] text-ink-mid hover:bg-card-sunk hover:text-ink",
        danger: "rounded-[3px] border border-block-line bg-block-wash text-block hover:bg-[#f5d9d3]",
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
