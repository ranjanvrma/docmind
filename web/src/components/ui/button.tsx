import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import type { ComponentProps } from "react";

import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex shrink-0 items-center justify-center gap-2 whitespace-nowrap rounded-xl text-sm font-medium transition-[color,background-color,border-color,box-shadow,transform] duration-200 active:scale-[0.98] disabled:pointer-events-none disabled:opacity-45 [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        primary:
          "relative overflow-hidden bg-accent text-accent-fg shadow-[0_0_0_1px_var(--accent-glow),0_8px_30px_-8px_var(--accent-glow)] hover:bg-accent-strong hover:shadow-[0_0_0_1px_var(--accent-glow),0_10px_40px_-6px_var(--accent-glow)]",
        glass: "glass text-fg hover:border-line-strong hover:bg-surface-2",
        ghost: "text-fg-muted hover:bg-surface-2 hover:text-fg",
        outline: "border border-line text-fg hover:border-line-strong hover:bg-surface",
        danger: "border border-danger/30 bg-danger/10 text-danger hover:bg-danger/20",
      },
      size: {
        sm: "h-8 px-3 text-[13px]",
        md: "h-10 px-4",
        lg: "h-12 px-6 text-[15px]",
        icon: "size-9",
      },
    },
    defaultVariants: { variant: "glass", size: "md" },
  },
);

export interface ButtonProps extends ComponentProps<"button">, VariantProps<typeof buttonVariants> {
  asChild?: boolean;
  /** Adds a slow light sweep (used only for the primary call to action). */
  shimmer?: boolean;
}

export function Button({ className, variant, size, asChild = false, shimmer = false, children, ...props }: ButtonProps) {
  const Comp = asChild ? Slot : "button";
  return (
    <Comp className={cn(buttonVariants({ variant, size }), className)} {...props}>
      {shimmer ? (
        <>
          <span
            aria-hidden
            className="pointer-events-none absolute inset-0 -translate-x-full animate-[beam_3.2s_ease-in-out_infinite] bg-[linear-gradient(110deg,transparent_30%,rgb(255_255_255/0.45)_50%,transparent_70%)]"
          />
          <span className="relative inline-flex items-center gap-2">{children}</span>
        </>
      ) : (
        children
      )}
    </Comp>
  );
}
