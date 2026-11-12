import type { components } from "@sk/api-client";
import { describe, expect, it } from "vitest";
import { describeQuote } from "./quote";

type Quote = components["schemas"]["QuoteResponse"];

const quote = (overrides: Partial<Quote>): Quote => ({
  method: "station",
  status: "priced",
  fee: { pesewas: 2000, display: "GHS 20.00" },
  cod_allowed: false,
  reason: null,
  road_km: null,
  ...overrides,
});

describe("describeQuote", () => {
  it("shows the server's fee text for a priced delivery", () => {
    expect(describeQuote(quote({}))).toEqual({ kind: "priced", text: "Delivery: GHS 20.00" });
  });

  it("says pickup is free", () => {
    const result = describeQuote(
      quote({ method: "pickup", fee: { pesewas: 0, display: "GHS 0.00" } }),
    );
    expect(result).toEqual({ kind: "free", text: "Pickup: free" });
  });

  it("promises a confirmed fee when the server is awaiting a quote", () => {
    const result = describeQuote(
      quote({ status: "awaiting_quote", fee: null, reason: "unlisted_station" }),
    );
    expect(result.kind).toBe("awaiting");
    expect(result.text).toBe("We will confirm the delivery fee before you pay.");
  });

  it("treats a priced status with no fee as awaiting", () => {
    expect(describeQuote(quote({ fee: null })).kind).toBe("awaiting");
  });
});
