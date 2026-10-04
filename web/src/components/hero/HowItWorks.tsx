import { Binary, BrainCircuit, Database, FileText, Layers, ShieldCheck } from "lucide-react";
import { motion } from "motion/react";
import { Fragment } from "react";

import { fadeUp, stagger } from "@/components/animations/motion";

const STEPS = [
  { icon: FileText, title: "Document", detail: "PyMuPDF extracts text page by page; it is cleaned and split into ~600-character chunks." },
  { icon: Binary, title: "Embedding", detail: "all-MiniLM-L6-v2 maps each chunk to a 384-dimensional unit vector." },
  { icon: Database, title: "Vector search", detail: "FAISS IndexFlatIP: exact inner product, which equals cosine similarity here." },
  { icon: Layers, title: "Retrieved context", detail: "The top-k passages, numbered as [Source n] with document and page." },
  { icon: BrainCircuit, title: "LLM", detail: "Instructed to use only those sources, cite them, or say it could not find the answer." },
  { icon: ShieldCheck, title: "Grounded answer", detail: "Citation numbers are checked against the sources actually sent." },
] as const;

/** The RAG pipeline as a connected strip, with a light beam travelling along each link. */
export function HowItWorks({ compact = false }: { compact?: boolean }) {
  return (
    <motion.ol
      variants={stagger(0.08)}
      initial="hidden"
      whileInView="show"
      viewport={{ once: true, margin: "-80px" }}
      className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-[repeat(5,minmax(0,1fr)_1.75rem)_minmax(0,1fr)] lg:items-stretch lg:gap-0"
    >
      {STEPS.map(({ icon: Icon, title, detail }, i) => (
        <Fragment key={title}>
          <motion.li variants={fadeUp} className="glass relative flex min-w-0 gap-3 rounded-2xl p-4 lg:flex-col lg:gap-2.5">
            <div className="flex size-9 shrink-0 items-center justify-center rounded-xl border border-line bg-surface-2 text-accent">
              <Icon className="size-4.5" />
            </div>
            <div>
              <p className="flex items-center gap-2 text-sm font-semibold">
                <span className="font-mono text-[10.5px] text-fg-faint">{String(i + 1).padStart(2, "0")}</span>
                {title}
              </p>
              {!compact && <p className="mt-1 text-xs leading-relaxed text-fg-muted">{detail}</p>}
            </div>
          </motion.li>
          {i < STEPS.length - 1 && (
            <li aria-hidden className="relative hidden self-center lg:block">
              <div className="h-px w-full bg-line-strong" />
              <div className="absolute inset-0 overflow-hidden">
                <div
                  className="absolute top-1/2 h-px w-full -translate-y-1/2 animate-beam bg-gradient-to-r from-transparent via-accent to-transparent"
                  style={{ animationDelay: `${i * 0.35}s` }}
                />
              </div>
            </li>
          )}
        </Fragment>
      ))}
    </motion.ol>
  );
}
