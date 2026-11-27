import { describe, expect, it } from "vitest";
import { isSignedIn, requestLoginCode, signOut, verifyLoginCode } from "./api";

interface Call {
  method: string;
  url: string;
  body: unknown;
}

function fakeFetch(status: number, body: unknown = {}) {
  const calls: Call[] = [];
  const impl = ((url: string, init: RequestInit) => {
    calls.push({
      method: String(init.method),
      url,
      body: init.body ? JSON.parse(String(init.body)) : undefined,
    });
    return Promise.resolve(new Response(status === 204 ? null : JSON.stringify(body), { status }));
  }) as unknown as typeof fetch;
  return { impl, calls };
}

describe("login API calls", () => {
  it("asks for a code with the trimmed phone number only", async () => {
    const { impl, calls } = fakeFetch(202, { expires_in_seconds: 300 });
    const result = await requestLoginCode(" 0240000000 ", { fetch: impl });
    expect(result.ok).toBe(true);
    expect(calls[0]).toEqual({
      method: "POST",
      url: "/api/v1/auth/code/request/",
      body: { phone: "0240000000" },
    });
  });

  it("verifies with the phone and the code, trimmed", async () => {
    const { impl, calls } = fakeFetch(200, { is_new_customer: true, user: { id: 1 } });
    const result = await verifyLoginCode("0240000000", " 123456 ", { fetch: impl });
    expect(result.ok).toBe(true);
    expect(calls[0]?.body).toEqual({ phone: "0240000000", code: "123456" });
  });

  it("shows the server's message for a wrong code", async () => {
    const { impl } = fakeFetch(400, {
      error: { code: "invalid_code", message: "That code is not valid. Check it, or ask for a new one." },
    });
    const result = await verifyLoginCode("0240000000", "000000", { fetch: impl });
    expect(result).toMatchObject({ ok: false, error: { code: "invalid_code" } });
  });

  it("reports a throttled request with the wait", async () => {
    const { impl } = fakeFetch(429, {
      error: { code: "throttled", message: "Slow down.", details: { retry_after_seconds: 30 } },
    });
    const result = await requestLoginCode("0240000000", { fetch: impl });
    expect(result).toMatchObject({ ok: false, error: { retryAfterSeconds: 30 } });
  });
});

describe("session", () => {
  it("is signed in when the server answers", async () => {
    const { impl } = fakeFetch(200, { id: 1 });
    expect(await isSignedIn({ fetch: impl })).toBe(true);
  });

  it("is not signed in when the server says 401", async () => {
    const { impl } = fakeFetch(401, { error: { code: "not_authenticated", message: "Sign in." } });
    expect(await isSignedIn({ fetch: impl })).toBe(false);
  });

  it("is not signed in when the server cannot be reached", async () => {
    const impl = (() => Promise.reject(new TypeError("offline"))) as unknown as typeof fetch;
    expect(await isSignedIn({ fetch: impl })).toBe(false);
  });

  it("signs out with a POST", async () => {
    const { impl, calls } = fakeFetch(204);
    const result = await signOut({ fetch: impl });
    expect(result.ok).toBe(true);
    expect(calls[0]).toMatchObject({ method: "POST", url: "/api/v1/auth/logout/" });
  });
});
