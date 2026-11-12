import { describe, expect, it } from "vitest";
import type { Cart } from "../cart/cart";
import type { CheckoutValues } from "./form";
import { quoteRequestFor, toCheckoutBody } from "./request";

const cart: Cart = [
  { productSlug: "tee", variantId: 1, quantity: 2 },
  { productSlug: "tee", variantId: 2, quantity: 3 },
];

const base = { name: "Ama", phone: "0240000000", email: "ama@example.com" };

describe("toCheckoutBody", () => {
  it("sends ids and quantities and the contact details for pickup", () => {
    const values: CheckoutValues = { method: "pickup", payment: "online", ...base };
    expect(toCheckoutBody(values, cart)).toEqual({
      items: [
        { variant_id: 1, quantity: 2 },
        { variant_id: 2, quantity: 3 },
      ],
      delivery: { method: "pickup" },
      contact_name: "Ama",
      contact_phone: "0240000000",
      payment_method: "online",
    });
  });

  it("sends the station name for station delivery", () => {
    const values: CheckoutValues = {
      method: "station",
      payment: "online",
      stationName: "Madina",
      ...base,
    };
    expect(toCheckoutBody(values, cart).delivery).toEqual({
      method: "station",
      station_name: "Madina",
    });
  });

  it("sends the address and coordinates for doorstep delivery and cod as chosen", () => {
    const values: CheckoutValues = {
      method: "doorstep",
      payment: "cod",
      address: "12 Palm St",
      latitude: 5.6,
      longitude: -0.18,
      ...base,
    };
    const body = toCheckoutBody(values, cart);
    expect(body.delivery).toEqual({
      method: "doorstep",
      address: "12 Palm St",
      latitude: 5.6,
      longitude: -0.18,
    });
    expect(body.payment_method).toBe("cod");
  });

  it("never carries a price, a fee, an email or other extra fields", () => {
    const values: CheckoutValues = { method: "pickup", payment: "online", ...base };
    const body = toCheckoutBody(values, cart);
    expect(Object.keys(body).sort()).toEqual([
      "contact_name",
      "contact_phone",
      "delivery",
      "items",
      "payment_method",
    ]);
    for (const item of body.items) {
      expect(Object.keys(item).sort()).toEqual(["quantity", "variant_id"]);
    }
  });
});

describe("quoteRequestFor", () => {
  it("can always ask for a pickup quote", () => {
    expect(quoteRequestFor({ method: "pickup", stationName: "", pin: null })).toEqual({
      method: "pickup",
    });
  });

  it("waits for a station name", () => {
    expect(quoteRequestFor({ method: "station", stationName: "  ", pin: null })).toBeNull();
    expect(quoteRequestFor({ method: "station", stationName: " Madina ", pin: null })).toEqual({
      method: "station",
      station_name: "Madina",
    });
  });

  it("waits for a pinned location for doorstep", () => {
    expect(quoteRequestFor({ method: "doorstep", stationName: "", pin: null })).toBeNull();
    expect(
      quoteRequestFor({
        method: "doorstep",
        stationName: "",
        pin: { latitude: 5.6, longitude: -0.18 },
      }),
    ).toEqual({ method: "doorstep", latitude: 5.6, longitude: -0.18 });
  });
});
