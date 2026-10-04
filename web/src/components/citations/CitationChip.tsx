import { ArrowUpRight, FileText } from "lucide-react";
import { useRef, useState } from "react";
import { Link } from "react-router";

import { Popover, PopoverContent, PopoverTrigger, Tooltip } from "@/components/ui/overlays";
import type { Source } from "@/lib/types";

const PREVIEW_CHARS = 320;

/**
 * An interactive [n] citation. Hover or focus shows the source (document,
 * page, passage); click pins it open (touch-friendly). A number that does not
 * match a source the model actually received is rendered as an invalid marker,
 * never linked to anything.
 */
export function CitationChip({ number, source, onReveal }: { number: number; source?: Source; onReveal?: (n: number) => void }) {
  const [open, setOpen] = useState(false);
  const [pinned, setPinned] = useState(false);
  const closeTimer = useRef<number | undefined>(undefined);

  if (!source) {
    return (
      <Tooltip content="The model cited a source number that was not provided. This citation is not real.">
        <span
          tabIndex={0}
          className="mx-0.5 inline-flex h-[1.15rem] min-w-[1.15rem] cursor-help items-center justify-center rounded-md border border-dashed border-danger/60 px-1 align-[0.12em] font-mono text-[10.5px] text-danger"
        >
          {number}?
        </span>
      </Tooltip>
    );
  }

  const show = () => {
    window.clearTimeout(closeTimer.current);
    setOpen(true);
  };
  const hide = () => {
    if (pinned) return;
    closeTimer.current = window.setTimeout(() => setOpen(false), 120);
  };
  const preview = source.text.length > PREVIEW_CHARS ? `${source.text.slice(0, PREVIEW_CHARS).trimEnd()}…` : source.text;

  return (
    <Popover
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        setPinned(next);
      }}
    >
      <PopoverTrigger asChild>
        <button
          type="button"
          aria-label={`Source ${number}: ${source.doc_name}, page ${source.page_number}`}
          onPointerEnter={show}
          onPointerLeave={hide}
          onFocus={show}
          onBlur={hide}
          onClick={(event) => {
            // First click on a hover-opened chip pins it (instead of Radix toggling it closed).
            if (!pinned) {
              event.preventDefault();
              setPinned(true);
              setOpen(true);
            }
          }}
          className="mx-0.5 inline-flex h-[1.15rem] min-w-[1.15rem] items-center justify-center rounded-md border border-accent/35 bg-accent-soft px-1 align-[0.12em] font-mono text-[10.5px] font-medium text-accent transition-[background-color,box-shadow] hover:bg-accent/20 hover:shadow-[0_0_14px_-2px_var(--accent-glow)] data-[state=open]:bg-accent/20"
          data-state={open ? "open" : "closed"}
        >
          {number}
        </button>
      </PopoverTrigger>
      <PopoverContent
        side="top"
        onPointerEnter={show}
        onPointerLeave={hide}
        onOpenAutoFocus={(e) => e.preventDefault()}
        className="w-[min(22rem,calc(100vw-2rem))]"
      >
        <div className="flex items-center justify-between gap-3">
          <span className="font-mono text-xs font-medium text-accent">Source {number}</span>
          <span className="rounded-md border border-line px-1.5 py-0.5 font-mono text-[11px] text-fg-muted">p. {source.page_number}</span>
        </div>
        <p className="mt-2 flex items-center gap-1.5 truncate text-sm font-medium">
          <FileText className="size-3.5 shrink-0 text-fg-faint" />
          <span className="truncate">{source.doc_name}</span>
        </p>
        <blockquote className="mt-3 border-l-2 border-accent/40 pl-3 text-[13px] leading-relaxed text-fg-muted">“{preview}”</blockquote>
        <div className="mt-3 flex items-center justify-between">
          {onReveal ? (
            <button type="button" onClick={() => (onReveal(number), setOpen(false))} className="text-xs text-fg-muted hover:text-fg">
              Show in sources
            </button>
          ) : (
            <span />
          )}
          <Link
            to={`/documents/${source.doc_id}?page=${source.page_number}#page-${source.page_number}`}
            className="inline-flex items-center gap-1 text-xs font-medium text-accent hover:underline"
          >
            Open in document <ArrowUpRight className="size-3.5" />
          </Link>
        </div>
      </PopoverContent>
    </Popover>
  );
}
