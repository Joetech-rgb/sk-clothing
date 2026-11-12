import { describe, expect, it } from "vitest";
import {
  GENERIC_MESSAGE,
  NETWORK_MESSAGE,
  NON_FIELD,
  describeError,
  networkError,
  parseApiError,
} from "./errors";

function envelope(code: string, message: string, extra: Record<string, unknown> = {}) {
  return { error: { code, message, ...extra } };
}

describe("parseApiError", () => {
  it("reads code, message and request id", () => {
    const error = parseApiError(404, envelope("not_found", "Not found.", { request_id: "abc" }));
    expect(error).toMatchObject({
      status: 404,
      code: "not_found",
      message: "Not found.",
      requestId: "abc",
      reason: null,
      fields: {},
    });
  });

  it("reads the stable reason and extra details of a refusal", () => {
    const error = parseApiError(
      409,
      envelope("insufficient_stock", "There is not enough stock for one of the items.", {
        details: { reason: "insufficient_stock", variant_id: 7, available: 2 },
      }),
    );
    expect(error.reason).toBe("insufficient_stock");
    expect(error.details).toMatchObject({ variant_id: 7, available: 2 });
  });

  it("flattens validation errors by field", () => {
    const error = parseApiError(
      400,
      envelope("validation_error", "The request was not valid.", {
        details: {
          contact_phone: ["Enter a valid Ghana phone number."],
          delivery: { latitude: ["Pin the delivery location on the map."] },
          items: [{}, { quantity: ["Ensure this value is less than or equal to 1000."] }],
        },
      }),
    );
    expect(error.fields).toEqual({
      contact_phone: ["Enter a valid Ghana phone number."],
      "delivery.latitude": ["Pin the delivery location on the map."],
      "items.1.quantity": ["Ensure this value is less than or equal to 1000."],
    });
  });

  it("keeps a plain message under a field", () => {
    const error = parseApiError(
      400,
      envelope("validation_error", "The request was not valid.", {
        details: { delivery: "That station is not served." },
      }),
    );
    expect(error.fields).toEqual({ delivery: ["That station is not served."] });
  });

  it("puts messages with no field under the non-field key", () => {
    const error = parseApiError(
      400,
      envelope("validation_error", "The request was not valid.", { details: ["Not allowed."] }),
    );
    expect(error.fields).toEqual({ [NON_FIELD]: ["Not allowed."] });
  });

  it("reads the retry wait of a throttled response", () => {
    const error = parseApiError(
      429,
      envelope("throttled", "Request was throttled.", { details: { retry_after_seconds: 31 } }),
    );
    expect(error.retryAfterSeconds).toBe(31);
  });

  it.each([
    ["an HTML page", "<html>Bad gateway</html>"],
    ["null", null],
    ["a list", [1, 2]],
    ["an error without a code", { error: { message: "x" } }],
    ["an error without a message", { error: { code: "x" } }],
    ["a string error", { error: "nope" }],
  ])("falls back safely for %s", (_label, body) => {
    const error = parseApiError(502, body);
    expect(error).toMatchObject({
      status: 502,
      code: "unexpected_response",
      message: GENERIC_MESSAGE,
      fields: {},
    });
  });
});

describe("networkError and describeError", () => {
  it("describes a failure with no response", () => {
    const error = networkError();
    expect(error).toMatchObject({ status: 0, code: "network_error", message: NETWORK_MESSAGE });
  });

  it("shows the server's message as it is", () => {
    const error = parseApiError(404, envelope("order_not_found", "We could not find that order."));
    expect(describeError(error)).toBe("We could not find that order.");
  });

  it("rewrites a throttled wait into plain words, rounding up", () => {
    const error = parseApiError(
      429,
      envelope("throttled", "Request was throttled.", { details: { retry_after_seconds: 30 } }),
    );
    expect(describeError(error)).toBe("Too many tries. Please wait 30 seconds and try again.");
  });

  it("keeps the server message for a throttled response with no wait time", () => {
    const error = parseApiError(429, envelope("throttled", "Too many wrong codes. Ask for a new code."));
    expect(describeError(error)).toBe("Too many wrong codes. Ask for a new code.");
  });
});
