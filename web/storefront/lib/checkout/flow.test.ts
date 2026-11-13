import { describe, expect, it } from "vitest";
import type { Cart } from "../cart/cart";
import type { CheckoutValues } from "./form";
import { lookupOrder, placeOrder, startPayment, verifyPayment } from "./flow";

interface Call {
  method: string;
  url: string;
  body: unknown;
  idempotencyKey: string | undefined;
}

function server(routes: Record<string, () => Response>) {
  const calls: Call[] = [];
  const impl = ((url: string, init: RequestInit & { headers: Record<string, string> }) => {
    const route = `${init.method} ${url}`;
    calls.push({
      method: String(init.method),
      url,
      body: init.body ? JSON.parse(String(init.body)) : undefined,
      idempotencyKey: init.headers["Idempotency-Key"],
    });
    const handler = routes[route];
    return Promise.resolve(handler ? handler() : new Response("{}", { status: 404 }));
  }) as unknown as typeof fetch;
  return { fetch: impl, calls };
}

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const money = (p: number) => ({ pesewas: p, display: `GHS ${(p / 100).toFixed(2)}` });

const orderJson = {
  reference: "SK-1",
  payment_status: "unpaid",
  fulfilment_status: "placed",
  refund_status: "none",
  delivery_method: "pickup",
  subtotal: money(1000),
  delivery_fee: money(0),
  total: money(1000),
  lines: [],
};

const cart: Cart = [{ productSlug: "tee", variantId: 1, quantity: 1 }];
const pickup = (payment: "online" | "cod"): CheckoutValues => ({
  method: "pickup",
  name: "Ama",
  phone: "0240000000",
  email: "ama@example.com",
  payment,
});

describe("placeOrder", () => {
  it("places a pay-on-delivery order and does not start a payment", async () => {
    const s = server({ "POST /api/v1/orders/": () => json(orderJson, 201) });
    const result = await placeOrder(pickup("cod"), cart, "key-12345678", { fetch: s.fetch });
    expect(result).toMatchObject({ ok: true, paymentUrl: null, paymentError: null });
    expect(s.calls).toHaveLength(1);
    expect(s.calls[0]?.idempotencyKey).toBe("key-12345678");
  });

  it("starts the payment for an online order with the order reference and email", async () => {
    const s = server({
      "POST /api/v1/orders/": () => json(orderJson, 201),
      "POST /api/v1/payments/initialize/": () =>
        json({ authorization_url: "https://checkout.paystack.com/x", reference: "PAY-1" }),
    });
    const result = await placeOrder(pickup("online"), cart, "key-12345678", { fetch: s.fetch });
    expect(result).toMatchObject({ ok: true, paymentUrl: "https://checkout.paystack.com/x" });
    expect(s.calls[1]?.body).toEqual({ order_reference: "SK-1", email: "ama@example.com" });
  });

  it("keeps the order when the payment page cannot be opened", async () => {
    const s = server({
      "POST /api/v1/orders/": () => json(orderJson, 201),
      "POST /api/v1/payments/initialize/": () =>
        json({ error: { code: "payment_unavailable", message: "Try again shortly." } }, 503),
    });
    const result = await placeOrder(pickup("online"), cart, "key-12345678", { fetch: s.fetch });
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.paymentUrl).toBeNull();
      expect(result.paymentError?.code).toBe("payment_unavailable");
    }
  });

  it("reports a refused order with the server's error", async () => {
    const s = server({
      "POST /api/v1/orders/": () =>
        json({ error: { code: "insufficient_stock", message: "Not enough stock." } }, 409),
    });
    const result = await placeOrder(pickup("cod"), cart, "key-12345678", { fetch: s.fetch });
    expect(result).toMatchObject({ ok: false, error: { code: "insufficient_stock" } });
  });

  it("reports a reply it cannot read instead of guessing", async () => {
    const s = server({ "POST /api/v1/orders/": () => json({ hello: "world" }, 201) });
    const result = await placeOrder(pickup("cod"), cart, "key-12345678", { fetch: s.fetch });
    expect(result).toMatchObject({ ok: false, error: { code: "unexpected_response" } });
  });
});

describe("startPayment, lookupOrder and verifyPayment", () => {
  it("refuses a payment address that is not secure", async () => {
    const s = server({
      "POST /api/v1/payments/initialize/": () =>
        json({ authorization_url: "http://insecure.example", reference: "P" }),
    });
    const result = await startPayment("SK-1", "a@b.co", { fetch: s.fetch });
    expect(result.ok).toBe(false);
  });

  it("looks an order up by reference and phone", async () => {
    const s = server({ "POST /api/v1/orders/lookup/": () => json(orderJson) });
    const result = await lookupOrder(" SK-1 ", " 0240000000 ", { fetch: s.fetch });
    expect(result).toMatchObject({ ok: true, data: { reference: "SK-1" } });
    expect(s.calls[0]?.body).toEqual({ reference: "SK-1", phone: "0240000000" });
  });

  it("shows the server's message when an order is not found", async () => {
    const s = server({
      "POST /api/v1/orders/lookup/": () =>
        json({ error: { code: "order_not_found", message: "We could not find that order." } }, 404),
    });
    const result = await lookupOrder("X", "Y", { fetch: s.fetch });
    expect(result).toMatchObject({ ok: false, error: { message: "We could not find that order." } });
  });

  it("asks the server to verify a payment by its reference", async () => {
    const s = server({
      "GET /api/v1/payments/verify/?reference=PAY-1": () => json({ outcome: "confirmed" }),
    });
    const result = await verifyPayment("PAY-1", { fetch: s.fetch });
    expect(result).toEqual({ ok: true, status: 200, data: { outcome: "confirmed" } });
  });
});
