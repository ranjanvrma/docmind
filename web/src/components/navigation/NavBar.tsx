import { FileText, Info, Menu, MessageSquareText, Search, Settings } from "lucide-react";
import { motion } from "motion/react";
import { useEffect, useState } from "react";
import { NavLink, useLocation } from "react-router";

import { spring } from "@/components/animations/motion";
import { Dialog, DialogDescription, DialogTitle, DialogTrigger, SheetContent } from "@/components/ui/overlays";
import { cn } from "@/lib/utils";
import { Logo } from "./Logo";
import { StatusIndicator } from "./StatusIndicator";

const LINKS = [
  { to: "/documents", label: "Documents", icon: FileText },
  { to: "/search", label: "Search", icon: Search },
  { to: "/ask", label: "Ask", icon: MessageSquareText },
  { to: "/settings", label: "Settings", icon: Settings },
] as const;

function isActive(pathname: string, to: string) {
  return pathname === to || pathname.startsWith(`${to}/`);
}

/** Floating glass navigation (desktop) and a compact header with a sheet (mobile). */
export function NavBar() {
  const { pathname } = useLocation();
  const [open, setOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);

  // Once content scrolls under the bar, switch from light glass to a solid
  // frosted surface so text behind it can never reduce legibility.
  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <header
      className={cn(
        "sticky top-0 z-40 px-4 pb-2 pt-4 transition-[background] duration-300 sm:px-6",
        // Fade the page out behind the floating bar so scrolled content never peeks around it.
        scrolled && "bg-[linear-gradient(to_bottom,var(--bg)_60%,transparent)]",
      )}
    >
      <nav
        aria-label="Main"
        className={cn(
          "mx-auto flex h-14 max-w-6xl items-center justify-between gap-4 rounded-2xl pl-3 pr-2 transition-[background-color,box-shadow,border-color] duration-300",
          scrolled ? "nav-solid" : "glass",
        )}
      >
        <Logo />

        <ul className="hidden items-center gap-1 md:flex">
          {LINKS.map(({ to, label, icon: Icon }) => {
            const active = isActive(pathname, to);
            return (
              <li key={to} className="relative">
                <NavLink
                  to={to}
                  className={cn(
                    "relative z-10 flex h-9 items-center gap-2 rounded-xl px-3.5 text-[13.5px] font-medium transition-colors",
                    active ? "text-fg" : "text-fg-muted hover:text-fg",
                  )}
                >
                  <Icon className="size-4" />
                  {label}
                </NavLink>
                {active && (
                  <motion.span
                    layoutId="nav-active"
                    transition={spring}
                    className="absolute inset-0 rounded-xl border border-line-strong bg-surface-2 shadow-[0_0_24px_-8px_var(--accent-glow)]"
                  />
                )}
              </li>
            );
          })}
        </ul>

        <div className="flex items-center gap-1">
          <StatusIndicator />
          <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger
              className="inline-flex size-9 items-center justify-center rounded-xl text-fg-muted hover:bg-surface-2 hover:text-fg md:hidden"
              aria-label="Open navigation"
            >
              <Menu className="size-5" />
            </DialogTrigger>
            <SheetContent>
              <DialogTitle className="mb-1 text-sm font-semibold">Navigate</DialogTitle>
              <DialogDescription className="mb-5 text-xs text-fg-muted">DocMind sections</DialogDescription>
              <ul className="space-y-1">
                {[...LINKS, { to: "/about", label: "How it works", icon: Info }].map(({ to, label, icon: Icon }) => (
                  <li key={to}>
                    <NavLink
                      to={to}
                      onClick={() => setOpen(false)}
                      className={cn(
                        "flex h-12 items-center gap-3 rounded-xl px-3 text-[15px] transition-colors",
                        isActive(pathname, to) ? "bg-surface-2 text-fg" : "text-fg-muted hover:bg-surface hover:text-fg",
                      )}
                    >
                      <Icon className="size-4.5" />
                      {label}
                    </NavLink>
                  </li>
                ))}
              </ul>
            </SheetContent>
          </Dialog>
        </div>
      </nav>
    </header>
  );
}
