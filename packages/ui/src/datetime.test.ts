import { describe, expect, it } from "vitest";
import { formatAccraDateTime } from "./datetime";

describe("formatAccraDateTime", () => {
  it("shows the same moment identically whatever offset the input uses", () => {
    const utc = formatAccraDateTime("2026-11-03T10:11:00Z");
    const plusTwo = formatAccraDateTime("2026-11-03T12:11:00+02:00");
    expect(plusTwo).toBe(utc);
  });

  it("uses Accra time (UTC+0), not the device zone", () => {
    const text = formatAccraDateTime("2026-11-03T10:11:00Z");
    expect(text).toContain("2026");
    expect(text).toContain("10:11");
  });

  it("rejects an invalid date", () => {
    expect(() => formatAccraDateTime("not a date")).toThrow(RangeError);
  });
});
