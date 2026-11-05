"use client";

import { useCallback, useSyncExternalStore } from "react";
import {
  addLine,
  clearCart,
  EMPTY_CART,
  removeLine,
  setQuantity as setLineQuantity,
  totalQuantity,
} from "./cart";
import type { Cart, CartLine } from "./cart";
import { CART_STORAGE_KEY, loadCart, saveCart } from "./cart-storage";
import type { KeyValueStorage } from "./cart-storage";

let snapshot: Cart = EMPTY_CART;
let loaded = false;
const listeners = new Set<() => void>();

function browserStorage(): KeyValueStorage | undefined {
  try {
    return typeof window === "undefined" ? undefined : window.localStorage;
  } catch {
    return undefined;
  }
}

function emit(): void {
  listeners.forEach((listener) => listener());
}

function update(next: Cart): void {
  snapshot = next;
  saveCart(browserStorage(), next);
  emit();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  const onStorage = (event: StorageEvent) => {
    // Another tab changed the cart (key is null when storage was cleared).
    if (event.key === CART_STORAGE_KEY || event.key === null) {
      snapshot = loadCart(browserStorage());
      emit();
    }
  };
  window.addEventListener("storage", onStorage);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", onStorage);
  };
}

function getSnapshot(): Cart {
  if (!loaded && typeof window !== "undefined") {
    snapshot = loadCart(browserStorage());
    loaded = true;
  }
  return snapshot;
}

function getServerSnapshot(): Cart {
  return EMPTY_CART;
}

export function useCart() {
  const cart = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);

  const add = useCallback((line: CartLine) => update(addLine(snapshot, line)), []);
  const setQuantity = useCallback(
    (variantId: number, quantity: number) =>
      update(setLineQuantity(snapshot, variantId, quantity)),
    [],
  );
  const remove = useCallback(
    (variantId: number) => update(removeLine(snapshot, variantId)),
    [],
  );
  const clear = useCallback(() => update(clearCart()), []);

  return { cart, count: totalQuantity(cart), add, setQuantity, remove, clear };
}
