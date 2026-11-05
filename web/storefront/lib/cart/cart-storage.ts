import { addLine, EMPTY_CART } from "./cart";
import type { Cart, CartLine } from "./cart";

export const CART_STORAGE_KEY = "sk.cart.v1";
const VERSION = 1;

/** The small part of the Storage API we use, so tests need no browser. */
export interface KeyValueStorage {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}

/** Writes only the three known fields per line. Nothing else can be stored. */
export function serializeCart(cart: Cart): string {
  const lines = cart.map(({ productSlug, variantId, quantity }) => ({
    productSlug,
    variantId,
    quantity,
  }));
  return JSON.stringify({ version: VERSION, lines });
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function toLine(value: unknown): CartLine | null {
  if (!isRecord(value)) return null;
  const { productSlug, variantId, quantity } = value;
  if (typeof productSlug !== "string" || productSlug === "") return null;
  if (typeof variantId !== "string" || variantId === "") return null;
  if (typeof quantity !== "number" || !Number.isInteger(quantity) || quantity < 1) {
    return null;
  }
  return { productSlug, variantId, quantity };
}

/**
 * Reads stored text defensively: anything unexpected gives an empty cart, and
 * invalid lines are dropped. Extra fields (for example a stale price) are discarded.
 */
export function parseCart(raw: string | null): Cart {
  if (raw === null) return EMPTY_CART;
  let data: unknown;
  try {
    data = JSON.parse(raw);
  } catch {
    return EMPTY_CART;
  }
  if (!isRecord(data) || data.version !== VERSION || !Array.isArray(data.lines)) {
    return EMPTY_CART;
  }
  let cart: Cart = EMPTY_CART;
  for (const item of data.lines) {
    const line = toLine(item);
    if (line) cart = addLine(cart, line);
  }
  return cart;
}

export function loadCart(storage: KeyValueStorage | undefined): Cart {
  if (!storage) return EMPTY_CART;
  try {
    return parseCart(storage.getItem(CART_STORAGE_KEY));
  } catch {
    return EMPTY_CART;
  }
}

/** Returns false if the browser refused to store it (private mode, full disk). */
export function saveCart(storage: KeyValueStorage | undefined, cart: Cart): boolean {
  if (!storage) return false;
  try {
    storage.setItem(CART_STORAGE_KEY, serializeCart(cart));
    return true;
  } catch {
    return false;
  }
}
