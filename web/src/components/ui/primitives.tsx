/** Small presentational primitives (shadcn-style, owned by this project). */
import type { ComponentProps, ReactNode } from "react";

import { cn } from "@/lib/utils";

export function Badge({
  className,
  tone = "neutral",
  ...props
}: ComponentProps<"span"> & { tone?: "neutral" | "accent" | "success" | "warning" | "danger" | "violet" }) {
  const tones = {
    neutral: "border-line bg-surface text-fg-muted",
    accent: "border-accent/25 bg-accent-soft text-accent",
    success: "border-success/25 bg-success/10 text-success",
    warning: "border-warning/25 bg-warning/10 text-warning",
    danger: "border-danger/25 bg-danger/10 text-danger",
    violet: "border-accent-2/25 bg-accent-2-soft text-accent-2",
  } as const;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[11px] font-medium tracking-wide",
        tones[tone],
        className,
      )}
      {...props}
    />
  );
}

export function Kbd({ className, ...props }: ComponentProps<"kbd">) {
  return (
    <kbd
      className={cn(
        "inline-flex h-5 min-w-5 items-center justify-center rounded-md border border-line bg-surface-2 px-1.5 font-mono text-[10.5px] text-fg-muted",
        className,
      )}
      {...props}
    />
  );
}

export function Skeleton({ className, ...props }: ComponentProps<"div">) {
  return <div aria-hidden className={cn("skeleton", className)} {...props} />;
}

export function Input({ className, ...props }: ComponentProps<"input">) {
  return (
    <input
      className={cn(
        "h-10 w-full rounded-xl border border-line bg-surface px-3.5 text-sm text-fg placeholder:text-fg-faint transition-colors focus:border-accent/50 focus:bg-surface-2 focus:outline-none",
        className,
      )}
      {...props}
    />
  );
}

export function StatusDot({ tone, pulse = false }: { tone: "success" | "warning" | "danger" | "neutral"; pulse?: boolean }) {
  const colors = { success: "bg-success", warning: "bg-warning", danger: "bg-danger", neutral: "bg-fg-faint" };
  return (
    <span className="relative inline-flex size-2">
      {pulse && <span className={cn("absolute inset-0 animate-ping rounded-full opacity-60", colors[tone])} />}
      <span className={cn("relative inline-flex size-2 rounded-full", colors[tone])} />
    </span>
  );
}

/** Segmented control used for small enumerated settings (top-k, theme, motion). */
export function Segmented<T extends string | number>({
  value,
  options,
  onChange,
  label,
}: {
  value: T;
  options: { value: T; label: ReactNode }[];
  onChange: (value: T) => void;
  label: string;
}) {
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex rounded-xl border border-line bg-surface p-0.5">
      {options.map((option) => {
        const active = option.value === value;
        return (
          <button
            key={String(option.value)}
            type="button"
            role="radio"
            aria-checked={active}
            onClick={() => onChange(option.value)}
            className={cn(
              "h-7 rounded-[10px] px-3 text-[12.5px] font-medium transition-colors",
              active ? "bg-surface-2 text-fg shadow-[0_0_0_1px_var(--border-strong)]" : "text-fg-muted hover:text-fg",
            )}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
