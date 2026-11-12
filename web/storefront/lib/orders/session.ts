import type { KeyValueStorage } from "../cart/cart-storage";

/** What the browser remembers about the order just placed, until the tab is closed. */
export interface LastOrder {
  reference: string;
  phone: string;
  email: string;
  payment: "online" | "cod";
}

export const LAST_ORDER_KEY = "sk.lastOrder.v1";

/** The tab's own storage, or undefined when it is blocked. Never logged. */
export function browserSession(): KeyValueStorage | undefined {
  try {
    return typeof window === "undefined" ? undefined : window.sessionStorage;
  } catch {
    return undefined;
  }
}

export function saveLastOrder(storage: KeyValueStorage | undefined, order: LastOrder): boolean {
  if (!storage) return false;
  try {
    storage.setItem(LAST_ORDER_KEY, JSON.stringify(order));
    return true;
  } catch {
    return false;
  }
}

export function loadLastOrder(storage: KeyValueStorage | undefined): LastOrder | null {
  if (!storage) return null;
  try {
    const raw = storage.getItem(LAST_ORDER_KEY);
    if (raw === null) return null;
    const data: unknown = JSON.parse(raw);
    if (typeof data !== "object" || data === null) return null;
    const { reference, phone, email, payment } = data as Record<string, unknown>;
    if (typeof reference !== "string" || reference === "") return null;
    if (typeof phone !== "string" || typeof email !== "string") return null;
    if (payment !== "online" && payment !== "cod") return null;
    return { reference, phone, email, payment };
  } catch {
    return null;
  }
}
