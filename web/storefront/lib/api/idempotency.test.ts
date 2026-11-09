import { afterEach, describe, expect, it, vi } from "vitest";
import { IDEMPOTENCY_KEY_PATTERN, newIdempotencyKey } from "./idempotency";

// Keep the real crypto: the fake one below borrows its random numbers.
const realCrypto = globalThis.crypto;

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("newIdempotencyKey", () => {
  it("makes keys the server accepts", () => {
    for (let i = 0; i < 20; i++) {
      expect(newIdempotencyKey()).toMatch(IDEMPOTENCY_KEY_PATTERN);
    }
  });

  it("makes a different key each time", () => {
    const keys = new Set(Array.from({ length: 200 }, () => newIdempotencyKey()));
    expect(keys.size).toBe(200);
  });

  it("still works on a page where randomUUID is not available", () => {
    vi.stubGlobal("crypto", {
      getRandomValues: (array: Uint8Array) => realCrypto.getRandomValues(array),
    });
    const key = newIdempotencyKey();
    expect(key).toMatch(IDEMPOTENCY_KEY_PATTERN);
    expect(key).toHaveLength(32);
  });
});