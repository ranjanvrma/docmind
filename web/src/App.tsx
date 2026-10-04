import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createBrowserRouter, RouterProvider } from "react-router";
import { Toaster } from "sonner";

import { AppShell } from "@/components/layout/AppShell";
import { PreferencesProvider } from "@/components/layout/PreferencesProvider";
import { ChatProvider } from "@/components/qa/ChatProvider";
import { TooltipProvider } from "@/components/ui/overlays";
import { ApiError } from "@/lib/errors";
import { HomePage } from "@/pages/HomePage";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 10_000,
      refetchOnWindowFocus: false,
      // Don't hammer the server for errors that retrying cannot fix.
      retry: (count, error) => count < 2 && !(error instanceof ApiError && [401, 404, 422].includes(error.status)),
    },
  },
});

/** Shown only while the first, code-split page of a deep link loads. */
function RouteFallback() {
  return (
    <div role="status" aria-label="Loading" className="flex min-h-dvh items-center justify-center">
      <span className="size-2 animate-pulse-soft rounded-full bg-accent" />
    </div>
  );
}

const router = createBrowserRouter([
  {
    element: <AppShell />,
    HydrateFallback: RouteFallback,
    children: [
      { index: true, element: <HomePage /> },
      // Other pages are code-split: each loads on first visit (a few kB each).
      { path: "documents", lazy: async () => ({ Component: (await import("@/pages/DocumentsPage")).DocumentsPage }) },
      { path: "documents/:id", lazy: async () => ({ Component: (await import("@/pages/DocumentDetailPage")).DocumentDetailPage }) },
      { path: "search", lazy: async () => ({ Component: (await import("@/pages/SearchPage")).SearchPage }) },
      { path: "ask", lazy: async () => ({ Component: (await import("@/pages/AskPage")).AskPage }) },
      { path: "settings", lazy: async () => ({ Component: (await import("@/pages/SettingsPage")).SettingsPage }) },
      { path: "about", lazy: async () => ({ Component: (await import("@/pages/AboutPage")).AboutPage }) },
      { path: "*", lazy: async () => ({ Component: (await import("@/pages/NotFoundPage")).NotFoundPage }) },
    ],
  },
]);

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <PreferencesProvider>
        <TooltipProvider>
          <ChatProvider>
            <RouterProvider router={router} />
            <Toaster
              position="bottom-right"
              toastOptions={{
                className: "!bg-[var(--surface-solid)] !text-[var(--fg)] !border-[var(--border-strong)] !rounded-xl",
              }}
            />
          </ChatProvider>
        </TooltipProvider>
      </PreferencesProvider>
    </QueryClientProvider>
  );
}
