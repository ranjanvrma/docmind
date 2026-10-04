import { ArrowRight, CheckCircle2, FileText, FileUp, Loader2, Lock, RotateCcw, TriangleAlert, XCircle } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useCallback, useEffect, useMemo, useRef, useState, type DragEvent } from "react";
import { Link } from "react-router";
import { toast } from "sonner";

import { duration, ease, listItem, spring, stagger } from "@/components/animations/motion";
import { MovingBorder } from "@/components/effects/Background";
import { Button } from "@/components/ui/button";
import { ErrorState } from "@/components/ui/feedback";
import { api } from "@/lib/api";
import { emit } from "@/lib/events";
import { formatBytes, pluralize } from "@/lib/format";
import { isPendingStatus, useDocuments, useHealth, useInvalidateDocuments } from "@/lib/queries";
import type { DocumentInfo, ProcessItem, UploadItem } from "@/lib/types";
import { cn } from "@/lib/utils";
import { PipelineProgress, type PipelinePhase } from "./PipelineProgress";

interface Result {
  filename: string;
  size: number;
  upload?: UploadItem;
  process?: ProcessItem;
  clientError?: string;
}

type State =
  | { kind: "idle" }
  | { kind: "busy"; phase: Exclude<PipelinePhase, "done" | "error">; fraction: number; results: Result[] }
  | { kind: "finished"; results: Result[]; error?: unknown };

/**
 * Drop zone -> client-side checks -> upload (real progress) -> queue for
 * background processing -> result cards that follow the live document status.
 * Processing runs on the server's worker, so a slow PDF never ties up the
 * request (or hits a proxy timeout); the list polls while anything is pending.
 */
export function UploadZone({ id }: { id?: string }) {
  const { data: health } = useHealth();
  const { data: documents } = useDocuments();
  const invalidate = useInvalidateDocuments();
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [state, setState] = useState<State>({ kind: "idle" });

  const maxMb = health?.limits.max_upload_mb ?? 25;
  const maxFiles = health?.limits.max_files_per_upload ?? 20;
  const ttl = health?.session_ttl_hours ?? 24;
  const busy = state.kind === "busy";

  const run = useCallback(
    async (files: File[]) => {
      if (!files.length || busy) return;
      // Client-side checks mirror the server's; the server still validates everything.
      const results: Result[] = files.slice(0, maxFiles).map((f) => ({
        filename: f.name,
        size: f.size,
        clientError: !f.name.toLowerCase().endsWith(".pdf")
          ? "Only PDF files are supported."
          : f.size > maxMb * 1024 * 1024
            ? `Larger than the ${maxMb} MB limit.`
            : undefined,
      }));
      if (files.length > maxFiles) toast.warning(`Only the first ${maxFiles} files were taken.`);
      const validIndexes = results.flatMap((r, i) => (r.clientError ? [] : [i]));
      const valid = validIndexes.map((i) => files[i]);
      if (!valid.length) {
        setState({ kind: "finished", results });
        return;
      }

      setState({ kind: "busy", phase: "uploading", fraction: 0, results });
      try {
        const uploaded = await api.upload(valid, (fraction) =>
          setState((s) => (s.kind === "busy" ? { ...s, fraction } : s)),
        );
        // The API answers per file, in the order sent (filenames may come back sanitised).
        uploaded.forEach((item, i) => {
          if (validIndexes[i] !== undefined) results[validIndexes[i]].upload = item;
        });
        const ids = uploaded.filter((i) => i.doc_id).map((i) => i.doc_id!) as string[];
        if (ids.length) {
          const queued = await api.process(ids, false, true);
          queued.items.forEach((item) => {
            const r = results.find((x) => x.upload?.doc_id === item.doc_id);
            if (r) r.process = item;
          });
        }
        setState({ kind: "finished", results: [...results] });
      } catch (error) {
        setState({ kind: "finished", results: [...results], error });
      } finally {
        invalidate();
      }
    },
    [busy, maxFiles, maxMb, invalidate],
  );

  const onDrop = (event: DragEvent) => {
    event.preventDefault();
    setDragging(false);
    run(Array.from(event.dataTransfer.files));
  };

  const pending = documents?.filter((d) => d.status === "uploaded").length ?? 0;

  // Live status of the documents shown in the result list.
  const live = useMemo(() => new Map((documents ?? []).map((d) => [d.doc_id, d])), [documents]);
  const trackedIds = state.kind === "finished" ? state.results.map((r) => r.process?.doc_id ?? r.upload?.doc_id).filter(Boolean) : [];
  const tracked = trackedIds.map((id) => live.get(id!)).filter((d): d is DocumentInfo => !!d);
  const pendingKey = tracked.filter((d) => isPendingStatus(d.status)).map((d) => d.doc_id).join(",");
  const previousPending = useRef<Set<string>>(new Set());
  useEffect(() => {
    // Announce documents that just finished processing.
    const now = new Set(pendingKey ? pendingKey.split(",") : []);
    const finished = [...previousPending.current].filter((id) => !now.has(id)).map((id) => live.get(id));
    const indexed = finished.filter((d) => d?.status === "processed").length;
    if (indexed) {
      emit("scene-pulse");
      toast.success(`${pluralize(indexed, "document")} ready to search`);
    }
    previousPending.current = now;
  }, [pendingKey, live]);

  return (
    <section id={id} aria-label="Upload documents" className="scroll-mt-28">
      <motion.div
        onDragEnter={(e) => (e.preventDefault(), !busy && setDragging(true))}
        onDragOver={(e) => e.preventDefault()}
        onDragLeave={(e) => {
          if (!e.currentTarget.contains(e.relatedTarget as Node)) setDragging(false);
        }}
        onDrop={onDrop}
        animate={{ y: dragging ? -4 : 0, scale: dragging ? 1.005 : 1 }}
        transition={spring}
        className={cn(
          "glass relative overflow-hidden rounded-[1.4rem] transition-[box-shadow,border-color] duration-300",
          dragging && "border-accent/60 shadow-[var(--shadow-glass),0_0_60px_-10px_var(--accent-glow)]",
        )}
      >
        <MovingBorder active={dragging || busy} />
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 transition-opacity duration-300"
          style={{
            opacity: dragging ? 1 : 0.5,
            background: "radial-gradient(40rem 16rem at 50% 0%, var(--accent-soft), transparent 70%)",
          }}
        />

        <div className="relative px-6 py-10 sm:px-10 sm:py-12">
          <AnimatePresence mode="wait" initial={false}>
            {state.kind === "idle" && (
              <motion.div
                key="idle"
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -6 }}
                transition={{ duration: duration.normal, ease }}
                className="flex flex-col items-center text-center"
              >
                <motion.div
                  animate={dragging ? { y: [-2, -8, -2], rotate: [-3, 3, -3] } : { y: 0, rotate: 0 }}
                  transition={dragging ? { duration: 1.2, repeat: Infinity, ease: "easeInOut" } : spring}
                  className="mb-5 flex size-14 items-center justify-center rounded-2xl border border-line-strong bg-surface-2 text-accent shadow-[0_0_30px_-10px_var(--accent-glow)]"
                >
                  <FileUp className="size-6" />
                </motion.div>
                <p className="text-lg font-semibold">{dragging ? "Release to upload" : "Drop your documents here"}</p>
                <p className="mt-1.5 text-sm text-fg-muted">
                  PDF files supported · up to {maxMb} MB each · {maxFiles} at a time
                </p>
                <p className="mt-2 flex items-center gap-1.5 text-xs text-fg-faint">
                  <Lock className="size-3" aria-hidden />
                  Private to this browser · deleted after {ttl} h of inactivity or when the server restarts
                </p>
                <div className="mt-6 flex flex-wrap items-center justify-center gap-2">
                  <Button variant="primary" onClick={() => inputRef.current?.click()}>
                    Browse files
                  </Button>
                  {pending > 0 && (
                    <Button
                      variant="ghost"
                      onClick={async () => {
                        setState({ kind: "busy", phase: "processing", fraction: 1, results: [] });
                        try {
                          const res = await api.process(undefined, false, true);
                          const results = res.items.map((item) => ({ filename: item.filename, size: 0, process: item }));
                          setState({ kind: "finished", results });
                        } catch (error) {
                          setState({ kind: "finished", results: [], error });
                        } finally {
                          invalidate();
                        }
                      }}
                    >
                      Process {pluralize(pending, "pending document")}
                    </Button>
                  )}
                </div>
              </motion.div>
            )}

            {state.kind === "busy" && (
              <motion.div
                key="busy"
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -6 }}
                className="mx-auto max-w-xl"
              >
                <PipelineProgress phase={state.phase} uploadFraction={state.fraction} />
              </motion.div>
            )}

            {state.kind === "finished" && (
              <motion.div key="done" initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
                {!state.error && tracked.length > 0 && (
                  <div className="mx-auto mb-6 max-w-xl">
                    <PipelineProgress phase={tracked.some((d) => isPendingStatus(d.status)) ? "processing" : "done"} uploadFraction={1} />
                  </div>
                )}
                {state.error ? <ErrorState error={state.error} className="mb-4" /> : null}
                <ResultList results={state.results} live={live} />
                <div className="mt-6 flex justify-center gap-2">
                  <Button variant="glass" onClick={() => setState({ kind: "idle" })}>
                    <RotateCcw /> Upload more
                  </Button>
                  <Button variant="ghost" asChild>
                    <Link to="/search">
                      Search documents <ArrowRight />
                    </Link>
                  </Button>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        <input
          ref={inputRef}
          type="file"
          accept="application/pdf,.pdf"
          multiple
          className="sr-only"
          tabIndex={-1}
          aria-label="Choose PDF files"
          onChange={(e) => {
            run(Array.from(e.target.files ?? []));
            e.target.value = "";
          }}
        />
      </motion.div>
    </section>
  );
}

function ResultList({ results, live }: { results: Result[]; live: Map<string, DocumentInfo> }) {
  if (!results.length) return null;
  return (
    <motion.ul variants={stagger(0.06)} initial="hidden" animate="show" className="mx-auto grid max-w-2xl gap-2">
      {results.map((r, i) => {
        const process = r.process;
        const upload = r.upload;
        const docId = process?.doc_id ?? upload?.doc_id;
        const doc = docId ? live.get(docId) : undefined;
        const status = doc?.status ?? process?.status;
        const pending = status === "queued" || status === "processing";
        const ok = status === "processed";
        const failed = r.clientError || upload?.status === "rejected" || status === "failed";
        const warning = ok ? (doc?.warnings.length ? doc.warnings.join("; ") : null) : null;
        const message =
          r.clientError ??
          (upload?.status === "rejected" ? upload.detail : null) ??
          (status === "failed" ? (doc?.error ?? process?.detail) : null) ??
          (process?.skipped ? "Already indexed" : null) ??
          (pending ? (status === "queued" ? "Queued for processing…" : "Extracting, embedding and indexing…") : null) ??
          (upload?.status === "duplicate" ? upload.detail : null) ??
          (ok ? `Indexed ${pluralize(doc?.chunk_count ?? process?.chunk_count ?? 0, "chunk")}` : null) ??
          null;
        return (
          <motion.li key={`${r.filename}-${i}`} variants={listItem} className="glass flex items-center gap-3 rounded-xl px-4 py-3">
            <FileText className="size-4.5 shrink-0 text-fg-muted" />
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium">{r.filename}</p>
              <p className={cn("truncate text-xs", failed ? "text-danger" : "text-fg-muted")}>
                {r.size ? `${formatBytes(r.size)} · ` : ""}
                {message ?? "Uploaded"}
              </p>
              {warning && <p className="mt-0.5 text-xs text-warning">{warning}</p>}
            </div>
            {failed ? (
              <XCircle className="size-4.5 shrink-0 text-danger" />
            ) : pending ? (
              <Loader2 className="size-4.5 shrink-0 animate-spin text-accent" aria-label="Processing" />
            ) : ok || process?.skipped ? (
              <CheckCircle2 className="size-4.5 shrink-0 text-success" />
            ) : (
              <TriangleAlert className="size-4.5 shrink-0 text-warning" />
            )}
            {docId && !failed && (
              <Link to={`/documents/${docId}`} className="text-xs font-medium text-accent hover:underline">
                Open
              </Link>
            )}
          </motion.li>
        );
      })}
    </motion.ul>
  );
}
