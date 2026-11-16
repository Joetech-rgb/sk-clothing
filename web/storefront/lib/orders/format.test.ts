import { describe, expect, it } from "vitest";
import { humanize } from "./format";

describe("humanize", () => {
  it.each([
    ["awaiting_payment", "Awaiting payment"],
    ["paid", "Paid"],
    ["", ""],
    ["  out_for_delivery ", "Out for delivery"],
  ])("turns %j into %j", (input, expected) => {
    expect(humanize(input)).toBe(expected);
  });
});
