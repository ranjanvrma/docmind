import { FileText, MessageSquareText, Search, Trash2 } from "lucide-react";
import { motion } from "motion/react";
import { Link, useNavigate } from "react-router";

import { listItem } from "@/components/animations/motion";
import { GlowCard } from "@/components/effects/GlowCard";
import { Tooltip } from "@/components/ui/overlays";
import { formatBytes, formatRelative, pluralize } from "@/lib/format";
import type { DocumentInfo } from "@/lib/types";
import { DeleteDocumentDialog } from "./DeleteDocumentDialog";
import { DocumentStatusBadge } from "./DocumentStatus";

function IconAction({ label, to, icon: Icon }: { label: string; to: string; icon: typeof Search }) {
  return (
    <Tooltip content={label}>
      <Link
        to={to}
        aria-label={label}
        onClick={(e) => e.stopPropagation()}
        className="inline-flex size-8 items-center justify-center rounded-lg text-fg-muted transition-colors hover:bg-surface-2 hover:text-fg"
      >
        <Icon className="size-4" />
      </Link>
    </Tooltip>
  );
}

export function DocumentCard({ document }: { document: DocumentInfo }) {
  const navigate = useNavigate();
  const open = () => navigate(`/documents/${document.doc_id}`);
  const category = document.classification?.label;

  return (
    <motion.li variants={listItem} layout exit="exit" className="list-none">
      <GlowCard
        role="link"
        tabIndex={0}
        aria-label={`Open ${document.filename}`}
        onClick={open}
        onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), open())}
        className="h-full cursor-pointer p-4 hover:-translate-y-0.5"
      >
        <div className="flex items-start gap-3">
          <div className="flex size-10 shrink-0 items-center justify-center rounded-xl border border-line bg-surface-2 text-accent">
            <FileText className="size-5" />
          </div>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium" title={document.filename}>
              {document.filename}
            </p>
            <p className="mt-0.5 text-xs text-fg-faint">
              {formatBytes(document.size_bytes)} · {formatRelative(document.uploaded_at)}
            </p>
          </div>
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-1.5">
          <DocumentStatusBadge status={document.status} />
          {category && <span className="rounded-full border border-line px-2 py-0.5 text-[11px] text-fg-muted">{category}</span>}
        </div>

        <div className="mt-4 flex items-center justify-between border-t border-line pt-3">
          <p className="font-mono text-[11.5px] text-fg-faint">
            {document.page_count ? pluralize(document.page_count, "page") : "–"} · {pluralize(document.chunk_count, "chunk")}
          </p>
          <div className="flex items-center gap-0.5 opacity-100 transition-opacity duration-200 md:opacity-0 md:group-hover/glow:opacity-100 md:group-focus-within/glow:opacity-100">
            {document.status === "processed" && (
              <>
                <IconAction label="Search this document" to={`/search?doc=${document.doc_id}`} icon={Search} />
                <IconAction label="Ask about this document" to={`/ask?doc=${document.doc_id}`} icon={MessageSquareText} />
              </>
            )}
            <span onClick={(e) => e.stopPropagation()} onKeyDown={(e) => e.stopPropagation()}>
              <DeleteDocumentDialog
                document={document}
                trigger={
                  <button
                    type="button"
                    aria-label={`Delete ${document.filename}`}
                    className="inline-flex size-8 items-center justify-center rounded-lg text-fg-muted transition-colors hover:bg-danger/10 hover:text-danger"
                  >
                    <Trash2 className="size-4" />
                  </button>
                }
              />
            </span>
          </div>
        </div>
      </GlowCard>
    </motion.li>
  );
}

export function DocumentCardSkeleton() {
  return (
    <div className="glass rounded-2xl p-4">
      <div className="flex gap-3">
        <div className="skeleton size-10 rounded-xl" />
        <div className="flex-1 space-y-2">
          <div className="skeleton h-3.5 w-3/4" />
          <div className="skeleton h-3 w-1/2" />
        </div>
      </div>
      <div className="skeleton mt-4 h-5 w-24 rounded-full" />
      <div className="skeleton mt-4 h-3 w-1/3" />
    </div>
  );
}
