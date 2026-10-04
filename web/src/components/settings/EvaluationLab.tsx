import { useMutation } from "@tanstack/react-query";
import { FlaskConical, Loader2, TrendingDown, TrendingUp } from "lucide-react";
import { motion } from "motion/react";
import { useState } from "react";

import { fadeUp, stagger } from "@/components/animations/motion";
import { Button } from "@/components/ui/button";
import { ErrorState } from "@/components/ui/feedback";
import { Tooltip } from "@/components/ui/overlays";
import { api } from "@/lib/api";
import type { EvaluationReport } from "@/lib/types";
import { cn } from "@/lib/utils";

function Delta({ now, before }: { now: number; before?: number }) {
  if (before === undefined) return null;
  const diff = now - before;
  if (Math.abs(diff) < 0.005) return <span className="text-[11px] text-fg-faint">no change</span>;
  const Icon = diff > 0 ? TrendingUp : TrendingDown;
  return (
    <span className={cn("inline-flex items-center gap-1 text-[11px]", diff > 0 ? "text-success" : "text-danger")}>
      <Icon className="size-3" />
      {diff > 0 ? "+" : ""}
      {(diff * 100).toFixed(0)} pts
    </span>
  );
}

/**
 * Runs the bundled retrieval evaluation against the *saved* settings, on a
 * temporary index, and compares with the previous run in this session. The
 * dataset is a small demo set: results are for comparing settings, not
 * evidence of real-world quality.
 */
export function EvaluationLab({ dirtyIndexing }: { dirtyIndexing: boolean }) {
  const [history, setHistory] = useState<EvaluationReport[]>([]);
  const run = useMutation({
    mutationFn: () => api.evaluateRetrieval([1, 3, 5]),
    onSuccess: (report) => setHistory((h) => [report, ...h].slice(0, 2)),
  });
  const [current, previous] = history;
  const metric = (r: EvaluationReport | undefined, k: number) => r?.metrics.find((m) => m.k === k)?.hit_rate;

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="max-w-lg text-sm text-fg-muted">
          Index the bundled sample PDFs with your saved settings and measure how often the right page is retrieved. Change chunking,
          save, run again and compare.
        </p>
        <Button variant="glass" onClick={() => run.mutate()} disabled={run.isPending}>
          {run.isPending ? <Loader2 className="animate-spin" /> : <FlaskConical />}
          {run.isPending ? "Measuring…" : history.length ? "Run again" : "Run evaluation"}
        </Button>
      </div>
      {dirtyIndexing && <p className="mt-3 text-xs text-warning">You have unsaved indexing changes. The evaluation uses saved settings.</p>}
      {run.error && <ErrorState error={run.error} className="mt-4" />}

      {current && (
        <motion.div key={current.run_at} variants={stagger(0.05)} initial="hidden" animate="show" className="mt-5">
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            {[
              { label: "Hit@1", value: metric(current, 1)!, before: metric(previous, 1), tip: "Share of questions whose top result comes from the right page." },
              { label: "Hit@3", value: metric(current, 3)!, before: metric(previous, 3), tip: "Right page somewhere in the top 3 results." },
              { label: "Hit@5", value: metric(current, 5)!, before: metric(previous, 5), tip: "Right page somewhere in the top 5 results." },
              { label: "MRR", value: current.mrr, before: previous?.mrr, tip: "Mean reciprocal rank: 1 if the right page is always first, 0.5 if always second." },
            ].map((tile) => (
              <motion.div key={tile.label} variants={fadeUp} className="rounded-xl border border-line bg-surface p-3.5">
                <Tooltip content={tile.tip}>
                  <p tabIndex={0} className="w-fit cursor-help text-[11px] uppercase tracking-wider text-fg-faint">
                    {tile.label}
                  </p>
                </Tooltip>
                <p className="mt-1 font-mono text-2xl font-medium tabular-nums">{tile.value.toFixed(2)}</p>
                <Delta now={tile.value} before={tile.before} />
              </motion.div>
            ))}
          </div>
          <p className="mt-3 font-mono text-[11.5px] text-fg-faint">
            chunk {current.settings.chunk_size} / overlap {current.settings.chunk_overlap} · {current.indexed_chunks} chunks ·{" "}
            {current.n_queries} questions · {current.n_documents} documents
          </p>
          {current.misses.length > 0 && (
            <details className="mt-3 text-sm">
              <summary className="cursor-pointer text-fg-muted hover:text-fg">{current.misses.length} questions missed in the top 5</summary>
              <ul className="mt-2 space-y-1 text-xs text-fg-muted">
                {current.misses.map((m) => (
                  <li key={m.id}>
                    “{m.query}” → top result {m.top1}
                  </li>
                ))}
              </ul>
            </details>
          )}
          <p className="mt-4 rounded-xl border border-warning/20 bg-warning/5 px-3 py-2 text-xs text-fg-muted">
            Demo dataset: 20 hand-written questions over 3 short fictional PDFs. Use it to compare settings, not as a measure of
            real-world accuracy.
          </p>
        </motion.div>
      )}
    </div>
  );
}
