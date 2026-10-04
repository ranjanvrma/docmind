import { AlertTriangle, CircleSlash, ShieldCheck, Sparkles } from "lucide-react";
import { motion } from "motion/react";
import { useState } from "react";

import { fadeUp } from "@/components/animations/motion";
import { SourcesPanel } from "@/components/sources/SourcesPanel";
import { ErrorState } from "@/components/ui/feedback";
import { Badge } from "@/components/ui/primitives";
import { isAbstention } from "@/lib/citations";
import { AnswerContent } from "./AnswerContent";
import type { ChatTurn } from "./ChatProvider";
import { useChat } from "./ChatProvider";

function AnswerStatus({ turn }: { turn: ChatTurn }) {
  const r = turn.response!;
  if (isAbstention(r.answer))
    return (
      <Badge tone="warning">
        <CircleSlash className="size-3" /> Not found in your documents
      </Badge>
    );
  if (r.answered_from_documents)
    return (
      <Badge tone="success">
        <ShieldCheck className="size-3" /> Grounded in cited sources
      </Badge>
    );
  return (
    <Badge tone="warning">
      <AlertTriangle className="size-3" /> No valid citations
    </Badge>
  );
}

export function ChatTurnView({ turn }: { turn: ChatTurn }) {
  const { retry } = useChat();
  const [expanded, setExpanded] = useState<Set<number>>(new Set());

  const toggle = (n: number) =>
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(n)) next.delete(n);
      else next.add(n);
      return next;
    });
  const reveal = (n: number) => {
    setExpanded((prev) => new Set(prev).add(n));
    requestAnimationFrame(() => document.getElementById(`${turn.id}-source-${n}`)?.scrollIntoView({ behavior: "smooth", block: "center" }));
  };

  return (
    <motion.li variants={fadeUp} initial="hidden" animate="show" className="list-none space-y-3">
      {/* User question */}
      <div className="flex justify-end">
        <p className="max-w-[85%] whitespace-pre-line rounded-2xl rounded-br-md border border-line bg-surface-2 px-4 py-2.5 text-[14.5px]">
          {turn.question}
        </p>
      </div>

      {/* Assistant answer */}
      <div className="glass rounded-2xl rounded-tl-md p-5 sm:p-6">
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <span className="flex size-6 items-center justify-center rounded-lg bg-accent-soft text-accent">
            <Sparkles className="size-3.5" />
          </span>
          <span className="text-xs font-medium text-fg-muted">DocMind</span>
          {turn.status === "done" && <AnswerStatus turn={turn} />}
          {turn.docIds.length > 0 && <Badge>{turn.docIds.length === 1 ? "1 document" : `${turn.docIds.length} documents`}</Badge>}
        </div>

        {turn.status === "pending" && (
          <div aria-live="polite" aria-busy>
            <p className="mb-4 flex items-center gap-2 text-sm text-fg-muted">
              <span className="size-1.5 animate-pulse-soft rounded-full bg-accent" />
              Generating grounded answer…
            </p>
            <div className="space-y-2">
              <div className="skeleton h-3 w-full" />
              <div className="skeleton h-3 w-5/6" />
              <div className="skeleton h-3 w-2/3" />
            </div>
          </div>
        )}

        {turn.status === "error" && <ErrorState error={turn.error} onRetry={() => retry(turn.id)} />}

        {turn.status === "done" && turn.response && (
          <>
            <AnswerContent answer={turn.response.answer} sources={turn.response.sources} onReveal={reveal} />
            {turn.response.invalid_citations.length > 0 && (
              <p className="mt-4 flex items-start gap-2 rounded-xl border border-danger/25 bg-danger/5 px-3 py-2 text-xs text-danger">
                <AlertTriangle className="mt-0.5 size-3.5 shrink-0" />
                The model cited source {turn.response.invalid_citations.join(", ")}, which it was never given. Those citations are marked as invalid.
              </p>
            )}
            <SourcesPanel sources={turn.response.sources} expanded={expanded} onToggle={toggle} idPrefix={turn.id} />
          </>
        )}
      </div>
    </motion.li>
  );
}
