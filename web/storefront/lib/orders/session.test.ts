import { describe, expect, it } from "vitest";
import type { KeyValueStorage } from "../cart/cart-storage";
import { LAST_ORDER_KEY, loadLastOrder, saveLastOrder } from "./session";
import type { LastOrder } from "./session";

function memory(initial: Record<string, string> = {}): KeyValueStorage {
  const data = new Map(Object.entries(initial));
  return {
    getItem: (key) => data.get(key) ?? null,
    setItem: (key, value) => void data.set(key, value),
    removeItem: (key) => void data.delete(key),
  };
}

const broken: KeyValueStorage = {
  getItem: () => {
    throw new Error("blocked");
  },
  setItem: () => {
    throw new Error("blocked");
  },
  removeItem: () => {
    throw new Error("blocked");
  },
};

const order: LastOrder = {
  reference: "SK-1",
  phone: "0240000000",
  email: "ama@example.com",
  payment: "online",
};

describe("last order in the tab", () => {
  it("saves and loads", () => {
    const storage = memory();
    expect(saveLastOrder(storage, order)).toBe(true);
    expect(loadLastOrder(storage)).toEqual(order);
  });

  it("returns null when nothing was saved", () => {
    expect(loadLastOrder(memory())).toBeNull();
  });

  it.each([
    ["broken json", "{"],
    ["a number", "5"],
    ["no reference", JSON.stringify({ ...order, reference: "" })],
    ["an unknown payment kind", JSON.stringify({ ...order, payment: "cash" })],
    ["a missing phone", JSON.stringify({ reference: "SK-1", email: "", payment: "cod" })],
  ])("returns null for %s", (_label, raw) => {
    expect(loadLastOrder(memory({ [LAST_ORDER_KEY]: raw }))).toBeNull();
  });

  it("copes with blocked or missing storage", () => {
    expect(saveLastOrder(broken, order)).toBe(false);
    expect(loadLastOrder(broken)).toBeNull();
    expect(saveLastOrder(undefined, order)).toBe(false);
    expect(loadLastOrder(undefined)).toBeNull();
  });
});
