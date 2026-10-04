import { Binary, BrainCircuit, Database, FileSearch, Quote, ShieldCheck } from "lucide-react";
import { motion } from "motion/react";

import { fadeUp, stagger } from "@/components/animations/motion";
import { GlowCard } from "@/components/effects/GlowCard";
import { HowItWorks } from "@/components/hero/HowItWorks";
import { PageHeader } from "@/components/layout/AppShell";
import { useHealth } from "@/lib/queries";

const COMPONENTS = [
  { icon: Binary, title: "Embeddings", body: "sentence-transformers all-MiniLM-L6-v2: a 6-layer transformer producing 384-dimensional vectors, L2-normalised. Used as-is, without fine-tuning." },
  { icon: Database, title: "Vector index", body: "FAISS IndexFlatIP wrapped in IndexIDMap2: exact search where inner product equals cosine similarity. Metadata is persisted alongside and checked for consistency on load." },
  { icon: FileSearch, title: "Semantic retrieval", body: "The query is embedded with the same model; the top-k most similar passages are returned with document and page." },
  { icon: BrainCircuit, title: "LLM", body: "A provider-agnostic client (Anthropic or OpenAI-compatible). The prompt treats document text as untrusted and requires citations." },
  { icon: Quote, title: "Citations", body: "Every [n] in an answer is checked against the passages actually sent to the model. Numbers that were never provided are flagged, not shown as sources." },
  { icon: ShieldCheck, title: "Safety", body: "Optional API token, upload and page limits, sanitised source text, and an interface that renders documents and answers as text, never HTML." },
];

const NOT_CLAIMED = [
  "Answers are grounded by instruction and citation checks, not guaranteed to be correct.",
  "Retrieval quality has only been measured on a small demo dataset.",
  "Scanned PDFs need OCR, which is not included.",
  "Designed as a single-instance application, not a multi-tenant service.",
];

export function AboutPage() {
  const { data } = useHealth();
  return (
    <motion.div variants={stagger(0.08)} initial="hidden" animate="show" className="space-y-14">
      <motion.div variants={fadeUp}>
        <PageHeader
          eyebrow="Architecture"
          title="How DocMind works"
          description="DocMind is a retrieval-augmented generation (RAG) application: it retrieves the passages most similar in meaning to your question, then asks a language model to answer only from them."
        />
        <HowItWorks />
      </motion.div>

      <motion.section variants={fadeUp} aria-labelledby="components-heading">
        <h2 id="components-heading" className="mb-4 text-lg font-semibold tracking-tight">
          Components
        </h2>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {COMPONENTS.map(({ icon: Icon, title, body }) => (
            <GlowCard key={title} className="p-5">
              <Icon className="size-5 text-accent" />
              <h3 className="mt-3 text-sm font-semibold">{title}</h3>
              <p className="mt-1.5 text-[13.5px] leading-relaxed text-fg-muted">{body}</p>
            </GlowCard>
          ))}
        </div>
      </motion.section>

      <motion.section variants={fadeUp} className="grid grid-cols-1 gap-5 md:grid-cols-2 [&>*]:min-w-0">
        <div className="glass rounded-2xl p-6">
          <h2 className="text-[15px] font-semibold">What DocMind does not claim</h2>
          <ul className="mt-4 space-y-2.5 text-sm text-fg-muted">
            {NOT_CLAIMED.map((item) => (
              <li key={item} className="flex gap-2.5">
                <span className="mt-2 size-1 shrink-0 rounded-full bg-fg-faint" />
                {item}
              </li>
            ))}
          </ul>
        </div>
        <div className="glass rounded-2xl p-6">
          <h2 className="text-[15px] font-semibold">This instance</h2>
          <dl className="mt-4 space-y-2.5 text-sm">
            {[
              ["Version", data?.version ?? "–"],
              ["Embedding model", data?.embedding_model ?? "–"],
              ["LLM", data ? `${data.llm_provider} / ${data.llm_model}${data.llm_configured ? "" : " (not configured)"}` : "–"],
              ["Documents", data?.documents ?? "–"],
              ["Indexed passages", data?.indexed_chunks ?? "–"],
            ].map(([k, v]) => (
              <div key={String(k)} className="flex justify-between gap-4 border-b border-line pb-2.5 last:border-0">
                <dt className="shrink-0 text-fg-muted">{k}</dt>
                <dd className="min-w-0 truncate text-right font-mono text-[12.5px]" title={String(v)}>{v}</dd>
              </div>
            ))}
          </dl>
        </div>
      </motion.section>
    </motion.div>
  );
}
