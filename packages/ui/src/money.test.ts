import { describe, expect, it } from "vitest";
import { formatGhs } from "./money";

describe("formatGhs", () => {
  it.each([
    [0, "GHS 0.00"],
    [1, "GHS 0.01"],
    [9, "GHS 0.09"],
    [99, "GHS 0.99"],
    [100, "GHS 1.00"],
    [5000, "GHS 50.00"],
    [123456, "GHS 1,234.56"],
    [100000000, "GHS 1,000,000.00"],
    [-2550, "-GHS 25.50"],
    [Number.MAX_SAFE_INTEGER, "GHS 90,071,992,547,409.91"],
  ])("formats %i pesewas as %s", (input, expected) => {
    expect(formatGhs(input)).toBe(expected);
  });

  it.each([10.5, Number.NaN, Infinity, Number.MAX_SAFE_INTEGER + 1])(
    "rejects %s (not a safe whole number)",
    (input) => {
      expect(() => formatGhs(input)).toThrow(RangeError);
    },
  );
});
