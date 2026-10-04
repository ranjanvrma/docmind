import { motion } from "motion/react";

import { duration, ease } from "@/components/animations/motion";
import { Tooltip } from "@/components/ui/overlays";
import { similarityPercent } from "@/lib/format";

/**
 * Retrieval similarity, deliberately labelled "Similarity" (not accuracy or
 * confidence): it is the cosine similarity between query and passage vectors,
 * which says nothing about whether an answer is correct.
 */
export function SimilarityBar({ score, delay = 0 }: { score: number; delay?: number }) {
  const pct = similarityPercent(score);
  return (
    <Tooltip content={`Vector similarity score from semantic retrieval (cosine ${score.toFixed(3)}). Higher means closer in meaning; it is not a measure of correctness.`}>
      <div className="flex cursor-help items-center gap-2.5" tabIndex={0} aria-label={`Similarity ${pct} percent`}>
        <span className="text-[11px] uppercase tracking-wider text-fg-faint">Similarity</span>
        <div className="h-1.5 w-24 overflow-hidden rounded-full bg-surface-2">
          <motion.div
            className="h-full rounded-full bg-gradient-to-r from-accent/70 to-accent"
            initial={{ width: 0 }}
            animate={{ width: `${pct}%` }}
            transition={{ duration: duration.slow, ease, delay }}
          />
        </div>
        <span className="w-8 font-mono text-xs text-fg-muted">{pct}%</span>
      </div>
    </Tooltip>
  );
}
