import { ArrowUp } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";

import { DocumentFilter } from "@/components/search/DocumentFilter";
import { Kbd, Segmented } from "@/components/ui/primitives";
import { cn } from "@/lib/utils";

/** Question input: Enter sends, Shift+Enter adds a line. */
export function AskComposer({
  disabled,
  busy,
  onSubmit,
  docIds,
  onDocIdsChange,
  topK,
  onTopKChange,
}: {
  disabled: boolean;
  busy: boolean;
  onSubmit: (question: string) => void;
  docIds: string[];
  onDocIdsChange: (ids: string[]) => void;
  topK: number;
  onTopKChange: (k: number) => void;
}) {
  const [value, setValue] = useState("");
  const ref = useRef<HTMLTextAreaElement>(null);

  // Auto-grow up to ~8 lines.
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, [value]);

  const submit = (event?: FormEvent) => {
    event?.preventDefault();
    const question = value.trim();
    if (!question || disabled || busy) return;
    onSubmit(question);
    setValue("");
  };

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      submit();
    }
  };

  return (
    <form
      onSubmit={submit}
      className={cn(
        "glass-strong rounded-2xl p-2 transition-shadow focus-within:shadow-[var(--shadow-glass),0_0_0_1px_var(--accent-glow),0_0_40px_-12px_var(--accent-glow)]",
        disabled && "opacity-60",
      )}
    >
      <label htmlFor="ask-input" className="sr-only">
        Ask a question about your documents
      </label>
      <textarea
        id="ask-input"
        ref={ref}
        rows={1}
        value={value}
        disabled={disabled}
        maxLength={2000}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={onKeyDown}
        placeholder={disabled ? "Question answering is unavailable" : "Ask a question about your documents…"}
        className="block max-h-[200px] w-full resize-none bg-transparent px-3 py-2.5 text-[15px] text-fg placeholder:text-fg-faint focus:outline-none disabled:cursor-not-allowed"
      />
      <div className="flex flex-wrap items-center justify-between gap-2 px-1 pb-0.5">
        <div className="flex flex-wrap items-center gap-2">
          <DocumentFilter value={docIds} onChange={onDocIdsChange} />
          <Segmented
            label="Number of passages to retrieve"
            value={topK}
            onChange={onTopKChange}
            options={[3, 5, 8].map((k) => ({ value: k, label: `${k} passages` }))}
          />
        </div>
        <div className="flex items-center gap-2">
          <span className="hidden items-center gap-1 text-[11px] text-fg-faint sm:flex">
            <Kbd>Enter</Kbd> send · <Kbd>Shift</Kbd>+<Kbd>Enter</Kbd> new line
          </span>
          <button
            type="submit"
            disabled={disabled || busy || !value.trim()}
            aria-label="Send question"
            className="inline-flex size-9 items-center justify-center rounded-xl bg-accent text-accent-fg shadow-[0_0_24px_-6px_var(--accent-glow)] transition-[transform,opacity] hover:bg-accent-strong active:scale-95 disabled:opacity-35"
          >
            <ArrowUp className="size-4.5" />
          </button>
        </div>
      </div>
    </form>
  );
}
