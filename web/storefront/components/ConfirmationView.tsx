"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { describeError } from "../lib/api/errors";
import type { OrderView } from "../lib/api/orders-temp";
import { lookupOrder } from "../lib/checkout/flow";
import { canPayOnline } from "../lib/orders/pay";
import { browserSession, loadLastOrder } from "../lib/orders/session";
import type { LastOrder } from "../lib/orders/session";
import { OrderCard } from "./OrderCard";
import { PayNowPanel } from "./PayNowPanel";

/** Shown right after an order is placed. */
export function ConfirmationView() {
  const [last, setLast] = useState<LastOrder | null | undefined>(undefined);
  const [order, setOrder] = useState<OrderView | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLast(loadLastOrder(browserSession()));
  }, []);

  useEffect(() => {
    if (!last) return;
    let alive = true;
    void lookupOrder(last.reference, last.phone).then((result) => {
      if (!alive) return;
      if (result.ok) setOrder(result.data);
      else setError(describeError(result.error));
    });
    return () => {
      alive = false;
    };
  }, [last]);

  if (last === undefined) return <p className="text-ink-muted">Loading your order.</p>;

  if (last === null) {
    return (
      <div className="flex flex-col gap-3">
        <h1 className="text-2xl font-semibold">Your order</h1>
        <p className="text-ink-muted">
          We could not find your recent order on this device. You can look it up with its reference
          and your phone number.
        </p>
        <Link
          href="/orders"
          className="inline-flex min-h-11 items-center self-start rounded-control border border-line px-4 text-ink hover:bg-surface-muted"
        >
          Track your order
        </Link>
      </div>
    );
  }

  const showPay = last.payment === "online" && order !== null && canPayOnline(order);

  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-2xl font-semibold">Thank you for your order</h1>
      <p className="text-ink-muted">
        {last.payment === "cod"
          ? "We will call you to confirm your order before we pack it. Keep your order reference."
          : "Your order is placed. Keep your order reference."}
      </p>
      {error && (
        <p role="alert" className="text-danger">
          {error}
        </p>
      )}
      {order && <OrderCard order={order} />}
      {showPay && order && <PayNowPanel order={order} phone={last.phone} email={last.email} />}
      <Link
        href="/orders"
        className="inline-flex min-h-11 items-center self-start rounded-control border border-line px-4 text-ink hover:bg-surface-muted"
      >
        Track this order later
      </Link>
    </div>
  );
}
