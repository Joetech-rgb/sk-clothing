import { afterEach, describe, expect, it, vi } from "vitest";
import { apiRequest } from "./request";

interface Call {
  url: string;
  init: RequestInit;
}

function fakeFetch(respond: () => Response | Promise<Response>) {
  const calls: Call[] = [];
  const impl = ((url: string, init: RequestInit) => {
    calls.push({ url, init });
    return Promise.resolve(respond());
  }) as unknown as typeof fetch;
  return { impl, calls };
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status });
}

afterEach(() => {
  vi.useRealTimers();
});

describe("apiRequest", () => {
  it("builds the URL with a query, leaving out undefined values, and returns the data", async () => {
    const { impl, calls } = fakeFetch(() => json({ results: [] }));
    const result = await apiRequest<{ results: unknown[] }>("GET", "/catalog/products/", {
      query: { q: "shirt", limit: 24, cursor: undefined },
      fetch: impl,
    });
    expect(calls[0]?.url).toBe("/api/v1/catalog/products/?q=shirt&limit=24");
    expect(result).toEqual({ ok: true, status: 200, data: { results: [] } });
  });

  it("sends a JSON body, the idempotency key and no cookies to other sites", async () => {
    const { impl, calls } = fakeFetch(() => json({ reference: "SK1" }, 201));
    const result = await apiRequest("POST", "/orders/", {
      body: { items: [{ variant_id: 1, quantity: 2 }] },
      idempotencyKey: "abc-12345678",
      fetch: impl,
    });
    const init = calls[0]?.init as RequestInit & { headers: Record<string, string> };
    expect(init.method).toBe("POST");
    expect(init.headers["Content-Type"]).toBe("application/json");
    expect(init.headers["Idempotency-Key"]).toBe("abc-12345678");
    expect(init.credentials).toBe("same-origin");
    expect(JSON.parse(init.body as string)).toEqual({ items: [{ variant_id: 1, quantity: 2 }] });
    expect(result).toMatchObject({ ok: true, status: 201 });
  });

  it("sends no content type on a request without a body", async () => {
    const { impl, calls } = fakeFetch(() => json({}));
    await apiRequest("GET", "/auth/me/", { fetch: impl });
    const init = calls[0]?.init as RequestInit & { headers: Record<string, string> };
    expect(init.headers["Content-Type"]).toBeUndefined();
  });

  it("uses an absolute base URL when given one", async () => {
    const { impl, calls } = fakeFetch(() => json({}));
    await apiRequest("GET", "/delivery/stations/", {
      baseUrl: "http://backend:8000/api/v1",
      fetch: impl,
    });
    expect(calls[0]?.url).toBe("http://backend:8000/api/v1/delivery/stations/");
  });

  it("treats an empty success reply as null data", async () => {
    const { impl } = fakeFetch(() => new Response(null, { status: 204 }));
    const result = await apiRequest("POST", "/auth/logout/", { fetch: impl });
    expect(result).toEqual({ ok: true, status: 204, data: null });
  });

  it("returns the server's error envelope", async () => {
    const { impl } = fakeFetch(() =>
      json({ error: { code: "order_not_found", message: "We could not find that order." } }, 404),
    );
    const result = await apiRequest("POST", "/orders/lookup/", { body: {}, fetch: impl });
    expect(result).toMatchObject({
      ok: false,
      error: { status: 404, code: "order_not_found", message: "We could not find that order." },
    });
  });

  it("copes with an error page that is not our envelope", async () => {
    const { impl } = fakeFetch(() => new Response("<html>Bad gateway</html>", { status: 502 }));
    const result = await apiRequest("GET", "/catalog/categories/", { fetch: impl });
    expect(result).toMatchObject({ ok: false, error: { status: 502, code: "unexpected_response" } });
  });

  it("treats a success reply that is not JSON as an error", async () => {
    const { impl } = fakeFetch(() => new Response("not json", { status: 200 }));
    const result = await apiRequest("GET", "/catalog/categories/", { fetch: impl });
    expect(result).toMatchObject({ ok: false, error: { code: "unexpected_response" } });
  });

  it("reports a network failure instead of throwing", async () => {
    const impl = (() => Promise.reject(new TypeError("Failed to fetch"))) as unknown as typeof fetch;
    const result = await apiRequest("GET", "/catalog/categories/", { fetch: impl });
    expect(result).toMatchObject({ ok: false, error: { status: 0, code: "network_error" } });
  });

  it("gives up after the timeout", async () => {
    vi.useFakeTimers();
    const impl = ((_url: string, init: RequestInit) =>
      new Promise((_resolve, reject) => {
        init.signal?.addEventListener("abort", () =>
          reject(new DOMException("aborted", "AbortError")),
        );
      })) as unknown as typeof fetch;
    const pending = apiRequest("GET", "/catalog/products/", { timeoutMs: 1000, fetch: impl });
    await vi.advanceTimersByTimeAsync(1000);
    expect(await pending).toMatchObject({ ok: false, error: { code: "network_error" } });
  });
});
