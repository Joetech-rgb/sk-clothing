import type { components, paths } from "@sk/api-client";
import { parseApiError } from "../api/errors";
import type { ApiError } from "../api/errors";
import {
  readOrder,
  readPaymentStart,
  readVerifyOutcome,
} from "../api/orders-temp";
import type { OrderView, PaymentStart } from "../api/orders-temp";
import { apiRequest } from "../api/request";
import type { ApiResult } from "../api/request";
import type { Cart } from "../cart/cart";
import type { CheckoutValues } from "./form";
import { toCheckoutBody } from "./request";

type InitializeBody =
  paths["/api/v1/payments/initialize/"]["post"]["requestBody"]["content"]["application/json"];
type LookupBody =
  paths["/api/v1/orders/lookup/"]["post"]["requestBody"]["content"]["application/json"];
export type { components };

interface Options {
  fetch?: typeof fetch;
}

function bad(status: number): { ok: false; error: ApiError } {
  return { ok: false, error: parseApiError(status, undefined) };
}

export async function startPayment(
  orderReference: string,
  email: string,
  options: Options = {},
): Promise<ApiResult<PaymentStart>> {
  const body: InitializeBody = { order_reference: orderReference, email };
  const result = await apiRequest<unknown>("POST", "/payments/initialize/", { body, ...options });
  if (!result.ok) return result;
  const start = readPaymentStart(result.data);
  return start ? { ok: true, status: result.status, data: start } : bad(result.status);
}

export async function lookupOrder(
  reference: string,
  phone: string,
  options: Options = {},
): Promise<ApiResult<OrderView>> {
  const body: LookupBody = { reference: reference.trim(), phone: phone.trim() };
  const result = await apiRequest<unknown>("POST", "/orders/lookup/", { body, ...options });
  if (!result.ok) return result;
  const order = readOrder(result.data);
  return order ? { ok: true, status: result.status, data: order } : bad(result.status);
}

/** Asks the server to confirm the payment with Paystack. Only the server decides if it is paid. */
export async function verifyPayment(
  paymentReference: string,
  options: Options = {},
): Promise<ApiResult<{ outcome: string | null }>> {
  const result = await apiRequest<unknown>("GET", "/payments/verify/", {
    query: { reference: paymentReference },
    ...options,
  });
  if (!result.ok) return result;
  return { ok: true, status: result.status, data: { outcome: readVerifyOutcome(result.data) } };
}

export type PlaceResult =
  | {
      ok: true;
      order: OrderView;
      /** Where to send the customer to pay, for an online order. */
      paymentUrl: string | null;
      /** Set when the order was placed but the payment page could not be opened. */
      paymentError: ApiError | null;
    }
  | { ok: false; error: ApiError };

/**
 * Places the order, then for an online order asks for the payment page. The same idempotency
 * key must be reused when retrying the same order, so a double tap cannot place it twice.
 */
export async function placeOrder(
  values: CheckoutValues,
  cart: Cart,
  idempotencyKey: string,
  options: Options = {},
): Promise<PlaceResult> {
  const created = await apiRequest<unknown>("POST", "/orders/", {
    body: toCheckoutBody(values, cart),
    idempotencyKey,
    ...options,
  });
  if (!created.ok) return { ok: false, error: created.error };
  const order = readOrder(created.data);
  if (!order) return bad(created.status);

  if (values.payment === "cod") {
    return { ok: true, order, paymentUrl: null, paymentError: null };
  }
  const started = await startPayment(order.reference, values.email, options);
  if (!started.ok) {
    return { ok: true, order, paymentUrl: null, paymentError: started.error };
  }
  return { ok: true, order, paymentUrl: started.data.authorizationUrl, paymentError: null };
}
