import { PAID_STATUS } from "../api/orders-temp";
import type { OrderView } from "../api/orders-temp";

/**
 * True while the server has not yet worked out the total (a quoted delivery fee is pending).
 * Display logic only: the server decides everything else.
 */
export function awaitingQuote(order: OrderView): boolean {
  return order.totalDisplay === null && order.paymentStatus !== PAID_STATUS;
}

/**
 * Whether to offer "Pay now": the server has a total and the order is not paid yet. If the server
 * refuses the payment (for example the order is cancelled), its message is shown instead.
 * A clearer flag from the backend ("payable") has been requested.
 */
export function canPayOnline(order: OrderView): boolean {
  return order.totalDisplay !== null && order.paymentStatus !== PAID_STATUS;
}
