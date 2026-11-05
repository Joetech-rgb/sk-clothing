import { describe, expect, it } from "vitest";
import type { Cart } from "./cart";
import {
  CART_STORAGE_KEY,
  loadCart,
  parseCart,
  saveCart,
  serializeCart,
} from "./cart-storage";
import type { KeyValueStorage } from "./cart-storage";

const cart: Cart = [
  { productSlug: "tee", variantId: "v-red", quantity: 2 },
  { productSlug: "tee", variantId: "v-blue", quantity: 3 },
];

function memoryStorage(initial: Record<string, string> = {}): KeyValueStorage {
  const data = new Map(Object.entries(initial));
  return {
    getItem: (key) => data.get(key) ?? null,
    setItem: (key, value) => void data.set(key, value),
    removeItem: (key) => void data.delete(key),
  };
}

const brokenStorage: KeyValueStorage = {
  getItem: () => {
    throw new Error("blocked");
  },
  setItem: () => {
    throw new Error("quota");
  },
  removeItem: () => {
    throw new Error("blocked");
  },
};

describe("serialize and parse", () => {
  it("round-trips a cart", () => {
    expect(parseCart(serializeCart(cart))).toEqual(cart);
  });

  it("stores only version and the three known fields per line (never a price)", () => {
    const parsed = JSON.parse(serializeCart(cart)) as {
      lines: Record<string, unknown>[];
    };
    expect(Object.keys(parsed).sort()).toEqual(["lines", "version"]);
    for (const line of parsed.lines) {
      expect(Object.keys(line).sort()).toEqual(["productSlug", "quantity", "variantId"]);
    }
  });

  it("gives an empty cart for missing, broken or wrong-version data", () => {
    expect(parseCart(null)).toEqual([]);
    expect(parseCart("not json")).toEqual([]);
    expect(parseCart(JSON.stringify({ version: 2, lines: [] }))).toEqual([]);
    expect(parseCart(JSON.stringify({ version: 1, lines: "x" }))).toEqual([]);
    expect(parseCart(JSON.stringify([1, 2]))).toEqual([]);
  });

  it("drops invalid lines and keeps valid ones", () => {
    const raw = JSON.stringify({
      version: 1,
      lines: [
        { productSlug: "tee", variantId: "v1", quantity: 1 },
        { productSlug: "tee", variantId: "v2", quantity: 0 },
        { productSlug: "tee", variantId: "v3", quantity: -4 },
        { productSlug: "tee", variantId: "v4", quantity: "2" },
        { productSlug: "", variantId: "v5", quantity: 1 },
        { variantId: "v6", quantity: 1 },
        null,
        "junk",
      ],
    });
    expect(parseCart(raw)).toEqual([{ productSlug: "tee", variantId: "v1", quantity: 1 }]);
  });

  it("discards extra fields such as a stale price", () => {
    const raw = JSON.stringify({
      version: 1,
      lines: [{ productSlug: "tee", variantId: "v1", quantity: 1, price: 100 }],
    });
    expect(parseCart(raw)).toEqual([{ productSlug: "tee", variantId: "v1", quantity: 1 }]);
  });

  it("merges duplicate variants found in storage", () => {
    const raw = JSON.stringify({
      version: 1,
      lines: [
        { productSlug: "tee", variantId: "v1", quantity: 1 },
        { productSlug: "tee", variantId: "v1", quantity: 2 },
      ],
    });
    expect(parseCart(raw)).toEqual([{ productSlug: "tee", variantId: "v1", quantity: 3 }]);
  });
});

describe("loadCart and saveCart", () => {
  it("saves then loads through storage", () => {
    const storage = memoryStorage();
    expect(saveCart(storage, cart)).toBe(true);
    expect(storage.getItem(CART_STORAGE_KEY)).not.toBeNull();
    expect(loadCart(storage)).toEqual(cart);
  });

  it("copes with unavailable storage", () => {
    expect(loadCart(undefined)).toEqual([]);
    expect(saveCart(undefined, cart)).toBe(false);
  });

  it("copes with storage that throws", () => {
    expect(loadCart(brokenStorage)).toEqual([]);
    expect(saveCart(brokenStorage, cart)).toBe(false);
  });
});
