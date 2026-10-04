/** Form controls for the Settings page. */
import { Plus, X } from "lucide-react";
import { useId, useState, type KeyboardEvent, type ReactNode } from "react";

import { Badge } from "@/components/ui/primitives";
import { cn } from "@/lib/utils";

export function Field({
  label,
  hint,
  modified,
  children,
  htmlFor,
}: {
  label: string;
  hint?: ReactNode;
  modified?: boolean;
  children: ReactNode;
  htmlFor?: string;
}) {
  return (
    <div className="grid grid-cols-1 gap-2 py-4 first:pt-0 last:pb-0 sm:grid-cols-[minmax(0,14rem)_minmax(0,1fr)] sm:gap-6">
      <div>
        <label htmlFor={htmlFor} className="flex items-center gap-2 text-sm font-medium">
          {label}
          {modified && <span className="size-1.5 rounded-full bg-accent" aria-label="unsaved change" />}
        </label>
        {hint && <p className="mt-1 text-xs leading-relaxed text-fg-faint">{hint}</p>}
      </div>
      <div className="min-w-0">{children}</div>
    </div>
  );
}

export function SliderField({
  value,
  min,
  max,
  step = 1,
  onChange,
  format = String,
  label,
}: {
  value: number;
  min: number;
  max: number;
  step?: number;
  onChange: (v: number) => void;
  format?: (v: number) => string;
  label: string;
}) {
  const pct = ((value - min) / (max - min)) * 100;
  return (
    <div className="flex items-center gap-4">
      <input
        type="range"
        aria-label={label}
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="h-1.5 w-full cursor-pointer appearance-none rounded-full bg-surface-2 accent-[var(--accent)] [&::-webkit-slider-thumb]:size-4 [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-accent [&::-webkit-slider-thumb]:shadow-[0_0_0_4px_var(--accent-soft)]"
        style={{ background: `linear-gradient(to right, var(--accent) ${pct}%, var(--surface-2) ${pct}%)` }}
      />
      <span className="w-24 shrink-0 text-right font-mono text-[13px] text-fg">{format(value)}</span>
    </div>
  );
}

export function NumberInput({
  value,
  onChange,
  min,
  max,
  step = 1,
  suffix,
  id,
}: {
  value: number;
  onChange: (v: number) => void;
  min?: number;
  max?: number;
  step?: number;
  suffix?: string;
  id?: string;
}) {
  return (
    <div className="flex items-center gap-2">
      <input
        id={id}
        type="number"
        inputMode="decimal"
        value={Number.isFinite(value) ? value : ""}
        min={min}
        max={max}
        step={step}
        onChange={(e) => onChange(e.target.value === "" ? Number.NaN : Number(e.target.value))}
        className="h-9 w-32 rounded-xl border border-line bg-surface px-3 font-mono text-sm text-fg focus:border-accent/50 focus:outline-none"
      />
      {suffix && <span className="text-xs text-fg-faint">{suffix}</span>}
    </div>
  );
}

export function TextInput({ id, value, onChange, placeholder }: { id?: string; value: string; onChange: (v: string) => void; placeholder?: string }) {
  return (
    <input
      id={id}
      value={value}
      placeholder={placeholder}
      spellCheck={false}
      autoComplete="off"
      onChange={(e) => onChange(e.target.value)}
      className="h-9 w-full rounded-xl border border-line bg-surface px-3 font-mono text-[13px] text-fg placeholder:text-fg-faint focus:border-accent/50 focus:outline-none"
    />
  );
}

export function Chips({ options, onPick, active }: { options: { label: string; value: string }[]; onPick: (v: string) => void; active?: string }) {
  return (
    <div className="mt-2 flex flex-wrap gap-1.5">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          onClick={() => onPick(o.value)}
          className={cn(
            "rounded-full border px-2.5 py-1 text-[11.5px] transition-colors",
            active === o.value ? "border-accent/40 bg-accent-soft text-accent" : "border-line text-fg-muted hover:border-line-strong hover:text-fg",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

/** Editable list of category labels (zero-shot classification). */
export function LabelEditor({ value, onChange }: { value: string[]; onChange: (labels: string[]) => void }) {
  const [draft, setDraft] = useState("");
  const inputId = useId();
  const add = () => {
    const label = draft.trim();
    if (label && !value.some((v) => v.toLowerCase() === label.toLowerCase())) onChange([...value, label]);
    setDraft("");
  };
  const onKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      e.preventDefault();
      add();
    } else if (e.key === "Backspace" && !draft && value.length) onChange(value.slice(0, -1));
  };
  return (
    <div className="flex flex-wrap items-center gap-1.5 rounded-xl border border-line bg-surface p-2">
      {value.map((label) => (
        <Badge key={label} tone="neutral" className="gap-1 py-1 pl-2.5 pr-1 text-[12px] text-fg">
          {label}
          <button type="button" onClick={() => onChange(value.filter((v) => v !== label))} aria-label={`Remove ${label}`} className="rounded-full p-0.5 hover:bg-surface-2">
            <X className="size-3" />
          </button>
        </Badge>
      ))}
      <label htmlFor={inputId} className="sr-only">
        Add a category
      </label>
      <input
        id={inputId}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={onKey}
        maxLength={40}
        placeholder="Add a category…"
        className="h-7 min-w-[8rem] flex-1 bg-transparent px-1 text-sm text-fg placeholder:text-fg-faint focus:outline-none"
      />
      <button type="button" onClick={add} disabled={!draft.trim()} aria-label="Add category" className="rounded-lg p-1 text-fg-muted hover:bg-surface-2 hover:text-fg disabled:opacity-30">
        <Plus className="size-4" />
      </button>
    </div>
  );
}

/**
 * Three consecutive chunks drawn to scale, so the effect of chunk size and
 * overlap is visible before re-indexing. Purely illustrative (characters).
 */
export function ChunkDiagram({ size, overlap }: { size: number; overlap: number }) {
  const stride = Math.max(1, size - overlap);
  const total = size + stride * 2;
  const pct = (v: number) => `${(v / total) * 100}%`;
  const perPage = Math.max(1, Math.ceil((2500 - overlap) / stride));
  return (
    <div className="mt-4 rounded-xl border border-line bg-bg-2/60 p-4" aria-hidden>
      <div className="relative h-[4.5rem]">
        {[0, 1, 2].map((i) => (
          <div
            key={i}
            className="absolute h-5 rounded-md border border-accent/40 bg-accent-soft transition-all duration-300"
            style={{ left: pct(i * stride), width: pct(size), top: `${i * 1.55}rem` }}
          >
            <span className="absolute left-2 top-0.5 font-mono text-[10px] text-accent">chunk {i + 1}</span>
          </div>
        ))}
        {overlap > 0 &&
          [1, 2].map((i) => (
            <div
              key={`o${i}`}
              className="absolute inset-y-0 border-x border-dashed border-accent-2/60 bg-accent-2-soft transition-all duration-300"
              style={{ left: pct(i * stride), width: pct(overlap) }}
            />
          ))}
      </div>
      <p className="mt-3 text-xs text-fg-faint">
        {size} characters per chunk, {overlap} shared with the next (violet). A typical 2,500-character page becomes about{" "}
        <span className="text-fg-muted">{perPage} chunks</span>.
      </p>
    </div>
  );
}
