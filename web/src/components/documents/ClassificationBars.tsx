import { motion } from "motion/react";

import { duration, ease } from "@/components/animations/motion";
import type { Classification } from "@/lib/types";

/** Per-category scores. Zero-shot scores are cosine similarities, not probabilities. */
export function ClassificationBars({ classification }: { classification: Classification }) {
  const entries = Object.entries(classification.scores).sort((a, b) => b[1] - a[1]);
  const max = Math.max(...entries.map(([, s]) => s), 1e-6);
  const isSupervised = classification.method === "supervised";

  return (
    <div>
      <ul className="space-y-2.5">
        {entries.map(([label, score], i) => (
          <li key={label} className="grid grid-cols-[7.5rem_1fr_3rem] items-center gap-3 text-[13px]">
            <span className={label === classification.label ? "font-medium text-fg" : "text-fg-muted"}>{label}</span>
            <div className="h-1.5 overflow-hidden rounded-full bg-surface-2">
              <motion.div
                className={`h-full rounded-full ${label === classification.label ? "bg-accent" : "bg-fg-faint/60"}`}
                initial={{ width: 0 }}
                animate={{ width: `${Math.max(0, (score / max) * 100)}%` }}
                transition={{ duration: duration.slow, ease, delay: i * 0.04 }}
              />
            </div>
            <span className="text-right font-mono text-xs text-fg-faint">{score.toFixed(3)}</span>
          </li>
        ))}
      </ul>
      <p className="mt-4 text-xs text-fg-faint">
        {isSupervised
          ? "Supervised classifier: scores are class probabilities from logistic regression."
          : "Zero-shot: scores are cosine similarities to category descriptions, not probabilities. This is a demo feature without measured accuracy."}
      </p>
    </div>
  );
}
