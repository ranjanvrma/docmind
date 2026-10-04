import { ArrowUpRight, FileText } from "lucide-react";
import { motion } from "motion/react";
import { Link } from "react-router";

import { listItem } from "@/components/animations/motion";
import { GlowCard } from "@/components/effects/GlowCard";
import { pad2 } from "@/lib/format";
import type { SearchHit } from "@/lib/types";
import { SimilarityBar } from "./SimilarityBar";

/** One retrieved passage. The passage text is rendered as plain (escaped) text. */
export function SearchResultCard({ hit }: { hit: SearchHit }) {
  return (
    <motion.li variants={listItem} className="list-none">
      <GlowCard className="p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex min-w-0 items-center gap-3">
            <span className="font-mono text-xs font-medium text-accent">Source {pad2(hit.rank)}</span>
            <span className="h-3.5 w-px bg-line" />
            <span className="flex min-w-0 items-center gap-1.5 text-sm">
              <FileText className="size-3.5 shrink-0 text-fg-faint" />
              <span className="truncate font-medium">{hit.doc_name}</span>
            </span>
            <span className="shrink-0 rounded-md border border-line px-1.5 py-0.5 font-mono text-[11px] text-fg-muted">
              p. {hit.page_number}
            </span>
          </div>
          <SimilarityBar score={hit.score} delay={hit.rank * 0.05} />
        </div>
        <p className="mt-4 whitespace-pre-line text-[14.5px] leading-relaxed text-fg/90">{hit.text}</p>
        <div className="mt-4 flex justify-end">
          <Link
            to={`/documents/${hit.doc_id}?page=${hit.page_number}#page-${hit.page_number}`}
            className="inline-flex items-center gap-1 text-xs font-medium text-fg-muted transition-colors hover:text-accent"
          >
            Open in document <ArrowUpRight className="size-3.5" />
          </Link>
        </div>
      </GlowCard>
    </motion.li>
  );
}

export function SearchResultSkeleton() {
  return (
    <div className="glass rounded-2xl p-5">
      <div className="flex justify-between">
        <div className="skeleton h-4 w-56" />
        <div className="skeleton h-4 w-32" />
      </div>
      <div className="mt-5 space-y-2">
        <div className="skeleton h-3 w-full" />
        <div className="skeleton h-3 w-11/12" />
        <div className="skeleton h-3 w-3/4" />
      </div>
    </div>
  );
}
