import { describe, expect, it } from "vitest";
import type { OrderView } from "../api/orders-temp";
import { awaitingQuote, canPayOnline } from "./pay";

const order = (overrides: Partial<OrderView>): OrderView => ({
  reference: "SK-1",
  paymentStatus: "unpaid",
  fulfilmentStatus: "placed",
  refundStatus: "none",
  deliveryMethod: "station",
  subtotalDisplay: "GHS 30.00",
  deliveryFeeDisplay: "GHS 20.00",
  totalDisplay: "GHS 50.00",
  lines: [],
  deliveryCode: null,
  ...overrides,
});

describe("canPayOnline", () => {
  it("offers Pay now for an unpaid order with a total", () => {
    expect(canPayOnline(order({}))).toBe(true);
  });

  it("does not offer it once the order is paid", () => {
    expect(canPayOnline(order({ paymentStatus: "paid" }))).toBe(false);
  });

  it("does not offer it while the total is still being worked out", () => {
    expect(canPayOnline(order({ totalDisplay: null, deliveryFeeDisplay: null }))).toBe(false);
  });
});

describe("awaitingQuote", () => {
  it("is true when the server has not set the total yet", () => {
    expect(awaitingQuote(order({ totalDisplay: null, deliveryFeeDisplay: null }))).toBe(true);
  });

  it("is false once there is a total", () => {
    expect(awaitingQuote(order({}))).toBe(false);
  });

  it("is false for a paid order", () => {
    expect(awaitingQuote(order({ paymentStatus: "paid", totalDisplay: null }))).toBe(false);
  });
});
