import { ArrowUpRight, ChevronDown } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { Link } from "react-router";

import { duration, ease } from "@/components/animations/motion";
import { SimilarityBar } from "@/components/search/SimilarityBar";
import { pad2 } from "@/lib/format";
import type { Source } from "@/lib/types";
import { cn } from "@/lib/utils";

/**
 * "Sources used": exactly the passages that were sent to the LLM for this
 * answer, cited ones first. Each expands to show its retrieved passage.
 */
export function SourcesPanel({
  sources,
  expanded,
  onToggle,
  idPrefix,
}: {
  sources: Source[];
  expanded: Set<number>;
  onToggle: (n: number) => void;
  idPrefix: string;
}) {
  if (!sources.length) return null;
  const ordered = [...sources].sort((a, b) => Number(b.cited) - Number(a.cited) || a.source_number - b.source_number);
  const citedCount = sources.filter((s) => s.cited).length;

  return (
    <div className="mt-5 border-t border-line pt-4">
      <p className="mb-2.5 text-xs font-medium uppercase tracking-[0.12em] text-fg-faint">
        Sources used · {citedCount} cited of {sources.length} retrieved
      </p>
      <motion.ul layout className="space-y-1.5">
        {ordered.map((source) => {
          const open = expanded.has(source.source_number);
          const panelId = `${idPrefix}-source-${source.source_number}`;
          return (
            <motion.li layout key={source.source_number} id={panelId} className="overflow-hidden rounded-xl border border-line bg-surface">
              <button
                type="button"
                aria-expanded={open}
                aria-controls={`${panelId}-body`}
                onClick={() => onToggle(source.source_number)}
                className="flex w-full items-center gap-3 px-3.5 py-2.5 text-left text-[13px] transition-colors hover:bg-surface-2"
              >
                <span className={cn("font-mono text-xs font-medium", source.cited ? "text-accent" : "text-fg-faint")}>{pad2(source.source_number)}</span>
                <span className="min-w-0 flex-1 truncate">
                  {source.doc_name} <span className="text-fg-faint">— p.{source.page_number}</span>
                </span>
                <span className={cn("hidden rounded-full border px-2 py-0.5 text-[10.5px] sm:inline", source.cited ? "border-accent/30 text-accent" : "border-line text-fg-faint")}>
                  {source.cited ? "cited" : "not cited"}
                </span>
                <ChevronDown className={cn("size-4 shrink-0 text-fg-faint transition-transform duration-200", open && "rotate-180")} />
              </button>
              <AnimatePresence initial={false}>
                {open && (
                  <motion.div
                    id={`${panelId}-body`}
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: "auto", opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    transition={{ duration: duration.normal, ease }}
                  >
                    <div className="space-y-3 border-t border-line px-3.5 py-3">
                      <p className="whitespace-pre-line text-[13.5px] leading-relaxed text-fg-muted">{source.text}</p>
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <SimilarityBar score={source.score} />
                        <Link
                          to={`/documents/${source.doc_id}?page=${source.page_number}#page-${source.page_number}`}
                          className="inline-flex items-center gap-1 text-xs font-medium text-accent hover:underline"
                        >
                          Open in document <ArrowUpRight className="size-3.5" />
                        </Link>
                      </div>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </motion.li>
          );
        })}
      </motion.ul>
    </div>
  );
}
