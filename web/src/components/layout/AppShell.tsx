import { AnimatePresence, motion } from "motion/react";
import { useEffect } from "react";
import { Link, Outlet, useLocation } from "react-router";

import { duration, ease } from "@/components/animations/motion";
import { AppBackground } from "@/components/effects/Background";
import { NavBar } from "@/components/navigation/NavBar";
import { AuthDialog } from "./AuthDialog";

export function AppShell() {
  const location = useLocation();

  // New page: start at the top (unless the URL targets an anchor).
  useEffect(() => {
    if (!location.hash) window.scrollTo({ top: 0 });
  }, [location.pathname, location.hash]);

  return (
    <div className="relative flex min-h-dvh flex-col">
      <AppBackground />
      <a
        href="#main"
        className="sr-only z-50 rounded-lg bg-surface-solid px-3 py-2 focus:not-sr-only focus:fixed focus:left-4 focus:top-4"
      >
        Skip to content
      </a>
      <NavBar />
      <AnimatePresence mode="wait">
        <motion.main
          id="main"
          key={location.pathname}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0, transition: { duration: duration.normal, ease } }}
          exit={{ opacity: 0, transition: { duration: duration.fast } }}
          className="relative z-10 mx-auto w-full max-w-6xl flex-1 px-4 pb-16 pt-8 sm:px-6"
        >
          <Outlet />
        </motion.main>
      </AnimatePresence>
      <footer className="relative z-10 mx-auto flex w-full max-w-6xl flex-wrap items-center justify-between gap-2 px-4 pb-8 text-xs text-fg-faint sm:px-6">
        <span>DocMind · retrieval-augmented document intelligence</span>
        <Link to="/about" className="hover:text-fg-muted">
          How it works
        </Link>
      </footer>
      <AuthDialog />
    </div>
  );
}

/** Consistent page heading: small eyebrow, compact title, optional actions. */
export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  actions?: React.ReactNode;
}) {
  return (
    <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        {eyebrow && <p className="mb-2 text-xs font-medium uppercase tracking-[0.14em] text-accent">{eyebrow}</p>}
        <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">{title}</h1>
        {description && <p className="mt-2 max-w-2xl text-sm text-fg-muted">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}
