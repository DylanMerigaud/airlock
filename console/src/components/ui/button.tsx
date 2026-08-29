"use client";

import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-[2px] font-medium transition-colors duration-150 disabled:pointer-events-none disabled:opacity-45 [&_svg]:pointer-events-none [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        // The only filled accent in the product. Reserved for Run airlock.
        accent: "bg-accent text-surface hover:bg-[#0b4fae] active:bg-[#0b4fae]",
        outline: "border border-line-strong bg-surface text-ink hover:bg-sunk",
        ghost: "text-ink-soft hover:bg-sunk hover:text-ink",
        danger: "border border-line-strong bg-surface text-block hover:bg-sunk",
      },
      size: {
        sm: "h-7 px-2.5 text-[12px]",
        md: "h-8 px-3 text-[13px]",
        lg: "h-8 px-4 text-[13px] font-medium",
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
