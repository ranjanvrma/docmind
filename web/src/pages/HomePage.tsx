import { ArrowRight } from "lucide-react";
import { Link } from "react-router";

import { DocumentGrid, DocumentGridSkeleton } from "@/components/documents/DocumentGrid";
import { Hero } from "@/components/hero/Hero";
import { HowItWorks } from "@/components/hero/HowItWorks";
import { ErrorState } from "@/components/ui/feedback";
import { UploadZone } from "@/components/upload/UploadZone";
import { useDocuments } from "@/lib/queries";

function SectionTitle({ title, action }: { title: string; action?: React.ReactNode }) {
  return (
    <div className="mb-4 flex items-end justify-between gap-4">
      <h2 className="text-lg font-semibold tracking-tight">{title}</h2>
      {action}
    </div>
  );
}

export function HomePage() {
  const documents = useDocuments();
  const recent = [...(documents.data ?? [])].sort((a, b) => b.uploaded_at.localeCompare(a.uploaded_at)).slice(0, 3);

  const focusUpload = () => {
    const el = document.getElementById("upload");
    el?.scrollIntoView({ behavior: "smooth", block: "center" });
    el?.querySelector<HTMLButtonElement>("button")?.focus({ preventScroll: true });
  };

  return (
    <div className="space-y-16">
      <Hero onUpload={focusUpload} />

      <UploadZone id="upload" />

      {documents.isPending ? (
        <section>
          <SectionTitle title="Recent documents" />
          <DocumentGridSkeleton />
        </section>
      ) : documents.error ? (
        <ErrorState error={documents.error} onRetry={() => documents.refetch()} />
      ) : recent.length > 0 ? (
        <section aria-labelledby="recent-heading">
          <SectionTitle
            title="Recent documents"
            action={
              <Link to="/documents" className="inline-flex items-center gap-1 text-sm text-fg-muted transition-colors hover:text-accent">
                View all <ArrowRight className="size-4" />
              </Link>
            }
          />
          <DocumentGrid documents={recent} />
        </section>
      ) : null}

      <section aria-label="How DocMind works">
        <SectionTitle
          title="How it works"
          action={
            <Link to="/about" className="inline-flex items-center gap-1 text-sm text-fg-muted transition-colors hover:text-accent">
              Architecture <ArrowRight className="size-4" />
            </Link>
          }
        />
        <HowItWorks />
      </section>
    </div>
  );
}
