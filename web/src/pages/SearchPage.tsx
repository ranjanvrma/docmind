import { useMutation } from "@tanstack/react-query";
import { Loader2, Search as SearchIcon, Sparkles } from "lucide-react";
import { motion } from "motion/react";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router";

import { stagger } from "@/components/animations/motion";
import { PageHeader } from "@/components/layout/AppShell";
import { DocumentFilter } from "@/components/search/DocumentFilter";
import { SearchResultCard, SearchResultSkeleton } from "@/components/search/SearchResultCard";
import { Button } from "@/components/ui/button";
import { DocumentIllustration, EmptyState, ErrorState } from "@/components/ui/feedback";
import { Kbd, Segmented } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { emit } from "@/lib/events";
import { useDocuments } from "@/lib/queries";
import { cn } from "@/lib/utils";

const EXAMPLES = ["What are the main findings?", "What are the eligibility requirements?", "Which risks are mentioned?"];
const isMac = typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform);

export function SearchPage() {
  const [params, setParams] = useSearchParams();
  const [query, setQuery] = useState(params.get("q") ?? "");
  const [topK, setTopK] = useState(5);
  const [docIds, setDocIds] = useState<string[]>(() => (params.get("doc") ? [params.get("doc")!] : []));
  const [focused, setFocused] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const documents = useDocuments();
  const indexed = (documents.data ?? []).filter((d) => d.status === "processed").length;

  const search = useMutation({
    mutationFn: (q: string) => api.search(q, topK, docIds),
    onSuccess: () => emit("scene-pulse"),
  });

  // Ctrl/⌘+K or "/" focuses the search box.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const typing = e.target instanceof HTMLElement && ["INPUT", "TEXTAREA"].includes(e.target.tagName);
      if ((e.key === "k" && (e.metaKey || e.ctrlKey)) || (e.key === "/" && !typing)) {
        e.preventDefault();
        inputRef.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // Run a search that arrives via the URL (?q=...).
  useEffect(() => {
    const q = params.get("q");
    if (q) search.mutate(q);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const submit = (event?: FormEvent, text = query) => {
    event?.preventDefault();
    const q = text.trim();
    if (!q) return;
    setQuery(q);
    setParams((p) => {
      p.set("q", q);
      return p;
    }, { replace: true });
    search.mutate(q);
  };

  const results = search.data?.results ?? [];

  return (
    <>
      <PageHeader eyebrow="Semantic retrieval" title="Search" description="Find passages by meaning, not just matching words." />

      <form onSubmit={submit} role="search" className="relative">
        <div
          className={cn(
            "glass-strong relative flex items-center gap-3 rounded-2xl px-4 transition-shadow duration-300 sm:px-5",
            focused && "shadow-[var(--shadow-glass),0_0_0_1px_var(--accent-glow),0_0_60px_-15px_var(--accent-glow)]",
          )}
        >
          {search.isPending ? <Loader2 className="size-5 shrink-0 animate-spin text-accent" /> : <SearchIcon className="size-5 shrink-0 text-fg-faint" />}
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onFocus={() => setFocused(true)}
            onBlur={() => setFocused(false)}
            placeholder="Search across your documents..."
            aria-label="Search query"
            maxLength={2000}
            className="h-16 min-w-0 flex-1 bg-transparent text-[16px] text-fg placeholder:text-fg-faint focus:outline-none sm:text-[17px]"
          />
          <span className="hidden items-center gap-1 sm:flex" aria-hidden>
            <Kbd>{isMac ? "⌘" : "Ctrl"}</Kbd>
            <Kbd>K</Kbd>
          </span>
          <Button type="submit" variant="primary" size="sm" disabled={!query.trim() || search.isPending}>
            Search
          </Button>
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <DocumentFilter value={docIds} onChange={setDocIds} />
          <Segmented
            label="Number of results"
            value={topK}
            onChange={setTopK}
            options={[3, 5, 10].map((k) => ({ value: k, label: `Top ${k}` }))}
          />
        </div>
      </form>

      <div className="mt-10">
        {documents.data && indexed === 0 ? (
          <EmptyState
            icon={<DocumentIllustration />}
            title="Nothing to search yet"
            description="Upload and index a PDF first. Search works without an LLM."
            action={
              <Button variant="primary" asChild>
                <Link to="/documents">Go to documents</Link>
              </Button>
            }
          />
        ) : search.isPending ? (
          <div className="space-y-3" aria-busy aria-label="Searching">
            {Array.from({ length: Math.min(topK, 4) }, (_, i) => (
              <SearchResultSkeleton key={i} />
            ))}
          </div>
        ) : search.error ? (
          <ErrorState error={search.error} onRetry={() => submit()} />
        ) : search.data ? (
          results.length === 0 ? (
            <p className="glass rounded-2xl p-8 text-center text-sm text-fg-muted">No passages found in the selected documents.</p>
          ) : (
            <>
              <p className="mb-4 text-sm text-fg-muted" aria-live="polite">
                {results.length} passages, ranked by similarity to “{search.data.query}”
              </p>
              <motion.ol variants={stagger(0.07)} initial="hidden" animate="show" className="space-y-3">
                {results.map((hit) => (
                  <SearchResultCard key={hit.chunk_id} hit={hit} />
                ))}
              </motion.ol>
            </>
          )
        ) : (
          <div className="flex flex-col items-center py-10 text-center">
            <Sparkles className="mb-4 size-6 text-accent" />
            <p className="text-sm text-fg-muted">Try a question in your own words:</p>
            <div className="mt-4 flex flex-wrap justify-center gap-2">
              {EXAMPLES.map((example) => (
                <button
                  key={example}
                  type="button"
                  onClick={() => submit(undefined, example)}
                  className="glass rounded-full px-3.5 py-1.5 text-[13px] text-fg-muted transition-colors hover:border-line-strong hover:text-fg"
                >
                  {example}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </>
  );
}
