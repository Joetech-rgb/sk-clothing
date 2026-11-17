"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { describeError } from "../lib/api/errors";
import { PAID_STATUS } from "../lib/api/orders-temp";
import type { OrderView } from "../lib/api/orders-temp";
import { lookupOrder, verifyPayment } from "../lib/checkout/flow";
import { browserSession, loadLastOrder } from "../lib/orders/session";
import { OrderCard } from "./OrderCard";

const POLLS = 6;
const POLL_MS = 4000;

/**
 * Where Paystack sends the customer back. Coming back proves nothing: this page asks the server
 * to confirm the payment, then shows what the server says about the order.
 */
export function PaymentReturnView() {
  const params = useSearchParams();
  const reference = params.get("reference") ?? params.get("trxref") ?? "";
  const [order, setOrder] = useState<OrderView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [checking, setChecking] = useState(true);

  useEffect(() => {
    let alive = true;
    async function run() {
      if (reference === "") {
        setChecking(false);
        return;
      }
      const verified = await verifyPayment(reference);
      if (alive && !verified.ok) setError(describeError(verified.error));

      const last = loadLastOrder(browserSession());
      if (!last) {
        if (alive) setChecking(false);
        return;
      }
      for (let attempt = 0; attempt < POLLS && alive; attempt++) {
        const result = await lookupOrder(last.reference, last.phone);
        if (!alive) return;
        if (result.ok) {
          setOrder(result.data);
          if (result.data.paymentStatus === PAID_STATUS) break;
        }
        await new Promise((resolve) => setTimeout(resolve, POLL_MS));
      }
      if (alive) setChecking(false);
    }
    void run();
    return () => {
      alive = false;
    };
  }, [reference]);

  const paid = order?.paymentStatus === PAID_STATUS;

  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-2xl font-semibold">Your payment</h1>
      {paid ? (
        <p className="text-ink">Payment received. Thank you!</p>
      ) : checking ? (
        <p className="text-ink-muted">We are confirming your payment. This usually takes under a minute.</p>
      ) : (
        <p className="text-ink-muted">
          We have not confirmed your payment yet. If you paid, it can take a few minutes. You can
          check again by tracking your order.
        </p>
      )}
      {error && (
        <p role="alert" className="text-danger">
          {error}
        </p>
      )}
      {order && <OrderCard order={order} />}
      <Link
        href="/orders"
        className="inline-flex min-h-11 items-center self-start rounded-control border border-line px-4 text-ink hover:bg-surface-muted"
      >
        Track your order
      </Link>
    </div>
  );
}
