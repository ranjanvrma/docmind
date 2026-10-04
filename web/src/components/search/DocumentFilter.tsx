import { Check, Filter } from "lucide-react";

import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/overlays";
import { useDocuments } from "@/lib/queries";
import { cn } from "@/lib/utils";

/** Restrict retrieval to selected (processed) documents. Empty selection = all documents. */
export function DocumentFilter({ value, onChange }: { value: string[]; onChange: (ids: string[]) => void }) {
  const { data } = useDocuments();
  const processed = (data ?? []).filter((d) => d.status === "processed");
  const label = value.length === 0 ? "All documents" : value.length === 1 ? (processed.find((d) => d.doc_id === value[0])?.filename ?? "1 document") : `${value.length} documents`;

  const toggle = (id: string) => onChange(value.includes(id) ? value.filter((v) => v !== id) : [...value, id]);

  return (
    <Popover>
      <PopoverTrigger
        className={cn(
          "inline-flex h-8 max-w-[16rem] items-center gap-2 rounded-xl border px-3 text-[12.5px] transition-colors",
          value.length ? "border-accent/40 bg-accent-soft text-accent" : "border-line bg-surface text-fg-muted hover:text-fg",
        )}
      >
        <Filter className="size-3.5 shrink-0" />
        <span className="truncate">{label}</span>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-72 p-2">
        <p className="px-2 pb-2 pt-1 text-xs text-fg-faint">Search within</p>
        {processed.length === 0 && <p className="px-2 py-3 text-sm text-fg-muted">No indexed documents yet.</p>}
        <ul className="max-h-64 overflow-y-auto">
          {processed.map((doc) => {
            const checked = value.includes(doc.doc_id);
            return (
              <li key={doc.doc_id}>
                <button
                  type="button"
                  role="checkbox"
                  aria-checked={checked}
                  onClick={() => toggle(doc.doc_id)}
                  className="flex w-full items-center gap-2.5 rounded-lg px-2 py-2 text-left text-sm hover:bg-surface-2"
                >
                  <span
                    className={cn(
                      "flex size-4 shrink-0 items-center justify-center rounded border",
                      checked ? "border-accent bg-accent text-accent-fg" : "border-line-strong",
                    )}
                  >
                    {checked && <Check className="size-3" />}
                  </span>
                  <span className="truncate">{doc.filename}</span>
                </button>
              </li>
            );
          })}
        </ul>
        {value.length > 0 && (
          <button type="button" onClick={() => onChange([])} className="mt-1 w-full rounded-lg px-2 py-2 text-left text-xs text-fg-muted hover:bg-surface-2">
            Clear selection
          </button>
        )}
      </PopoverContent>
    </Popover>
  );
}
