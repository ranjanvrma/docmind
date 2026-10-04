import { AlertTriangle, RotateCw } from "lucide-react";
import { motion } from "motion/react";
import type { ReactNode } from "react";

import { fadeUp } from "@/components/animations/motion";
import { describeError } from "@/lib/errors";
import { cn } from "@/lib/utils";
import { Button } from "./button";

/** Friendly error panel. Only safe, user-facing details are ever shown (see lib/errors.ts). */
export function ErrorState({ error, onRetry, className }: { error: unknown; onRetry?: () => void; className?: string }) {
  const { title, detail } = describeError(error);
  return (
    <div role="alert" className={cn("glass flex items-start gap-3 rounded-2xl border-danger/25 p-4", className)}>
      <AlertTriangle className="mt-0.5 size-4.5 shrink-0 text-danger" />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium">{title}</p>
        {detail && <p className="mt-1 break-words text-sm text-fg-muted">{detail}</p>}
      </div>
      {onRetry && (
        <Button size="sm" variant="ghost" onClick={onRetry}>
          <RotateCw /> Retry
        </Button>
      )}
    </div>
  );
}

export function EmptyState({
  icon,
  title,
  description,
  action,
  className,
}: {
  icon: ReactNode;
  title: string;
  description: string;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <motion.div
      variants={fadeUp}
      initial="hidden"
      animate="show"
      className={cn("glass flex flex-col items-center rounded-2xl px-6 py-14 text-center", className)}
    >
      <div className="relative mb-5">
        <div aria-hidden className="absolute inset-0 -z-10 scale-150 rounded-full bg-accent/10 blur-2xl" />
        {icon}
      </div>
      <h2 className="text-lg font-semibold">{title}</h2>
      <p className="mt-1.5 max-w-sm text-sm text-fg-muted">{description}</p>
      {action && <div className="mt-6">{action}</div>}
    </motion.div>
  );
}

/** Minimal document illustration for empty states. */
export function DocumentIllustration() {
  return (
    <svg viewBox="0 0 64 64" className="size-16" fill="none" aria-hidden>
      <rect x="14" y="8" width="34" height="44" rx="5" fill="var(--surface-2)" stroke="var(--border-strong)" />
      <rect x="18" y="12" width="34" height="44" rx="5" fill="var(--bg-3)" stroke="var(--accent)" strokeOpacity="0.5" />
      {[22, 28, 34, 40].map((y, i) => (
        <rect key={y} x="24" y={y} width={[20, 16, 22, 12][i]} height="2.4" rx="1.2" fill="var(--fg)" fillOpacity="0.22" />
      ))}
      <circle cx="47" cy="47" r="7" fill="var(--accent-soft)" stroke="var(--accent)" />
      <path d="M47 44v6M44 47h6" stroke="var(--accent)" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}
