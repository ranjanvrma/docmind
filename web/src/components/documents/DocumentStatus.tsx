import { AlertCircle, CheckCircle2, Clock, Loader2 } from "lucide-react";

import { Badge } from "@/components/ui/primitives";
import type { DocumentStatus } from "@/lib/types";

export function DocumentStatusBadge({ status }: { status: DocumentStatus }) {
  if (status === "processed")
    return (
      <Badge tone="success">
        <CheckCircle2 className="size-3" /> Indexed
      </Badge>
    );
  if (status === "queued" || status === "processing")
    return (
      <Badge tone="accent">
        <Loader2 className="size-3 animate-spin" /> {status === "queued" ? "Queued" : "Processing"}
      </Badge>
    );
  if (status === "failed")
    return (
      <Badge tone="danger">
        <AlertCircle className="size-3" /> Failed
      </Badge>
    );
  return (
    <Badge tone="warning">
      <Clock className="size-3" /> Not processed
    </Badge>
  );
}
