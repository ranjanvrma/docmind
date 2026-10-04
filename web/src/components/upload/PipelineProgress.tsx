import { Check, Loader2, X } from "lucide-react";
import { motion } from "motion/react";

import { cn } from "@/lib/utils";

export type PipelinePhase = "uploading" | "processing" | "done" | "error";

const STAGES = ["Upload", "Extract", "Chunk", "Embed", "Index"] as const;

/**
 * Honest pipeline view.
 *
 * Upload progress is real (bytes sent). Extraction, chunking, embedding and
 * indexing happen inside one server request that does not report progress,
 * so those four stages are shown together as "in progress" with an
 * indeterminate beam, never as fake percentages or fake stage timing.
 */
export function PipelineProgress({ phase, uploadFraction }: { phase: PipelinePhase; uploadFraction: number }) {
  const stageState = (i: number): "done" | "active" | "pending" | "error" => {
    if (phase === "error") return i === 0 && uploadFraction >= 1 ? "done" : "error";
    if (phase === "done") return "done";
    if (i === 0) return phase === "uploading" ? "active" : "done";
    return phase === "processing" ? "active" : "pending";
  };

  return (
    <div aria-live="polite">
      <ol className="relative grid grid-cols-5 gap-1">
        {STAGES.map((stage, i) => {
          const state = stageState(i);
          return (
            <li key={stage} className="flex flex-col items-center gap-2 text-center">
              <span
                className={cn(
                  "flex size-8 items-center justify-center rounded-full border text-xs transition-colors duration-300",
                  state === "done" && "border-success/40 bg-success/10 text-success",
                  state === "active" && "border-accent/50 bg-accent-soft text-accent shadow-[0_0_20px_-4px_var(--accent-glow)]",
                  state === "pending" && "border-line text-fg-faint",
                  state === "error" && "border-danger/40 bg-danger/10 text-danger",
                )}
              >
                {state === "done" ? (
                  <Check className="size-3.5" />
                ) : state === "active" ? (
                  <Loader2 className="size-3.5 animate-spin" />
                ) : state === "error" ? (
                  <X className="size-3.5" />
                ) : (
                  i + 1
                )}
              </span>
              <span className={cn("text-[11px] font-medium", state === "pending" ? "text-fg-faint" : "text-fg-muted")}>{stage}</span>
            </li>
          );
        })}
      </ol>

      <div className="relative mt-4 h-1 overflow-hidden rounded-full bg-surface-2">
        {phase === "uploading" && (
          <motion.div
            className="h-full rounded-full bg-accent"
            initial={{ width: 0 }}
            animate={{ width: `${Math.round(uploadFraction * 20)}%` }}
            transition={{ duration: 0.2 }}
          />
        )}
        {phase === "processing" && (
          <>
            <div className="absolute inset-y-0 left-0 w-1/5 rounded-full bg-success/60" />
            <div className="absolute inset-y-0 left-1/5 right-0 overflow-hidden">
              <div className="h-full w-1/3 animate-beam rounded-full bg-gradient-to-r from-transparent via-accent to-transparent" />
            </div>
          </>
        )}
        {phase === "done" && <div className="h-full w-full rounded-full bg-success/70" />}
        {phase === "error" && <div className="h-full w-full rounded-full bg-danger/50" />}
      </div>

      <p className="mt-3 text-center text-xs text-fg-muted">
        {phase === "uploading" && `Uploading… ${Math.round(uploadFraction * 100)}%`}
        {phase === "processing" && "Extracting text, creating chunks, generating embeddings and building the index…"}
        {phase === "done" && "Ready to search and ask."}
        {phase === "error" && "Processing stopped."}
      </p>
    </div>
  );
}
