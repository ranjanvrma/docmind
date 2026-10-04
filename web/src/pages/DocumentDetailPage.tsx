import { AlertTriangle, ArrowLeft, MessageSquareText, RefreshCw, Search, Trash2 } from "lucide-react";
import { motion } from "motion/react";
import { useEffect, useMemo } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router";
import { toast } from "sonner";

import { fadeUp, stagger } from "@/components/animations/motion";
import { ClassificationBars } from "@/components/documents/ClassificationBars";
import { DeleteDocumentDialog } from "@/components/documents/DeleteDocumentDialog";
import { DocumentStatusBadge } from "@/components/documents/DocumentStatus";
import { Button } from "@/components/ui/button";
import { ErrorState } from "@/components/ui/feedback";
import { Skeleton } from "@/components/ui/primitives";
import { describeError } from "@/lib/errors";
import { formatBytes, formatDate } from "@/lib/format";
import { useDocument, useDocumentChunks, useReprocessDocument } from "@/lib/queries";
import type { DocumentChunk } from "@/lib/types";
import { cn } from "@/lib/utils";

function Meta({ label, value, mono = false }: { label: string; value: React.ReactNode; mono?: boolean }) {
  return (
    <div>
      <dt className="text-xs text-fg-faint">{label}</dt>
      <dd className={cn("mt-1 text-sm", mono && "break-all font-mono text-[12.5px]")}>{value}</dd>
    </div>
  );
}

export function DocumentDetailPage() {
  const { id = "" } = useParams();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const highlightPage = Number(params.get("page")) || null;

  const doc = useDocument(id);
  const chunks = useDocumentChunks(id, doc.data?.status === "processed");
  const reprocess = useReprocessDocument();

  const pages = useMemo(() => {
    const byPage = new Map<number, DocumentChunk[]>();
    (chunks.data ?? []).forEach((c) => byPage.set(c.page_number, [...(byPage.get(c.page_number) ?? []), c]));
    return [...byPage.entries()].sort((a, b) => a[0] - b[0]);
  }, [chunks.data]);

  // Deep links from citations (?page=7#page-7): scroll once the content exists.
  useEffect(() => {
    if (highlightPage && pages.length) {
      document.getElementById(`page-${highlightPage}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, [highlightPage, pages.length]);

  if (doc.isPending)
    return (
      <div className="space-y-4">
        <Skeleton className="h-5 w-32" />
        <Skeleton className="h-9 w-2/3" />
        <Skeleton className="h-40 w-full rounded-2xl" />
      </div>
    );
  if (doc.error) return <ErrorState error={doc.error} onRetry={() => doc.refetch()} />;
  const d = doc.data!;

  return (
    <motion.div variants={stagger(0.06)} initial="hidden" animate="show">
      <motion.div variants={fadeUp}>
        <Link to="/documents" className="mb-6 inline-flex items-center gap-1.5 text-sm text-fg-muted hover:text-fg">
          <ArrowLeft className="size-4" /> Documents
        </Link>
      </motion.div>

      <motion.div variants={fadeUp} className="mb-8 flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <DocumentStatusBadge status={d.status} />
            {d.classification && <span className="rounded-full border border-line px-2 py-0.5 text-[11px] text-fg-muted">{d.classification.label}</span>}
          </div>
          <h1 className="break-words text-2xl font-semibold tracking-tight sm:text-3xl">{d.filename}</h1>
        </div>
        <div className="flex flex-wrap gap-2">
          {d.status === "processed" && (
            <>
              <Button variant="glass" size="sm" asChild>
                <Link to={`/search?doc=${d.doc_id}`}>
                  <Search /> Search
                </Link>
              </Button>
              <Button variant="glass" size="sm" asChild>
                <Link to={`/ask?doc=${d.doc_id}`}>
                  <MessageSquareText /> Ask
                </Link>
              </Button>
            </>
          )}
          <Button
            variant="ghost"
            size="sm"
            disabled={reprocess.isPending || d.status === "queued" || d.status === "processing"}
            onClick={() =>
              reprocess.mutate(d.doc_id, {
                onSuccess: (res) => {
                  if (res.items[0]?.status === "failed") toast.error(res.items[0].detail ?? "Processing failed");
                  else toast.message("Processing in the background", { description: "The status updates here when it finishes." });
                },
                onError: (e) => toast.error(describeError(e).title),
              })
            }
          >
            <RefreshCw className={reprocess.isPending ? "animate-spin" : ""} /> {d.status === "processed" ? "Re-index" : "Process"}
          </Button>
          <DeleteDocumentDialog
            document={d}
            onDeleted={() => navigate("/documents")}
            trigger={
              <Button variant="danger" size="sm">
                <Trash2 /> Delete
              </Button>
            }
          />
        </div>
      </motion.div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[20rem_minmax(0,1fr)]">
        <motion.aside variants={fadeUp} className="space-y-4 lg:sticky lg:top-24 lg:self-start">
          <div className="glass rounded-2xl p-5">
            <dl className="grid grid-cols-2 gap-4">
              <Meta label="Pages" value={d.page_count || "–"} />
              <Meta label="Indexed passages" value={d.chunk_count} />
              <Meta label="Empty pages" value={d.empty_pages.length ? d.empty_pages.join(", ") : "None"} />
              <Meta label="Size" value={formatBytes(d.size_bytes)} />
              <Meta label="Uploaded" value={formatDate(d.uploaded_at)} />
              <Meta label="Processed" value={formatDate(d.processed_at)} />
              <div className="col-span-2">
                <Meta label="Document ID (content hash)" value={d.doc_id} mono />
              </div>
            </dl>
          </div>

          {(d.error || d.warnings.length > 0) && (
            <div className="glass space-y-2 rounded-2xl border-warning/25 p-4">
              {d.error && (
                <p className="flex gap-2 text-sm text-danger">
                  <AlertTriangle className="mt-0.5 size-4 shrink-0" /> {d.error}
                </p>
              )}
              {d.warnings.map((w) => (
                <p key={w} className="flex gap-2 text-sm text-warning">
                  <AlertTriangle className="mt-0.5 size-4 shrink-0" /> {w}
                </p>
              ))}
            </div>
          )}

          {d.classification && (
            <div className="glass rounded-2xl p-5">
              <p className="mb-4 text-sm font-medium">Category</p>
              <ClassificationBars classification={d.classification} />
            </div>
          )}

          {pages.length > 1 && (
            <nav aria-label="Pages" className="glass rounded-2xl p-4">
              <p className="mb-3 text-xs text-fg-faint">Jump to page</p>
              <div className="flex flex-wrap gap-1.5">
                {pages.map(([page]) => (
                  <a
                    key={page}
                    href={`#page-${page}`}
                    className={cn(
                      "inline-flex h-7 min-w-7 items-center justify-center rounded-lg border px-2 font-mono text-xs transition-colors",
                      page === highlightPage ? "border-accent/50 bg-accent-soft text-accent" : "border-line text-fg-muted hover:text-fg",
                    )}
                  >
                    {page}
                  </a>
                ))}
              </div>
            </nav>
          )}
        </motion.aside>

        <motion.section variants={fadeUp} aria-label="Indexed content" className="min-w-0">
          <p className="mb-3 text-xs font-medium uppercase tracking-[0.12em] text-fg-faint">Indexed passages, as the retriever sees them</p>
          {d.status !== "processed" ? (
            <p className="glass rounded-2xl p-6 text-sm text-fg-muted">This document has not been indexed yet, so there is no searchable content.</p>
          ) : chunks.isPending ? (
            <div className="space-y-3">
              <Skeleton className="h-32 w-full rounded-2xl" />
              <Skeleton className="h-32 w-full rounded-2xl" />
            </div>
          ) : chunks.error ? (
            <ErrorState error={chunks.error} onRetry={() => chunks.refetch()} />
          ) : (
            <div className="space-y-4">
              {pages.map(([page, items]) => (
                <article
                  key={page}
                  id={`page-${page}`}
                  className={cn(
                    "glass scroll-mt-28 rounded-2xl p-5 transition-shadow duration-500",
                    page === highlightPage && "border-accent/50 shadow-[var(--shadow-glass),0_0_0_1px_var(--accent-glow),0_0_50px_-15px_var(--accent-glow)]",
                  )}
                >
                  <header className="mb-3 flex items-center justify-between">
                    <h2 className="font-mono text-xs font-medium text-accent">Page {page}</h2>
                    <span className="text-[11px] text-fg-faint">{items.length === 1 ? "1 passage" : `${items.length} passages`}</span>
                  </header>
                  <div className="space-y-3">
                    {items.map((c) => (
                      <p key={c.chunk_id} className="whitespace-pre-line text-[14px] leading-relaxed text-fg/85">
                        {c.text}
                      </p>
                    ))}
                  </div>
                </article>
              ))}
            </div>
          )}
        </motion.section>
      </div>
    </motion.div>
  );
}
