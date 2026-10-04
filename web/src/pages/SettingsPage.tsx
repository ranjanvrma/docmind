import { useMutation, useQueryClient } from "@tanstack/react-query";
import { BrainCircuit, Cpu, FlaskConical, Gauge, Loader2, Monitor, Moon, RefreshCw, RotateCcw, Shapes, Sun, Upload } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useEffect, useMemo, useState, type FormEvent, type ReactNode } from "react";
import { toast } from "sonner";

import { spring } from "@/components/animations/motion";
import { PageHeader } from "@/components/layout/AppShell";
import { usePreferences } from "@/components/layout/PreferencesProvider";
import { ApiKeyField } from "@/components/settings/ApiKeyField";
import { Chips, ChunkDiagram, Field, LabelEditor, NumberInput, SliderField, TextInput } from "@/components/settings/controls";
import { EvaluationLab } from "@/components/settings/EvaluationLab";
import { Button } from "@/components/ui/button";
import { ErrorState } from "@/components/ui/feedback";
import { Dialog, DialogContent, DialogDescription, DialogTitle, DialogTrigger } from "@/components/ui/overlays";
import { Badge, Input, Segmented, Skeleton } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { describeError } from "@/lib/errors";
import { pluralize } from "@/lib/format";
import { isTokenRemembered } from "@/lib/preferences";
import { keys, useDocuments, useHealth, useServerSettings } from "@/lib/queries";
import type { EditableSettings } from "@/lib/types";
import { cn } from "@/lib/utils";

const SECTIONS = [
  { id: "model", label: "Model", icon: BrainCircuit },
  { id: "retrieval", label: "Retrieval & indexing", icon: Cpu },
  { id: "lab", label: "Evaluation lab", icon: FlaskConical },
  { id: "classification", label: "Classification", icon: Shapes },
  { id: "limits", label: "Upload limits", icon: Upload },
  { id: "preferences", label: "This browser", icon: Monitor },
] as const;

const ANTHROPIC_MODELS = ["claude-opus-5", "claude-sonnet-5", "claude-haiku-4-5"];
const BASE_URL_PRESETS = [
  { label: "OpenAI", value: "https://api.openai.com/v1" },
  { label: "Groq", value: "https://api.groq.com/openai/v1" },
  { label: "Ollama (local)", value: "http://localhost:11434/v1" },
];
const INDEXING_KEYS: (keyof EditableSettings)[] = ["chunk_size", "chunk_overlap", "min_chars_per_page"];

function Section({ id, title, description, icon: Icon, children, aside }: { id: string; title: string; description: string; icon: typeof Cpu; children: ReactNode; aside?: ReactNode }) {
  return (
    <section id={id} aria-labelledby={`${id}-title`} className="glass scroll-mt-28 rounded-2xl p-5 sm:p-6">
      <div className="mb-5 flex flex-wrap items-start justify-between gap-3 border-b border-line pb-4">
        <div className="flex gap-3">
          <div className="flex size-9 shrink-0 items-center justify-center rounded-xl border border-line bg-surface-2 text-accent">
            <Icon className="size-4.5" />
          </div>
          <div>
            <h2 id={`${id}-title`} className="text-[15px] font-semibold">
              {title}
            </h2>
            <p className="mt-0.5 text-sm text-fg-muted">{description}</p>
          </div>
        </div>
        {aside}
      </div>
      <div className="divide-y divide-line">{children}</div>
    </section>
  );
}

function equal(a: unknown, b: unknown) {
  return JSON.stringify(a) === JSON.stringify(b);
}

export function SettingsPage() {
  const client = useQueryClient();
  const settings = useServerSettings();
  const health = useHealth();
  const documents = useDocuments();
  const [draft, setDraft] = useState<EditableSettings | null>(null);
  const [needsReindex, setNeedsReindex] = useState(false);

  const saved = settings.data?.values;
  useEffect(() => {
    if (saved && !draft) setDraft(saved);
  }, [saved, draft]);

  const dirtyKeys = useMemo(
    () => (saved && draft ? (Object.keys(draft) as (keyof EditableSettings)[]).filter((k) => !equal(draft[k], saved[k])) : []),
    [saved, draft],
  );
  const set = <K extends keyof EditableSettings>(key: K, value: EditableSettings[K]) => setDraft((d) => (d ? { ...d, [key]: value } : d));
  const isDirty = (k: keyof EditableSettings) => dirtyKeys.includes(k);

  const save = useMutation({
    mutationFn: () => api.updateSettings(Object.fromEntries(dirtyKeys.map((k) => [k, draft![k]]))),
    onSuccess: (view) => {
      const changedIndexing = dirtyKeys.some((k) => INDEXING_KEYS.includes(k));
      client.setQueryData(keys.settings, view);
      client.invalidateQueries({ queryKey: keys.health });
      setDraft(view.values);
      toast.success(`Saved ${pluralize(dirtyKeys.length, "change")}`);
      if (changedIndexing && (documents.data ?? []).some((d) => d.status === "processed")) setNeedsReindex(true);
    },
    onError: (e) => toast.error(describeError(e).detail ?? describeError(e).title),
  });

  const reindex = useMutation({
    mutationFn: () => api.process(undefined, true),
    onSuccess: (res) => {
      setNeedsReindex(false);
      client.invalidateQueries();
      toast.success(`Re-indexed: ${res.indexed_chunks} chunks`);
    },
    onError: (e) => toast.error(describeError(e).title),
  });

  const reset = useMutation({
    mutationFn: api.resetSettings,
    onSuccess: (view) => {
      client.setQueryData(keys.settings, view);
      client.invalidateQueries({ queryKey: keys.health });
      setDraft(view.values);
      toast.success("Server settings reset to defaults");
    },
  });

  const processedCount = (documents.data ?? []).filter((d) => d.status === "processed").length;

  return (
    <div className="pb-24">
      <PageHeader
        eyebrow="Workspace"
        title="Settings"
        description="Tune how DocMind retrieves, generates and indexes. Changes are saved on the server, validated, and applied immediately, with no restart."
        actions={
          health.data && (
            <Badge tone={health.data.llm_configured ? "success" : "warning"}>
              {health.data.llm_configured ? "Q&A enabled" : "Search only"} · v{health.data.version}
            </Badge>
          )
        }
      />

      {settings.error ? (
        <ErrorState error={settings.error} onRetry={() => settings.refetch()} />
      ) : !draft || !settings.data ? (
        <div className="space-y-4">
          <Skeleton className="h-64 w-full rounded-2xl" />
          <Skeleton className="h-64 w-full rounded-2xl" />
        </div>
      ) : (
        <div className="grid gap-8 lg:grid-cols-[12rem_1fr]">
          <nav aria-label="Settings sections" className="hidden lg:block">
            <ul className="sticky top-28 space-y-1">
              {SECTIONS.map(({ id, label, icon: Icon }) => (
                <li key={id}>
                  <a href={`#${id}`} className="flex items-center gap-2.5 rounded-xl px-3 py-2 text-sm text-fg-muted transition-colors hover:bg-surface hover:text-fg">
                    <Icon className="size-4" /> {label}
                  </a>
                </li>
              ))}
            </ul>
          </nav>

          <div className="min-w-0 space-y-6">
            <AnimatePresence>
              {needsReindex && (
                <motion.div
                  initial={{ opacity: 0, y: -8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -8 }}
                  className="glass flex flex-wrap items-center justify-between gap-3 rounded-2xl border-accent/30 p-4"
                >
                  <p className="text-sm">
                    <span className="font-medium">Indexing settings changed.</span>{" "}
                    <span className="text-fg-muted">Re-index {pluralize(processedCount, "document")} to apply them to existing content.</span>
                  </p>
                  <Button variant="primary" size="sm" onClick={() => reindex.mutate()} disabled={reindex.isPending}>
                    {reindex.isPending ? <Loader2 className="animate-spin" /> : <RefreshCw />} Re-index now
                  </Button>
                </motion.div>
              )}
            </AnimatePresence>

            {/* ------------------------------------------------------------ model */}
            <Section id="model" icon={BrainCircuit} title="Model" description="The language model that writes grounded answers. Search works without one.">
              <Field label="Provider" modified={isDirty("llm_provider")}>
                <Segmented
                  label="LLM provider"
                  value={draft.llm_provider}
                  onChange={(v) => set("llm_provider", v)}
                  options={[
                    { value: "anthropic", label: "Anthropic" },
                    { value: "openai", label: "OpenAI-compatible" },
                  ]}
                />
              </Field>
              <Field label="Model" htmlFor="llm-model" modified={isDirty("llm_model")} hint="The exact model name your provider expects.">
                <TextInput id="llm-model" value={draft.llm_model} onChange={(v) => set("llm_model", v)} placeholder="model name" />
                {draft.llm_provider === "anthropic" && (
                  <Chips active={draft.llm_model} onPick={(v) => set("llm_model", v)} options={ANTHROPIC_MODELS.map((m) => ({ label: m, value: m }))} />
                )}
              </Field>
              {draft.llm_provider === "openai" && (
                <Field label="Base URL" htmlFor="llm-base" modified={isDirty("llm_base_url")} hint="Leave empty for OpenAI.">
                  <TextInput id="llm-base" value={draft.llm_base_url} onChange={(v) => set("llm_base_url", v)} placeholder="https://api.openai.com/v1" />
                  <Chips active={draft.llm_base_url} onPick={(v) => set("llm_base_url", v)} options={BASE_URL_PRESETS} />
                </Field>
              )}
              {draft.llm_provider === "anthropic" && (
                <Field label="Effort" modified={isDirty("llm_effort")} hint="Lower effort is faster and cheaper; usually enough for grounded Q&A. Use Default for models without effort support.">
                  <Segmented
                    label="Effort"
                    value={draft.llm_effort}
                    onChange={(v) => set("llm_effort", v)}
                    options={[{ value: "", label: "Default" }, ...["low", "medium", "high", "max"].map((v) => ({ value: v, label: v[0].toUpperCase() + v.slice(1) }))]}
                  />
                </Field>
              )}
              <Field label="Max answer tokens" htmlFor="llm-max" modified={isDirty("llm_max_tokens")} hint="Includes any reasoning tokens. Truncated answers are labelled.">
                <NumberInput id="llm-max" value={draft.llm_max_tokens} min={256} max={64000} step={256} onChange={(v) => set("llm_max_tokens", v)} suffix="tokens" />
              </Field>
              {draft.llm_provider === "openai" && (
                <Field label="Temperature" modified={isDirty("llm_temperature")} hint="0 = most deterministic. Some models only accept the default.">
                  <SliderField label="Temperature" value={draft.llm_temperature} min={0} max={1} step={0.1} onChange={(v) => set("llm_temperature", v)} format={(v) => v.toFixed(1)} />
                </Field>
              )}
              <Field label="Timeout" htmlFor="llm-timeout" modified={isDirty("llm_timeout_seconds")}>
                <NumberInput id="llm-timeout" value={draft.llm_timeout_seconds} min={5} max={600} step={5} onChange={(v) => set("llm_timeout_seconds", v)} suffix="seconds" />
              </Field>
              <Field label="API key" hint="Write-only. Overrides LLM_API_KEY from the server's .env while saved here.">
                <ApiKeyField status={settings.data.llm_api_key} disabledTest={dirtyKeys.some((k) => k.startsWith("llm_"))} />
              </Field>
            </Section>

            {/* -------------------------------------------------------- retrieval */}
            <Section id="retrieval" icon={Cpu} title="Retrieval & indexing" description="How documents are split, and how much context each answer sees.">
              <Field label="Passages per question" modified={isDirty("top_k")} hint="Default number of passages retrieved (top-k) for search and Q&A.">
                <SliderField label="Passages per question" value={draft.top_k} min={1} max={20} onChange={(v) => set("top_k", v)} format={(v) => `${v}`} />
              </Field>
              <Field label="Context budget" modified={isDirty("max_context_chars")} hint="Maximum retrieved text sent to the LLM per question.">
                <SliderField
                  label="Context budget"
                  value={draft.max_context_chars}
                  min={1000}
                  max={20000}
                  step={500}
                  onChange={(v) => set("max_context_chars", v)}
                  format={(v) => `≈${Math.round(v / 4).toLocaleString()} tok`}
                />
              </Field>
              <Field label="Chunk size" modified={isDirty("chunk_size")} hint="Characters per chunk. Smaller = more precise matches; larger = more context per match.">
                <SliderField
                  label="Chunk size"
                  value={draft.chunk_size}
                  min={200}
                  max={2000}
                  step={50}
                  onChange={(v) => {
                    set("chunk_size", v);
                    if (draft.chunk_overlap >= v) set("chunk_overlap", Math.floor(v / 4));
                  }}
                  format={(v) => `${v} chars`}
                />
              </Field>
              <Field label="Overlap" modified={isDirty("chunk_overlap")} hint="Text shared between consecutive chunks, so facts at a boundary stay intact.">
                <SliderField label="Chunk overlap" value={draft.chunk_overlap} min={0} max={Math.min(600, draft.chunk_size - 50)} step={10} onChange={(v) => set("chunk_overlap", v)} format={(v) => `${v} chars`} />
                <ChunkDiagram size={draft.chunk_size} overlap={draft.chunk_overlap} />
              </Field>
              <Field label="Empty-page threshold" htmlFor="min-chars" modified={isDirty("min_chars_per_page")} hint="Pages with less text are treated as empty (e.g. scans).">
                <NumberInput id="min-chars" value={draft.min_chars_per_page} min={0} max={1000} onChange={(v) => set("min_chars_per_page", v)} suffix="characters" />
              </Field>
              <Field label="Embedding model" hint="Changing it requires rebuilding the whole index, so it is set in the server environment.">
                <code className="font-mono text-[13px] text-fg-muted">{settings.data.read_only.embedding_model}</code>
              </Field>
            </Section>

            {/* ------------------------------------------------------------- lab */}
            <Section id="lab" icon={FlaskConical} title="Evaluation lab" description="Measure retrieval quality with your current settings, on a temporary index.">
              <div className="py-1">
                <EvaluationLab dirtyIndexing={dirtyKeys.some((k) => INDEXING_KEYS.includes(k))} />
              </div>
            </Section>

            {/* -------------------------------------------------- classification */}
            <Section id="classification" icon={Shapes} title="Classification" description="Categories for the zero-shot document classifier. New labels apply to documents processed from now on.">
              <Field label="Categories" modified={isDirty("classifier_labels")} hint="Press Enter to add. Clear, distinct names work best.">
                <LabelEditor value={draft.classifier_labels} onChange={(v) => set("classifier_labels", v)} />
              </Field>
            </Section>

            {/* ---------------------------------------------------------- limits */}
            <Section id="limits" icon={Gauge} title="Upload limits" description="Protect the server from oversized uploads.">
              <Field label="Per file" htmlFor="lim-file" modified={isDirty("max_upload_mb")}>
                <NumberInput id="lim-file" value={draft.max_upload_mb} min={1} max={500} onChange={(v) => set("max_upload_mb", v)} suffix="MB" />
              </Field>
              <Field label="Per upload request" htmlFor="lim-req" modified={isDirty("max_request_mb")} hint="Checked before the upload is read. Must be at least the per-file limit.">
                <NumberInput id="lim-req" value={draft.max_request_mb} min={1} max={2000} onChange={(v) => set("max_request_mb", v)} suffix="MB" />
              </Field>
              <Field label="Pages per document" htmlFor="lim-pages" modified={isDirty("max_pages")}>
                <NumberInput id="lim-pages" value={draft.max_pages} min={1} max={10000} onChange={(v) => set("max_pages", v)} suffix="pages" />
              </Field>
            </Section>

            <BrowserPreferences />

            <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-line p-4">
              <p className="text-sm text-fg-muted">
                {settings.data.overridden.length
                  ? `${pluralize(settings.data.overridden.length, "setting")} saved here override the server's .env.`
                  : "All server settings come from the server's .env."}
              </p>
              <ResetDialog disabled={!settings.data.overridden.length && settings.data.llm_api_key.source !== "settings"} onConfirm={() => reset.mutate()} />
            </div>
          </div>
        </div>
      )}

      {/* Floating save bar */}
      <AnimatePresence>
        {dirtyKeys.length > 0 && (
          <motion.div
            initial={{ y: 80, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: 80, opacity: 0 }}
            transition={spring}
            className="fixed inset-x-0 bottom-4 z-40 flex justify-center px-4"
          >
            <div role="status" className="nav-solid flex items-center gap-3 rounded-2xl py-2 pl-4 pr-2 text-sm">
              <span className="size-2 rounded-full bg-accent" />
              <span>{pluralize(dirtyKeys.length, "unsaved change")}</span>
              <Button variant="ghost" size="sm" onClick={() => setDraft(saved ?? null)}>
                Discard
              </Button>
              <Button variant="primary" size="sm" onClick={() => save.mutate()} disabled={save.isPending}>
                {save.isPending && <Loader2 className="animate-spin" />} Save changes
              </Button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function ResetDialog({ disabled, onConfirm }: { disabled: boolean; onConfirm: () => void }) {
  const [open, setOpen] = useState(false);
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm" disabled={disabled}>
          <RotateCcw /> Reset to defaults
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogTitle className="text-lg font-semibold">Reset server settings?</DialogTitle>
        <DialogDescription className="mt-2 text-sm text-fg-muted">
          All values saved here, including a saved API key, are removed and the server's .env values apply again. Documents are not affected.
        </DialogDescription>
        <div className="mt-6 flex justify-end gap-2">
          <Button variant="ghost" onClick={() => setOpen(false)}>
            Cancel
          </Button>
          <Button
            variant="danger"
            onClick={() => {
              onConfirm();
              setOpen(false);
            }}
          >
            Reset
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

/** Settings stored in this browser only: access token, theme, motion. */
function BrowserPreferences() {
  const { theme, setTheme, motion, setMotion, reducedMotion, hasToken, setToken } = usePreferences();
  const client = useQueryClient();
  const health = useHealth();
  const [tokenValue, setTokenValue] = useState("");
  const [remember, setRemember] = useState(isTokenRemembered);

  const saveToken = (event: FormEvent) => {
    event.preventDefault();
    setToken(tokenValue.trim() || null, remember);
    setTokenValue("");
    client.invalidateQueries();
    toast.success(tokenValue.trim() ? "Access token saved" : "Access token removed");
  };

  return (
    <Section id="preferences" icon={Monitor} title="This browser" description="Stored only in this browser.">
      <Field label="Theme">
        <Segmented
          label="Theme"
          value={theme}
          onChange={setTheme}
          options={[
            { value: "dark", label: <span className="inline-flex items-center gap-1.5"><Moon className="size-3.5" />Dark</span> },
            { value: "light", label: <span className="inline-flex items-center gap-1.5"><Sun className="size-3.5" />Light</span> },
            { value: "system", label: <span className="inline-flex items-center gap-1.5"><Monitor className="size-3.5" />System</span> },
          ]}
        />
      </Field>
      <Field label="Motion" hint={`Reduced motion turns off decorative animation and the 3D scene. Currently ${reducedMotion ? "reduced" : "full"}.`}>
        <Segmented
          label="Motion"
          value={motion}
          onChange={setMotion}
          options={[
            { value: "system", label: "System" },
            { value: "reduced", label: "Reduced" },
            { value: "full", label: "Full" },
          ]}
        />
      </Field>
      <Field
        label="Access token"
        hint={health.data?.auth_required ? "This server requires a token; it is sent as X-API-Key." : "This server does not require a token."}
      >
        <form onSubmit={saveToken} className="space-y-2.5">
          <div className="flex flex-col gap-2 sm:flex-row">
            <Input
              type="password"
              autoComplete="off"
              aria-label="Access token"
              placeholder={hasToken ? "Token stored. Enter a new one, or leave empty to remove" : "Access token"}
              value={tokenValue}
              onChange={(e) => setTokenValue(e.target.value)}
            />
            <Button type="submit" variant="glass">
              {tokenValue.trim() ? "Save" : hasToken ? "Remove" : "Save"}
            </Button>
          </div>
          <label className={cn("flex items-center gap-2 text-xs text-fg-muted")}>
            <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} className="accent-[var(--accent)]" />
            Remember on this device
          </label>
        </form>
      </Field>
    </Section>
  );
}
