import { Trash2 } from "lucide-react";
import { useState, type ReactNode } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle, DialogTrigger } from "@/components/ui/overlays";
import { describeError } from "@/lib/errors";
import { useDeleteDocument } from "@/lib/queries";
import type { DocumentInfo } from "@/lib/types";

/** Confirmation before deleting: removes the stored PDF, its vectors and its registry entry. */
export function DeleteDocumentDialog({
  document,
  trigger,
  onDeleted,
}: {
  document: DocumentInfo;
  trigger: ReactNode;
  onDeleted?: () => void;
}) {
  const [open, setOpen] = useState(false);
  const remove = useDeleteDocument();

  const confirm = () =>
    remove.mutate(document.doc_id, {
      onSuccess: () => {
        toast.success(`Deleted ${document.filename}`);
        setOpen(false);
        onDeleted?.();
      },
      onError: (error) => toast.error(describeError(error).title),
    });

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent>
        <DialogTitle className="text-lg font-semibold">Delete this document?</DialogTitle>
        <DialogDescription className="mt-2 text-sm text-fg-muted">
          <span className="font-medium text-fg">{document.filename}</span> and its {document.chunk_count} indexed passages will be removed.
          This cannot be undone.
        </DialogDescription>
        <div className="mt-6 flex justify-end gap-2">
          <Button variant="ghost" onClick={() => setOpen(false)}>
            Cancel
          </Button>
          <Button variant="danger" onClick={confirm} disabled={remove.isPending}>
            <Trash2 /> {remove.isPending ? "Deleting…" : "Delete"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
