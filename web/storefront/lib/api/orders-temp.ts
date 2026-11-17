/**
 * TEMPORARY, pending the human's approval (see PROGRESS.md "Deviations").
 *
 * The OpenAPI schema does not describe the responses of the order, lookup and payment
 * endpoints yet, so the generated client has no types for them. Until Agent B adds the response
 * schemas and the snapshot is refreshed, this file reads only the handful of fields the
 * customer screens need, checking each one at run time. Replace it with the generated types as
 * soon as they exist. The shapes below come from the backend code (orders/views.py order_json
 * and payments/api.py), not from guesswork.
 */

export interface OrderLineView {
  name: string;
  quantity: number;
  lineTotalDisplay: string;
}

export interface OrderView {
  reference: string;
  paymentStatus: string;
  fulfilmentStatus: string;
  refundStatus: string;
  deliveryMethod: string;
  subtotalDisplay: string;
  deliveryFeeDisplay: string | null;
  totalDisplay: string | null;
  lines: OrderLineView[];
  /** Shown once the backend includes it in the order response. */
  deliveryCode: string | null;
}

/** The payment status value the backend uses for a paid order. To be confirmed in states.py. */
export const PAID_STATUS = "paid";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function moneyDisplay(value: unknown): string | null {
  return isRecord(value) && typeof value.display === "string" ? value.display : null;
}

function text(value: unknown): string {
  return typeof value === "string" ? value : "";
}

export function readOrder(data: unknown): OrderView | null {
  if (!isRecord(data)) return null;
  const reference = data.reference;
  const subtotal = moneyDisplay(data.subtotal);
  if (typeof reference !== "string" || reference === "") return null;
  if (typeof data.payment_status !== "string" || typeof data.fulfilment_status !== "string") {
    return null;
  }
  if (subtotal === null) return null;

  const lines: OrderLineView[] = [];
  if (Array.isArray(data.lines)) {
    for (const line of data.lines) {
      if (!isRecord(line)) continue;
      const lineTotal = moneyDisplay(line.line_total);
      if (typeof line.name !== "string" || typeof line.quantity !== "number" || lineTotal === null) {
        continue;
      }
      lines.push({ name: line.name, quantity: line.quantity, lineTotalDisplay: lineTotal });
    }
  }

  return {
    reference,
    paymentStatus: data.payment_status,
    fulfilmentStatus: data.fulfilment_status,
    refundStatus: text(data.refund_status),
    deliveryMethod: text(data.delivery_method),
    subtotalDisplay: subtotal,
    deliveryFeeDisplay: moneyDisplay(data.delivery_fee),
    totalDisplay: moneyDisplay(data.total),
    lines,
    deliveryCode:
      typeof data.delivery_code === "string" && data.delivery_code !== ""
        ? data.delivery_code
        : null,
  };
}

export interface PaymentStart {
  authorizationUrl: string;
  reference: string;
}

/** The payment page address must be a secure web address, or it is refused. */
export function readPaymentStart(data: unknown): PaymentStart | null {
  if (!isRecord(data)) return null;
  const { authorization_url: url, reference } = data;
  if (typeof url !== "string" || !url.startsWith("https://")) return null;
  if (typeof reference !== "string" || reference === "") return null;
  return { authorizationUrl: url, reference };
}

export function readVerifyOutcome(data: unknown): string | null {
  return isRecord(data) && typeof data.outcome === "string" ? data.outcome : null;
}
