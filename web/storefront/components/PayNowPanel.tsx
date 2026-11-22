"use client";

import { useState } from "react";
import { Button, Input } from "@sk/ui";
import { describeError } from "../lib/api/errors";
import type { OrderView } from "../lib/api/orders-temp";
import { startPayment } from "../lib/checkout/flow";
import { browserSession, saveLastOrder } from "../lib/orders/session";

/**
 * Pay for an order that is ready to pay. It uses the same payment call as checkout, and Paystack
 * returns the customer to /payment/return, which asks the server whether it was paid.
 */
export function PayNowPanel({
  order,
  phone,
  email = "",
}: {
  order: OrderView;
  /** The phone number used to find the order; the return page needs it to look the order up. */
  phone: string;
  /** Already known (just after checkout): the email field is hidden. */
  email?: string;
}) {
  const [emailValue, setEmailValue] = useState(email);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function pay() {
    const trimmed = emailValue.trim();
    if (trimmed === "") {
      setError("Enter your email address.");
      return;
    }
    setBusy(true);
    setError(null);
    const result = await startPayment(order.reference, trimmed);
    if (!result.ok) {
      setError(describeError(result.error));
      setBusy(false);
      return;
    }
    saveLastOrder(browserSession(), {
      reference: order.reference,
      phone,
      email: trimmed,
      payment: "online",
    });
    window.location.assign(result.data.authorizationUrl);
  }

  return (
    <div className="flex flex-col gap-3">
      {email === "" && (
        <Input
          label="Email address"
          type="email"
          inputMode="email"
          autoComplete="email"
          value={emailValue}
          onChange={(e) => setEmailValue(e.target.value)}
        />
      )}
      {error && (
        <p role="alert" className="text-danger">
          {error}
        </p>
      )}
      <Button fullWidth disabled={busy} onClick={pay}>
        {busy ? "Please wait" : "Pay now"}
      </Button>
    </div>
  );
}
