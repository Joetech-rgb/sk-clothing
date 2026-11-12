import type { components } from "@sk/api-client";
import type { Cart } from "../cart/cart";
import type { CheckoutValues, DeliveryMethod } from "./form";

type Schemas = components["schemas"];

/** What the customer has chosen for delivery so far. Used to ask the server for a quote. */
export interface DeliverySelection {
  method: DeliveryMethod;
  stationName: string;
  pin: { latitude: number; longitude: number } | null;
}

/**
 * The body of POST /api/v1/orders/. It carries ids, quantities and what the customer typed.
 * It never carries a price or a fee: the server works those out.
 * The email is not part of the order; it goes to the payment step.
 */
export function toCheckoutBody(values: CheckoutValues, cart: Cart): Schemas["Checkout"] {
  const items = cart.map((line) => ({ variant_id: line.variantId, quantity: line.quantity }));
  const common = {
    items,
    contact_name: values.name,
    contact_phone: values.phone,
    payment_method: values.payment,
  };
  switch (values.method) {
    case "pickup":
      return { ...common, delivery: { method: "pickup" } };
    case "station":
      return {
        ...common,
        delivery: { method: "station", station_name: values.stationName },
      };
    case "doorstep":
      return {
        ...common,
        delivery: {
          method: "doorstep",
          address: values.address,
          latitude: values.latitude,
          longitude: values.longitude,
        },
      };
  }
}

/** The quote request for the current choice, or null until it is complete enough to ask. */
export function quoteRequestFor(selection: DeliverySelection): Schemas["QuoteRequest"] | null {
  switch (selection.method) {
    case "pickup":
      return { method: "pickup" };
    case "station":
      return selection.stationName.trim() === ""
        ? null
        : { method: "station", station_name: selection.stationName.trim() };
    case "doorstep":
      return selection.pin === null
        ? null
        : {
            method: "doorstep",
            latitude: selection.pin.latitude,
            longitude: selection.pin.longitude,
          };
  }
}
