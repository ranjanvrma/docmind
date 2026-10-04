import { AnimatePresence, motion } from "motion/react";

import { stagger } from "@/components/animations/motion";
import type { DocumentInfo } from "@/lib/types";
import { DocumentCard, DocumentCardSkeleton } from "./DocumentCard";

export function DocumentGrid({ documents }: { documents: DocumentInfo[] }) {
  return (
    <motion.ul
      variants={stagger(0.05)}
      initial="hidden"
      animate="show"
      className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3"
      aria-label="Documents"
    >
      <AnimatePresence initial={false}>
        {documents.map((doc) => (
          <DocumentCard key={doc.doc_id} document={doc} />
        ))}
      </AnimatePresence>
    </motion.ul>
  );
}

export function DocumentGridSkeleton({ count = 3 }: { count?: number }) {
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3" aria-busy aria-label="Loading documents">
      {Array.from({ length: count }, (_, i) => (
        <DocumentCardSkeleton key={i} />
      ))}
    </div>
  );
}
