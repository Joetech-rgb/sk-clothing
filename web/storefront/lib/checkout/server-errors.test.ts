import { describe, expect, it } from "vitest";
import { parseApiError } from "../api/errors";
import { checkoutErrors } from "./server-errors";

function validation(details: unknown) {
  return parseApiError(400, {
    error: { code: "validation_error", message: "The request was not valid.", details },
  });
}

describe("checkoutErrors", () => {
  it("puts each message beside its form field", () => {
    const result = checkoutErrors(
      validation({
        contact_name: ["This field may not be blank."],
        contact_phone: ["Enter a valid Ghana phone number."],
        delivery: {
          station_name: ["Choose a station."],
          address: ["Enter the delivery address."],
          latitude: ["Pin the delivery location on the map."],
        },
      }),
    );
    expect(result.fields).toEqual({
      name: "This field may not be blank.",
      phone: "Enter a valid Ghana phone number.",
      station: "Choose a station.",
      address: "Enter the delivery address.",
      location: "Pin the delivery location on the map.",
    });
    expect(result.general).toBeNull();
  });

  it("uses the first message when a field has several", () => {
    const result = checkoutErrors(validation({ contact_phone: ["First.", "Second."] }));
    expect(result.fields.phone).toBe("First.");
  });

  it("shows messages that belong to no form field at the top", () => {
    const result = checkoutErrors(validation({ items: "At most 1000 of one item." }));
    expect(result.fields).toEqual({});
    expect(result.general).toBe("At most 1000 of one item.");
  });

  it("falls back to the envelope message when validation gives no usable details", () => {
    const result = checkoutErrors(validation({}));
    expect(result.general).toBe("The request was not valid.");
  });

  it("shows other errors, such as an out-of-stock refusal, at the top", () => {
    const error = parseApiError(409, {
      error: {
        code: "insufficient_stock",
        message: "There is not enough stock for one of the items.",
        details: { reason: "insufficient_stock", variant_id: 7, available: 2 },
      },
    });
    expect(checkoutErrors(error)).toEqual({
      fields: {},
      general: "There is not enough stock for one of the items.",
    });
  });

  it("shows a network failure at the top", () => {
    const error = parseApiError(0, null);
    expect(checkoutErrors(error).general).toBe("Something went wrong. Please try again.");
  });
});
