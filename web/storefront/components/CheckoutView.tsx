"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { Card } from "@sk/ui";
import { listStations, priceCart, quoteDelivery } from "../lib/api/endpoints";
import { describeError } from "../lib/api/errors";
import { newIdempotencyKey } from "../lib/api/idempotency";
import { toPriceItems } from "../lib/cart/pricing";
import { useCart } from "../lib/cart/use-cart";
import { placeOrder } from "../lib/checkout/flow";
import type { CheckoutValues } from "../lib/checkout/form";
import { describeQuote } from "../lib/checkout/quote";
import { quoteRequestFor, toCheckoutBody } from "../lib/checkout/request";
import type { DeliverySelection } from "../lib/checkout/request";
import { checkoutErrors } from "../lib/checkout/server-errors";
import type { CheckoutErrors } from "../lib/checkout/server-errors";
import { browserSession, saveLastOrder } from "../lib/orders/session";
import { CheckoutForm } from "./CheckoutForm";
import type { StationOption } from "./CheckoutForm";
import { DoorstepLocationPicker, MAP_CONFIGURED } from "./DoorstepLocationPicker";

interface QuoteState {
  text: string;
  codAllowed: boolean;
}

/**
 * The checkout page. Prices, the delivery fee and whether pay on delivery is allowed all come
 * from the server. The browser sends ids, quantities and what the customer typed.
 */
export function CheckoutView() {
  const router = useRouter();
  const { cart, clear } = useCart();
  const [mounted, setMounted] = useState(false);
  const [stations, setStations] = useState<StationOption[]>([]);
  const [subtotal, setSubtotal] = useState<string | null>(null);
  const [selection, setSelection] = useState<DeliverySelection | null>(null);
  const [quote, setQuote] = useState<QuoteState | null>(null);
  const [quoteError, setQuoteError] = useState<string | null>(null);
  const [problem, setProblem] = useState<CheckoutErrors | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);
  const attempt = useRef<{ body: string; key: string } | null>(null);

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    let alive = true;
    void listStations().then((result) => {
      if (alive && result.ok) {
        setStations(result.data.map((s) => ({ name: s.name, feeDisplay: s.fee.display })));
      }
    });
    return () => {
      alive = false;
    };
  }, []);

  useEffect(() => {
    if (cart.length === 0) {
      setSubtotal(null);
      return;
    }
    setSubtotal(null);
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      const result = await priceCart(toPriceItems(cart), { signal: controller.signal });
      if (controller.signal.aborted) return;
      setSubtotal(result.ok ? result.data.subtotal.display : null);
    }, 300);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [cart]);

  useEffect(() => {
    setQuote(null);
    setQuoteError(null);
    const request = selection ? quoteRequestFor(selection) : null;
    if (!request) return;
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      const result = await quoteDelivery(request, { signal: controller.signal });
      if (controller.signal.aborted) return;
      if (result.ok) {
        setQuote({ text: describeQuote(result.data).text, codAllowed: result.data.cod_allowed });
      } else {
        setQuoteError(describeError(result.error));
      }
    }, 300);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [selection]);

  async function submit(values: CheckoutValues) {
    setSubmitting(true);
    setProblem(null);

    // The same key is reused while the order is unchanged, so a double tap or a retry cannot
    // place it twice. A changed order gets a new key.
    const body = JSON.stringify(toCheckoutBody(values, cart));
    if (!attempt.current || attempt.current.body !== body) {
      attempt.current = { body, key: newIdempotencyKey() };
    }
    const result = await placeOrder(values, cart, attempt.current.key);

    if (!result.ok) {
      setProblem(checkoutErrors(result.error));
      setSubmitting(false);
      return;
    }
    saveLastOrder(browserSession(), {
      reference: result.order.reference,
      phone: values.phone,
      email: values.email,
      payment: values.payment,
    });
    setDone(true);
    clear();
    if (result.paymentUrl) {
      window.location.assign(result.paymentUrl);
    } else {
      router.push("/orders/confirmation");
    }
  }

  if (!mounted) return <p className="text-ink-muted">Loading checkout.</p>;

  if (done) return <p className="text-ink">Placing your order. Please wait.</p>;

  if (cart.length === 0) {
    return (
      <div className="flex flex-col gap-3">
        <h1 className="text-2xl font-semibold">Checkout</h1>
        <p className="text-ink-muted">Your cart is empty.</p>
        <Link
          href="/products"
          className="inline-flex min-h-11 items-center self-start rounded-control border border-line px-4 text-ink hover:bg-surface-muted"
        >
          Browse products
        </Link>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-2xl font-semibold">Checkout</h1>
      <Card>
        <div className="flex items-baseline justify-between gap-3">
          <span className="text-ink">Subtotal</span>
          <span className="font-semibold tabular-nums text-ink">{subtotal ?? "Checking prices"}</span>
        </div>
        <p className="mt-2 text-sm text-ink-muted">
          Delivery is shown once you choose how to get your order. The total is confirmed when you
          place the order.
        </p>
      </Card>
      <CheckoutForm
        stations={stations}
        codAllowed={quote?.codAllowed ?? false}
        doorstepAvailable={MAP_CONFIGURED}
        renderLocationPicker={(props) => <DoorstepLocationPicker {...props} />}
        onDeliveryChange={setSelection}
        deliveryNote={quote?.text ?? quoteError ?? undefined}
        submitting={submitting}
        serverError={problem?.general ?? undefined}
        serverFieldErrors={problem?.fields}
        onSubmit={submit}
      />
    </div>
  );
}
