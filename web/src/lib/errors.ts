/**
 * API errors and the user-facing messages for them.
 *
 * Server error *details* are only shown for 4xx responses, whose messages the
 * API writes for users (e.g. "'x.pdf' does not look like a PDF"). 5xx details
 * can contain internal information such as file-system paths, so they are
 * replaced with generic text. Stack traces never reach the browser at all.
 */

export type ErrorKind =
  | "network"
  | "auth"
  | "not_found"
  | "too_large"
  | "invalid_file"
  | "validation"
  | "rate_limited"
  | "llm_unavailable"
  | "llm_failed"
  | "storage_unavailable"
  | "server";

export class ApiError extends Error {
  readonly status: number;
  readonly kind: ErrorKind;
  readonly detail: string | null;

  constructor(status: number, detail: string | null, path = "") {
    const kind = classify(status, detail, path);
    super(friendlyMessage(kind));
    this.name = "ApiError";
    this.status = status;
    this.kind = kind;
    this.detail = status >= 400 && status < 500 ? detail : null;
  }
}

export function classify(status: number, detail: string | null, path = ""): ErrorKind {
  if (status === 0) return "network";
  if (status === 401) return "auth";
  if (status === 404) return "not_found";
  if (status === 411 || status === 413) return "too_large";
  if (status === 429) return "rate_limited";
  if (status === 422) return "validation";
  if (status === 400 && path.includes("/documents/upload")) return "invalid_file";
  if (status === 400) return "validation";
  // The API itself only returns 502 from /ask (LLM provider failure). Elsewhere a
  // 502/504 comes from a proxy in front of an unreachable backend.
  if (status === 502 && path.startsWith("/ask")) return "llm_failed";
  if (status === 502 || status === 504) return "network";
  if (status === 503) {
    return /index unavailable|registry|stored data/i.test(detail ?? "") ? "storage_unavailable" : "llm_unavailable";
  }
  return "server";
}

export function friendlyMessage(kind: ErrorKind): string {
  switch (kind) {
    case "network":
      return "Unable to connect to DocMind.";
    case "auth":
      return "An access token is required.";
    case "not_found":
      return "That item could not be found.";
    case "too_large":
      return "This upload is too large.";
    case "invalid_file":
      return "This file could not be processed.";
    case "validation":
      return "Please check your input and try again.";
    case "rate_limited":
      return "Too many requests. Please try again.";
    case "llm_unavailable":
      return "AI question answering is currently unavailable.";
    case "llm_failed":
      return "The AI provider returned an error. Please try again in a moment.";
    case "storage_unavailable":
      return "DocMind's document index is unavailable. The server log explains how to recover.";
    default:
      return "Something went wrong on the server.";
  }
}

/** Message + optional safe detail for display. */
export function describeError(error: unknown): { title: string; detail: string | null } {
  if (error instanceof ApiError) return { title: error.message, detail: error.detail };
  return { title: friendlyMessage("server"), detail: null };
}
