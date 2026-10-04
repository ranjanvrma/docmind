import { describe, expect, it } from "vitest";

import { ApiError, classify, describeError } from "./errors";
import { formatBytes, formatRelative, similarityPercent } from "./format";

describe("error classification", () => {
  it.each([
    [0, null, "", "network"],
    [401, "Missing or invalid API token", "", "auth"],
    [404, "Document not found", "", "not_found"],
    [413, "Upload request exceeds 10 MB", "/documents/upload", "too_large"],
    [400, "'x.pdf' does not look like a PDF", "/documents/upload", "invalid_file"],
    [422, "query must not be blank", "/search", "validation"],
    [429, null, "", "rate_limited"],
    [502, "LLM request failed", "/ask", "llm_failed"],
    [502, null, "/health", "network"],
    [504, null, "/documents", "network"],
    [503, "Question answering needs an LLM.", "/ask", "llm_unavailable"],
    [503, "Search index unavailable: index.faiss is corrupt", "/health", "storage_unavailable"],
    [500, "Internal server error", "", "server"],
  ])("status %i -> %s", (status, detail, path, kind) => {
    expect(classify(status, detail, path)).toBe(kind);
  });

  it("shows server details for 4xx but never for 5xx (they may contain internal paths)", () => {
    const client = new ApiError(400, "'x.pdf' does not look like a PDF", "/documents/upload");
    expect(describeError(client)).toEqual({ title: "This file could not be processed.", detail: "'x.pdf' does not look like a PDF" });

    const server = new ApiError(503, "Search index unavailable: C:\\data\\index\\index.faiss is corrupt", "/health");
    expect(describeError(server).detail).toBeNull();
    expect(describeError(server).title).not.toContain("C:\\");
  });

  it("uses the spec's friendly wording", () => {
    expect(new ApiError(0, null).message).toBe("Unable to connect to DocMind.");
    expect(new ApiError(503, "needs an LLM", "/ask").message).toBe("AI question answering is currently unavailable.");
    expect(new ApiError(429, null).message).toBe("Too many requests. Please try again.");
  });

  it("falls back to a generic message for unknown errors", () => {
    expect(describeError(new Error("stack trace here")).title).toBe("Something went wrong on the server.");
  });
});

describe("formatting", () => {
  it("formats bytes", () => {
    expect(formatBytes(512)).toBe("512 B");
    expect(formatBytes(3546)).toBe("3.5 KB");
    expect(formatBytes(26 * 1024 * 1024)).toBe("26 MB");
  });

  it("clamps similarity to 0-100", () => {
    expect(similarityPercent(0.4862)).toBe(49);
    expect(similarityPercent(-0.2)).toBe(0);
    expect(similarityPercent(1.3)).toBe(100);
  });

  it("formats relative times", () => {
    const now = Date.parse("2026-10-04T12:00:00Z");
    expect(formatRelative("2026-10-04T11:59:50Z", now)).toBe("just now");
    expect(formatRelative("2026-10-04T11:30:00Z", now)).toBe("30 min ago");
    expect(formatRelative("not a date", now)).toBe("–");
  });
});
