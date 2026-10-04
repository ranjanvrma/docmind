import { useRef, type ComponentProps, type PointerEvent } from "react";

import { cn } from "@/lib/utils";

/**
 * Glass card with a soft light that follows the pointer (Magic Card-style).
 * The pointer position is written to CSS variables directly, so moving the
 * mouse never re-renders React.
 */
export function GlowCard({ className, children, selected = false, onPointerMove, ...props }: ComponentProps<"div"> & { selected?: boolean }) {
  const ref = useRef<HTMLDivElement>(null);

  const handleMove = (event: PointerEvent<HTMLDivElement>) => {
    const el = ref.current;
    if (el) {
      const rect = el.getBoundingClientRect();
      el.style.setProperty("--gx", `${event.clientX - rect.left}px`);
      el.style.setProperty("--gy", `${event.clientY - rect.top}px`);
    }
    onPointerMove?.(event);
  };

  return (
    <div
      ref={ref}
      onPointerMove={handleMove}
      className={cn(
        "glass group/glow relative overflow-hidden rounded-2xl transition-[border-color,box-shadow,transform] duration-300",
        "hover:border-line-strong hover:shadow-[var(--shadow-glass),0_0_0_1px_var(--border-strong)]",
        selected && "border-accent/50 shadow-[var(--shadow-glass),0_0_0_1px_var(--accent-glow),0_0_40px_-12px_var(--accent-glow)]",
        className,
      )}
      {...props}
    >
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 opacity-0 transition-opacity duration-300 group-hover/glow:opacity-100"
        style={{
          background:
            "radial-gradient(320px circle at var(--gx, 50%) var(--gy, 0%), var(--accent-soft), transparent 70%)",
        }}
      />
      <div className="relative">{children}</div>
    </div>
  );
}
