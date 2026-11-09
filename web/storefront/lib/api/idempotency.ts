/** The server accepts 8 to 64 letters, digits, "_" or "-" (POST /api/v1/orders/). */
export const IDEMPOTENCY_KEY_PATTERN = /^[A-Za-z0-9_-]{8,64}$/;

/**
 * A fresh key for one checkout attempt. Reuse the SAME key when retrying that attempt
 * (so a double tap or a lost response cannot place two orders), and make a new one only
 * when the customer changes what they are ordering.
 */
export function newIdempotencyKey(): string {
  if (typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  // randomUUID needs a secure page; getRandomValues does not.
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}
