import { FileUp, Search, X } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useMemo, useState } from "react";

import { DocumentGrid, DocumentGridSkeleton } from "@/components/documents/DocumentGrid";
import { PageHeader } from "@/components/layout/AppShell";
import { Button } from "@/components/ui/button";
import { DocumentIllustration, EmptyState, ErrorState } from "@/components/ui/feedback";
import { Input, Segmented } from "@/components/ui/primitives";
import { UploadZone } from "@/components/upload/UploadZone";
import { pluralize } from "@/lib/format";
import { useDocuments } from "@/lib/queries";
import type { DocumentStatus } from "@/lib/types";

type Filter = "all" | DocumentStatus;

export function DocumentsPage() {
  const { data, isPending, error, refetch } = useDocuments();
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<Filter>("all");
  const [showUpload, setShowUpload] = useState(false);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (data ?? [])
      .filter((d) => (status === "all" ? true : status === "uploaded" ? d.status !== "processed" && d.status !== "failed" : d.status === status))
      .filter((d) => !q || d.filename.toLowerCase().includes(q) || d.classification?.label.toLowerCase().includes(q))
      .sort((a, b) => b.uploaded_at.localeCompare(a.uploaded_at));
  }, [data, query, status]);

  const total = data?.length ?? 0;
  const chunks = (data ?? []).reduce((sum, d) => sum + d.chunk_count, 0);

  return (
    <>
      <PageHeader
        eyebrow="Library"
        title="Documents"
        description={total ? `${pluralize(total, "document")} · ${pluralize(chunks, "indexed passage")}` : "Your uploaded PDFs live here."}
        actions={
          <Button variant={showUpload ? "glass" : "primary"} onClick={() => setShowUpload((v) => !v)}>
            {showUpload ? <X /> : <FileUp />} {showUpload ? "Close" : "Upload"}
          </Button>
        }
      />

      <AnimatePresence initial={false}>
        {showUpload && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="overflow-hidden"
          >
            <div className="pb-8">
              <UploadZone />
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {total > 0 && (
        <div className="mb-6 flex flex-wrap items-center gap-3">
          <div className="relative min-w-[14rem] flex-1 sm:max-w-sm">
            <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-fg-faint" />
            <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Filter by name or category" aria-label="Filter documents" className="pl-9" />
          </div>
          <Segmented
            label="Filter by status"
            value={status}
            onChange={setStatus}
            options={[
              { value: "all", label: "All" },
              { value: "processed", label: "Indexed" },
              { value: "uploaded", label: "Pending" },
              { value: "failed", label: "Failed" },
            ]}
          />
        </div>
      )}

      {isPending ? (
        <DocumentGridSkeleton count={6} />
      ) : error ? (
        <ErrorState error={error} onRetry={() => refetch()} />
      ) : total === 0 ? (
        <EmptyState
          icon={<DocumentIllustration />}
          title="No documents yet"
          description="Upload a PDF to start searching and asking questions."
          action={
            <Button variant="primary" onClick={() => setShowUpload(true)}>
              <FileUp /> Upload document
            </Button>
          }
        />
      ) : filtered.length === 0 ? (
        <p className="glass rounded-2xl p-8 text-center text-sm text-fg-muted">No documents match these filters.</p>
      ) : (
        <DocumentGrid documents={filtered} />
      )}
    </>
  );
}
