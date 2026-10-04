/**
 * Typed client for the DocMind API (same origin, under /api).
 *
 * Every request carries the access token from preferences if one is set.
 * Errors are normalised into ApiError so the UI can show friendly messages.
 */
import { ApiError } from "./errors";
import { emit } from "./events";
import { getToken } from "./preferences";
import type {
  AskResponse,
  DocumentChunk,
  DocumentInfo,
  EditableSettings,
  EvaluationReport,
  Health,
  LlmTestResult,
  ProcessResponse,
  SearchResponse,
  SettingsView,
  UploadItem,
} from "./types";

// Same origin by default: FastAPI serves the built UI, and Vite proxies /api in
// development. Set VITE_API_BASE_URL at build time only when the UI is hosted
// on a different origin from the API (that API must then list this origin in
// CORS_ALLOW_ORIGINS). Never put secrets in VITE_* variables: they are public.
const API_ORIGIN = (import.meta.env.VITE_API_BASE_URL ?? "").trim().replace(/\/+$/, "");
const BASE = `${API_ORIGIN}/api`;

function authHeaders(): Record<string, string> {
  const token = getToken();
  return token ? { "X-API-Key": token } : {};
}

async function parseError(response: Response, path: string): Promise<ApiError> {
  let detail: string | null = null;
  try {
    const body = await response.json();
    if (typeof body?.detail === "string") detail = body.detail;
    else if (Array.isArray(body?.detail)) {
      // FastAPI validation errors
      detail = body.detail.map((d: { msg?: string }) => d.msg).filter(Boolean).join("; ");
    }
  } catch {
    /* non-JSON error body: ignore it */
  }
  if (response.status === 401) emit("auth-required");
  return new ApiError(response.status, detail, path);
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE}${path}`, {
      ...init,
      headers: { ...(init.body ? { "Content-Type": "application/json" } : {}), ...authHeaders(), ...init.headers },
    });
  } catch {
    throw new ApiError(0, null, path);
  }
  if (!response.ok) throw await parseError(response, path);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  health: () => request<Health>("/health"),
  documents: () => request<DocumentInfo[]>("/documents"),
  document: (id: string) => request<DocumentInfo>(`/documents/${encodeURIComponent(id)}`),
  chunks: (id: string) => request<DocumentChunk[]>(`/documents/${encodeURIComponent(id)}/chunks`),
  deleteDocument: (id: string) => request<void>(`/documents/${encodeURIComponent(id)}`, { method: "DELETE" }),
  process: (docIds?: string[], force = false) =>
    request<ProcessResponse>("/documents/process", {
      method: "POST",
      body: JSON.stringify({ doc_ids: docIds ?? null, force }),
    }),
  search: (query: string, topK: number, docIds?: string[]) =>
    request<SearchResponse>("/search", {
      method: "POST",
      body: JSON.stringify({ query, top_k: topK, doc_ids: docIds?.length ? docIds : null }),
    }),
  ask: (question: string, topK: number, docIds?: string[]) =>
    request<AskResponse>("/ask", {
      method: "POST",
      body: JSON.stringify({ question, top_k: topK, doc_ids: docIds?.length ? docIds : null }),
    }),

  settings: () => request<SettingsView>("/settings"),
  updateSettings: (changes: Partial<EditableSettings> & { llm_api_key?: string }) =>
    request<SettingsView>("/settings", { method: "PATCH", body: JSON.stringify(changes) }),
  removeSavedLlmKey: () => request<SettingsView>("/settings/llm-api-key", { method: "DELETE" }),
  resetSettings: () => request<SettingsView>("/settings/reset", { method: "POST" }),
  testLlm: () => request<LlmTestResult>("/settings/test-llm", { method: "POST" }),
  evaluateRetrieval: (ks = [1, 3, 5]) =>
    request<EvaluationReport>("/evaluation/retrieval", { method: "POST", body: JSON.stringify({ ks }) }),

  /**
   * Upload files with real byte-level progress. fetch() cannot report upload
   * progress, so this one request uses XMLHttpRequest.
   */
  upload(files: File[], onProgress?: (fraction: number) => void): Promise<UploadItem[]> {
    const path = "/documents/upload";
    return new Promise((resolve, reject) => {
      const form = new FormData();
      files.forEach((file) => form.append("files", file, file.name));
      const xhr = new XMLHttpRequest();
      xhr.open("POST", `${BASE}${path}`);
      Object.entries(authHeaders()).forEach(([k, v]) => xhr.setRequestHeader(k, v));
      xhr.upload.onprogress = (event) => {
        if (event.lengthComputable) onProgress?.(event.loaded / event.total);
      };
      xhr.onerror = () => reject(new ApiError(0, null, path));
      xhr.onload = () => {
        let body: { items?: UploadItem[]; detail?: unknown } = {};
        try {
          body = JSON.parse(xhr.responseText);
        } catch {
          /* ignore */
        }
        if (xhr.status >= 200 && xhr.status < 300 && body.items) return resolve(body.items);
        if (xhr.status === 401) emit("auth-required");
        reject(new ApiError(xhr.status, typeof body.detail === "string" ? body.detail : null, path));
      };
      xhr.send(form);
    });
  },
};
