import { describe, expect, it } from "vitest";
import { readOrder, readPaymentStart, readVerifyOutcome } from "./orders-temp";

const money = (pesewas: number) => ({ pesewas, display: `GHS ${(pesewas / 100).toFixed(2)}` });

const order = {
  reference: "SK-1234",
  payment_status: "unpaid",
  fulfilment_status: "placed",
  refund_status: "none",
  pickup: false,
  delivery_method: "station",
  subtotal: money(3000),
  delivery_fee: money(2000),
  total: money(5000),
  lines: [
    {
      variant_id: 7,
      name: "Cotton tee",
      quantity: 3,
      tier: "retail",
      unit_price: money(1000),
      line_total: money(3000),
    },
  ],
  created_at: "2026-11-12T10:00:00Z",
  replayed: false,
  stock_held_until: "2026-11-12T10:15:00Z",
};

describe("readOrder", () => {
  it("reads what the customer screens need, using the server's price text", () => {
    expect(readOrder(order)).toEqual({
      reference: "SK-1234",
      paymentStatus: "unpaid",
      fulfilmentStatus: "placed",
      refundStatus: "none",
      deliveryMethod: "station",
      subtotalDisplay: "GHS 30.00",
      deliveryFeeDisplay: "GHS 20.00",
      totalDisplay: "GHS 50.00",
      lines: [{ name: "Cotton tee", quantity: 3, lineTotalDisplay: "GHS 30.00" }],
      deliveryCode: null,
    });
  });

  it("keeps a missing fee and total as null (awaiting a quote)", () => {
    const view = readOrder({ ...order, delivery_fee: null, total: null });
    expect(view?.deliveryFeeDisplay).toBeNull();
    expect(view?.totalDisplay).toBeNull();
  });

  it("reads a delivery code when the backend sends one", () => {
    expect(readOrder({ ...order, delivery_code: "123456" })?.deliveryCode).toBe("123456");
  });

  it("skips malformed lines but keeps good ones", () => {
    const view = readOrder({ ...order, lines: [{ name: 1 }, order.lines[0], "junk"] });
    expect(view?.lines).toHaveLength(1);
  });

  it.each([
    ["null", null],
    ["a list", []],
    ["a string", "x"],
    ["no reference", { ...order, reference: "" }],
    ["no payment status", { ...order, payment_status: undefined }],
    ["no subtotal", { ...order, subtotal: null }],
  ])("returns null for %s", (_label, data) => {
    expect(readOrder(data)).toBeNull();
  });
});

describe("readPaymentStart", () => {
  it("reads the payment page address and reference", () => {
    expect(
      readPaymentStart({ authorization_url: "https://checkout.paystack.com/abc", reference: "r1" }),
    ).toEqual({ authorizationUrl: "https://checkout.paystack.com/abc", reference: "r1" });
  });

  it("refuses an address that is not secure", () => {
    expect(readPaymentStart({ authorization_url: "http://evil.example", reference: "r1" })).toBeNull();
    expect(readPaymentStart({ authorization_url: "javascript:alert(1)", reference: "r1" })).toBeNull();
  });

  it("refuses an incomplete reply", () => {
    expect(readPaymentStart({ authorization_url: "https://x.example" })).toBeNull();
    expect(readPaymentStart(null)).toBeNull();
  });
});

describe("readVerifyOutcome", () => {
  it("reads the outcome word", () => {
    expect(readVerifyOutcome({ outcome: "confirmed", reference: "SK-1" })).toBe("confirmed");
  });

  it("returns null when there is none", () => {
    expect(readVerifyOutcome({})).toBeNull();
    expect(readVerifyOutcome(null)).toBeNull();
  });
});
