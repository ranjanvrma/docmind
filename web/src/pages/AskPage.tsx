import { MessageSquareText, Trash2, Unplug } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router";

import { PageHeader } from "@/components/layout/AppShell";
import { AskComposer } from "@/components/qa/AskComposer";
import { useChat } from "@/components/qa/ChatProvider";
import { ChatTurnView } from "@/components/qa/ChatTurnView";
import { Button } from "@/components/ui/button";
import { DocumentIllustration, EmptyState } from "@/components/ui/feedback";
import { useDocuments, useHealth } from "@/lib/queries";

const STARTERS = ["Summarise the key points.", "What does the document say about costs?", "What are the main recommendations?"];

export function AskPage() {
  const [params] = useSearchParams();
  const { turns, ask, clear } = useChat();
  const health = useHealth();
  const documents = useDocuments();
  const [docIds, setDocIds] = useState<string[]>(() => (params.get("doc") ? [params.get("doc")!] : []));
  const [topK, setTopK] = useState(5);
  const endRef = useRef<HTMLDivElement>(null);

  const llmReady = health.data?.llm_configured ?? false;
  const indexed = (documents.data ?? []).filter((d) => d.status === "processed").length;
  const busy = turns.some((t) => t.status === "pending");

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns.length, turns[turns.length - 1]?.status]);

  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader
        eyebrow="Retrieval-augmented generation"
        title="Ask"
        description="Answers are generated only from passages retrieved from your documents, with citations you can inspect."
        actions={
          turns.length > 0 && (
            <Button variant="ghost" size="sm" onClick={clear}>
              <Trash2 /> Clear
            </Button>
          )
        }
      />

      {health.data && !llmReady && (
        <div role="status" className="glass mb-6 flex items-start gap-3 rounded-2xl border-warning/25 p-4">
          <Unplug className="mt-0.5 size-4.5 shrink-0 text-warning" />
          <div className="text-sm">
            <p className="font-medium">AI question answering is currently unavailable.</p>
            <p className="mt-1 text-fg-muted">
              The server has no LLM configured. An administrator can set <code className="font-mono text-xs">LLM_API_KEY</code> in{" "}
              <code className="font-mono text-xs">.env</code> and restart the API. Semantic{" "}
              <Link to="/search" className="text-accent hover:underline">
                search
              </Link>{" "}
              still works.
            </p>
          </div>
        </div>
      )}

      {documents.data && indexed === 0 ? (
        <EmptyState
          icon={<DocumentIllustration />}
          title="No documents to ask about"
          description="Upload a PDF to start searching and asking questions."
          action={
            <Button variant="primary" asChild>
              <Link to="/documents">Upload document</Link>
            </Button>
          }
        />
      ) : turns.length === 0 ? (
        <div className="flex flex-col items-center py-12 text-center">
          <div className="mb-4 flex size-12 items-center justify-center rounded-2xl border border-line bg-accent-soft text-accent">
            <MessageSquareText className="size-5" />
          </div>
          <p className="font-medium">Ask anything about your documents</p>
          <p className="mt-1 max-w-sm text-sm text-fg-muted">Each question is answered independently, from the top retrieved passages.</p>
          {llmReady && (
            <div className="mt-6 flex flex-wrap justify-center gap-2">
              {STARTERS.map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => ask(s, topK, docIds)}
                  className="glass rounded-full px-3.5 py-1.5 text-[13px] text-fg-muted transition-colors hover:border-line-strong hover:text-fg"
                >
                  {s}
                </button>
              ))}
            </div>
          )}
        </div>
      ) : (
        <ol className="space-y-8 pb-6" aria-label="Conversation" aria-live="polite">
          {turns.map((turn) => (
            <ChatTurnView key={turn.id} turn={turn} />
          ))}
        </ol>
      )}
      <div ref={endRef} />

      <div className="sticky bottom-4 z-20 mt-6">
        <AskComposer
          disabled={!llmReady || indexed === 0}
          busy={busy}
          onSubmit={(q) => ask(q, topK, docIds)}
          docIds={docIds}
          onDocIdsChange={setDocIds}
          topK={topK}
          onTopKChange={setTopK}
        />
      </div>
    </div>
  );
}
