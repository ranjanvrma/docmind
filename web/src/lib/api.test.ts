import { afterEach, describe, expect, it, vi } from "vitest";

import { api, hasAdminToken, setAdminToken } from "./api";
import { clearLegacyToken } from "./preferences";

function mockFetch() {
  const calls: { url: string; init: RequestInit }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init: RequestInit) => {
      calls.push({ url, init });
      return new Response("[]", { status: 200, headers: { "Content-Type": "application/json" } });
    }),
  );
  return calls;
}

const headerNames = (init: RequestInit) => Object.keys((init.headers ?? {}) as Record<string, string>).map((h) => h.toLowerCase());

afterEach(() => {
  setAdminToken(null);
  vi.unstubAllGlobals();
  localStorage.clear();
  sessionStorage.clear();
});

describe("API client", () => {
  it("sends no token on visitor requests; the session travels as a same-origin cookie", async () => {
    const calls = mockFetch();
    await api.documents();
    await api.search("refunds", 5);
    await api.ask("What is the refund policy?", 5);
    for (const { init } of calls) {
      expect(headerNames(init)).not.toContain("x-api-key");
      expect(headerNames(init)).not.toContain("authorization");
      expect(init.credentials).toBe("same-origin");
    }
  });

  it("sends the administrator token only to /api/admin and never stores it", async () => {
    const calls = mockFetch();
    setAdminToken("admin-secret-token");
    await api.settings();
    await api.documents();
    expect(calls[0].url).toBe("/api/admin/settings");
    expect((calls[0].init.headers as Record<string, string>)["X-API-Key"]).toBe("admin-secret-token");
    expect(headerNames(calls[1].init)).not.toContain("x-api-key");
    expect(JSON.stringify({ ...localStorage })).not.toContain("admin-secret-token");
    expect(JSON.stringify({ ...sessionStorage })).not.toContain("admin-secret-token");
    setAdminToken(null);
    expect(hasAdminToken()).toBe(false);
  });

  it("removes access tokens that older versions stored in the browser", () => {
    localStorage.setItem("docmind.token", "old");
    sessionStorage.setItem("docmind.token", "old");
    clearLegacyToken();
    expect(localStorage.getItem("docmind.token")).toBeNull();
    expect(sessionStorage.getItem("docmind.token")).toBeNull();
  });

  it("passes Retry-After through to the error", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify({ detail: "Question limit reached." }), { status: 429, headers: { "Retry-After": "120" } })),
    );
    await expect(api.ask("q", 5)).rejects.toMatchObject({ status: 429, kind: "rate_limited", retryAfter: 120 });
  });
});
