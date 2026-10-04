import { Link } from "react-router";

import { Button } from "@/components/ui/button";
import { DocumentIllustration, EmptyState } from "@/components/ui/feedback";

export function NotFoundPage() {
  return (
    <EmptyState
      className="mt-10"
      icon={<DocumentIllustration />}
      title="Page not found"
      description="The page you are looking for does not exist."
      action={
        <Button variant="primary" asChild>
          <Link to="/">Back to home</Link>
        </Button>
      }
    />
  );
}
