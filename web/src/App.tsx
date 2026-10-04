import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createBrowserRouter, RouterProvider } from "react-router";
import { Toaster } from "sonner";

import { AppShell } from "@/components/layout/AppShell";
import { PreferencesProvider } from "@/components/layout/PreferencesProvider";
import { ChatProvider } from "@/components/qa/ChatProvider";
import { TooltipProvider } from "@/components/ui/overlays";
import { ApiError } from "@/lib/errors";
import { AboutPage } from "@/pages/AboutPage";
import { AskPage } from "@/pages/AskPage";
import { DocumentDetailPage } from "@/pages/DocumentDetailPage";
import { DocumentsPage } from "@/pages/DocumentsPage";
import { HomePage } from "@/pages/HomePage";
import { NotFoundPage } from "@/pages/NotFoundPage";
import { SearchPage } from "@/pages/SearchPage";
import { SettingsPage } from "@/pages/SettingsPage";

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

const router = createBrowserRouter([
  {
    element: <AppShell />,
    children: [
      { index: true, element: <HomePage /> },
      { path: "documents", element: <DocumentsPage /> },
      { path: "documents/:id", element: <DocumentDetailPage /> },
      { path: "search", element: <SearchPage /> },
      { path: "ask", element: <AskPage /> },
      { path: "settings", element: <SettingsPage /> },
      { path: "about", element: <AboutPage /> },
      { path: "*", element: <NotFoundPage /> },
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
