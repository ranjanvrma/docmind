/**
 * Typed client for the DocMind API (same origin, under /api).
 *
 * Visitors need no credentials: the server identifies each browser with an
 * HttpOnly session cookie that this code never sees (the browser sends it on
 * same-origin requests automatically). Only the administrator endpoints
 * (/api/admin/*) take a token, which is kept in memory for the current page
 * and never written to browser storage.
 */
import { ApiError } from "./errors";
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
// development. Session cookies are same-origin only, so the public app must be
// served from the API's origin. Never put secrets in VITE_* variables: they are public.
const API_ORIGIN = (import.meta.env.VITE_API_BASE_URL ?? "").trim().replace(/\/+$/, "");
const BASE = `${API_ORIGIN}/api`;

let adminToken: string | null = null;

/** Administrator token for /api/admin/* (memory only; cleared on reload). */
export function setAdminToken(token: string | null) {
  adminToken = token && token.trim() ? token.trim() : null;
}

export function hasAdminToken(): boolean {
  return adminToken !== null;
}

function retryAfter(value: string | null): number | null {
  const seconds = value ? Number(value) : NaN;
  return Number.isFinite(seconds) && seconds > 0 ? seconds : null;
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
  return new ApiError(response.status, detail, path, retryAfter(response.headers.get("Retry-After")));
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response;
  const admin: Record<string, string> = path.startsWith("/admin/") && adminToken ? { "X-API-Key": adminToken } : {};
  try {
    response = await fetch(`${BASE}${path}`, {
      ...init,
      credentials: "same-origin",
      headers: { ...(init.body ? { "Content-Type": "application/json" } : {}), ...admin, ...init.headers },
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
  /** With background=true the server answers 202 at once; poll documents for status. */
  process: (docIds?: string[], force = false, background = false) =>
    request<ProcessResponse>("/documents/process", {
      method: "POST",
      body: JSON.stringify({ doc_ids: docIds ?? null, force, background }),
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

  // Administrator endpoints (DOCMIND_API_TOKEN).
  settings: () => request<SettingsView>("/admin/settings"),
  updateSettings: (changes: Partial<EditableSettings> & { llm_api_key?: string }) =>
    request<SettingsView>("/admin/settings", { method: "PATCH", body: JSON.stringify(changes) }),
  removeSavedLlmKey: () => request<SettingsView>("/admin/settings/llm-api-key", { method: "DELETE" }),
  resetSettings: () => request<SettingsView>("/admin/settings/reset", { method: "POST" }),
  testLlm: () => request<LlmTestResult>("/admin/settings/test-llm", { method: "POST" }),
  evaluateRetrieval: (ks = [1, 3, 5]) =>
    request<EvaluationReport>("/admin/evaluation/retrieval", { method: "POST", body: JSON.stringify({ ks }) }),

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
        const detail = typeof body.detail === "string" ? body.detail : null;
        reject(new ApiError(xhr.status, detail, path, retryAfter(xhr.getResponseHeader("Retry-After"))));
      };
      xhr.send(form);
    });
  },
};
