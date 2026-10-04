import { Link } from "react-router";

import { StatusDot } from "@/components/ui/primitives";
import { Tooltip } from "@/components/ui/overlays";
import { ApiError } from "@/lib/errors";
import { useHealth } from "@/lib/queries";

/** Compact API status: online / search-only (no LLM) / offline. */
export function StatusIndicator({ compact = false }: { compact?: boolean }) {
  const { data, error, isPending } = useHealth();

  let tone: "success" | "warning" | "danger" | "neutral" = "neutral";
  let label = "Connecting";
  let hint = "Checking the DocMind API…";
  if (data) {
    tone = data.llm_configured ? "success" : "warning";
    label = data.llm_configured ? "Online" : "Search only";
    hint = data.llm_configured
      ? `API online · ${data.llm_provider} / ${data.llm_model}`
      : "API online. Question answering is off until an LLM is configured.";
  } else if (error && !isPending) {
    tone = "danger";
    label = error instanceof ApiError && error.kind === "storage_unavailable" ? "Index error" : "Offline";
    hint = error instanceof ApiError ? error.message : "Unable to connect to DocMind.";
  }

  return (
    <Tooltip content={hint} side="bottom">
      <Link
        to="/settings"
        className="inline-flex items-center gap-2 rounded-full px-2.5 py-1 text-xs text-fg-muted transition-colors hover:bg-surface-2 hover:text-fg"
        aria-label={`API status: ${label}. Open settings.`}
      >
        <StatusDot tone={tone} pulse={tone === "success"} />
        {!compact && <span>{label}</span>}
      </Link>
    </Tooltip>
  );
}
