import { describe, expect, it } from "vitest";
import {
  EMPTY_FILTERS,
  activeFilterCount,
  hasFilters,
  parseFilterParams,
  productsHrefWithFilters,
} from "./filters";

describe("parseFilterParams", () => {
  it("reads repeated sizes and colours", () => {
    expect(parseFilterParams({ size: ["M", "L"], colour: "Red" })).toEqual({
      sizes: ["M", "L"],
      colours: ["Red"],
    });
  });

  it("drops blanks, repeats and very long values", () => {
    const result = parseFilterParams({ size: ["M", " M ", "", "x".repeat(51)] });
    expect(result.sizes).toEqual(["M"]);
  });

  it("keeps at most twenty choices", () => {
    const many = Array.from({ length: 40 }, (_, i) => `S${i}`);
    expect(parseFilterParams({ size: many }).sizes).toHaveLength(20);
  });

  it("reads whole-cedi prices and drops anything else", () => {
    expect(parseFilterParams({ price_min: "50", price_max: " 200 " })).toMatchObject({
      priceMin: 50,
      priceMax: 200,
    });
    expect(parseFilterParams({ price_min: "-5", price_max: "10.5" })).toEqual(EMPTY_FILTERS);
    expect(parseFilterParams({ price_min: "abc" })).toEqual(EMPTY_FILTERS);
    expect(parseFilterParams({ price_max: "999999999" })).toEqual(EMPTY_FILTERS);
  });

  it("accepts zero as a price", () => {
    expect(parseFilterParams({ price_min: "0" }).priceMin).toBe(0);
  });

  it("is empty when nothing is given", () => {
    expect(parseFilterParams({})).toEqual(EMPTY_FILTERS);
  });
});

describe("activeFilterCount and hasFilters", () => {
  it("counts each choice and each price bound", () => {
    const filters = { sizes: ["M", "L"], colours: ["Red"], priceMin: 10, priceMax: 90 };
    expect(activeFilterCount(filters)).toBe(5);
    expect(hasFilters(filters)).toBe(true);
  });

  it("is zero for no filters", () => {
    expect(activeFilterCount(EMPTY_FILTERS)).toBe(0);
    expect(hasFilters(EMPTY_FILTERS)).toBe(false);
  });
});

describe("productsHrefWithFilters", () => {
  it("is plain /products with no choices", () => {
    expect(productsHrefWithFilters({}, EMPTY_FILTERS)).toBe("/products");
  });

  it("keeps search, category, sort and every filter, with the page last", () => {
    const href = productsHrefWithFilters(
      { q: "tee", category: "tops", sort: "newest", cursor: "n1" },
      { sizes: ["M", "L"], colours: ["Red"], priceMin: 50, priceMax: 200 },
    );
    expect(href).toBe(
      "/products?q=tee&category=tops&sort=newest&size=M&size=L&colour=Red&price_min=50&price_max=200&cursor=n1",
    );
  });

  it("encodes values with spaces", () => {
    expect(productsHrefWithFilters({}, { sizes: [], colours: ["Navy blue"] })).toBe(
      "/products?colour=Navy+blue",
    );
  });
});
