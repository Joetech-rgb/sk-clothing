"use client";

import { useState } from "react";
import { Button, Input } from "@sk/ui";
import { describeError } from "../lib/api/errors";
import type { OrderView } from "../lib/api/orders-temp";
import { lookupOrder } from "../lib/checkout/flow";
import { OrderCard } from "./OrderCard";

/** Track an order by its reference and the phone number it was placed with. */
export function TrackView() {
  const [reference, setReference] = useState("");
  const [phone, setPhone] = useState("");
  const [order, setOrder] = useState<OrderView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function find(event: React.SyntheticEvent<HTMLFormElement>) {
    event.preventDefault();
    if (reference.trim() === "" || phone.trim() === "") {
      setError("Enter your order reference and the phone number you ordered with.");
      return;
    }
    setBusy(true);
    setError(null);
    const result = await lookupOrder(reference, phone);
    setBusy(false);
    if (result.ok) {
      setOrder(result.data);
    } else {
      setOrder(null);
      setError(describeError(result.error));
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-2xl font-semibold">Track your order</h1>
      <form onSubmit={find} noValidate className="flex flex-col gap-3">
        <Input label="Order reference" value={reference} onChange={(e) => setReference(e.target.value)} />
        <Input
          label="Phone number"
          type="tel"
          inputMode="tel"
          autoComplete="tel"
          value={phone}
          onChange={(e) => setPhone(e.target.value)}
        />
        {error && (
          <p role="alert" className="text-danger">
            {error}
          </p>
        )}
        <Button type="submit" disabled={busy}>
          {busy ? "Please wait" : "Find my order"}
        </Button>
      </form>
      {order && <OrderCard order={order} />}
    </div>
  );
}
