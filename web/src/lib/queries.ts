/** React Query hooks: server state lives here, not in components. */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "./api";
import { ApiError } from "./errors";
import type { DocumentInfo, DocumentStatus } from "./types";

export const isPendingStatus = (status: DocumentStatus) => status === "queued" || status === "processing";
/** Poll quickly while the server is still processing something, otherwise not at all. */
const pollWhilePending = (docs: DocumentInfo[] | DocumentInfo | undefined) =>
  (Array.isArray(docs) ? docs : docs ? [docs] : []).some((d) => isPendingStatus(d.status)) ? 1500 : false;

export const keys = {
  health: ["health"] as const,
  documents: ["documents"] as const,
  document: (id: string) => ["documents", id] as const,
  chunks: (id: string) => ["documents", id, "chunks"] as const,
  settings: ["settings"] as const,
};

export function useHealth() {
  return useQuery({
    queryKey: keys.health,
    queryFn: api.health,
    refetchInterval: 20_000,
    retry: (count, error) => count < 2 && !(error instanceof ApiError && error.kind === "storage_unavailable"),
  });
}

export function useDocuments() {
  return useQuery({ queryKey: keys.documents, queryFn: api.documents, refetchInterval: (q) => pollWhilePending(q.state.data) });
}

export function useDocument(id: string) {
  return useQuery({
    queryKey: keys.document(id),
    queryFn: () => api.document(id),
    refetchInterval: (q) => pollWhilePending(q.state.data),
  });
}

export function useDocumentChunks(id: string, enabled = true) {
  return useQuery({ queryKey: keys.chunks(id), queryFn: () => api.chunks(id), enabled });
}

/** Refresh everything that depends on the document set. */
export function useInvalidateDocuments() {
  const client = useQueryClient();
  return () =>
    Promise.all([
      client.invalidateQueries({ queryKey: keys.documents }),
      client.invalidateQueries({ queryKey: keys.health }),
    ]);
}

export function useDeleteDocument() {
  const invalidate = useInvalidateDocuments();
  return useMutation({ mutationFn: api.deleteDocument, onSuccess: invalidate });
}

export function useReprocessDocument() {
  const invalidate = useInvalidateDocuments();
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.process([id], true, true),
    onSuccess: (_data, id) => {
      client.invalidateQueries({ queryKey: keys.chunks(id) });
      return invalidate();
    },
  });
}

export function useServerSettings() {
  return useQuery({ queryKey: keys.settings, queryFn: api.settings });
}
