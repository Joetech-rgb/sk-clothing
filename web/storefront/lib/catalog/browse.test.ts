import { describe, expect, it } from "vitest";
import { parseBrowseParams, productsHref, withoutCursor } from "./browse";

describe("parseBrowseParams", () => {
  it("reads a search, category, sort and cursor", () => {
    expect(
      parseBrowseParams({ q: " red tee ", category: "tops", sort: "newest", cursor: "abc" }),
    ).toEqual({ q: "red tee", category: "tops", sort: "newest", cursor: "abc" });
  });

  it("takes the first value when a name is repeated", () => {
    expect(parseBrowseParams({ q: ["tee", "shoe"] })).toEqual({ q: "tee" });
  });

  it("leaves out blank and missing values", () => {
    expect(parseBrowseParams({ q: "   ", category: "" })).toEqual({});
    expect(parseBrowseParams({})).toEqual({});
  });

  it("drops a sort the server does not know", () => {
    expect(parseBrowseParams({ sort: "cheapest" })).toEqual({});
  });

  it.each(["a b", "../x", "tops?x=1", "a".repeat(101)])("drops the odd category %j", (category) => {
    expect(parseBrowseParams({ category })).toEqual({});
  });

  it("cuts a very long search and drops a very long cursor", () => {
    expect(parseBrowseParams({ q: "x".repeat(300) }).q).toHaveLength(200);
    expect(parseBrowseParams({ cursor: "c".repeat(65) })).toEqual({});
  });
});

describe("productsHref", () => {
  it("is plain /products with no choices", () => {
    expect(productsHref({})).toBe("/products");
  });

  it("keeps the choices in a stable order and encodes them", () => {
    expect(productsHref({ cursor: "n1", q: "red tee", sort: "price_low", category: "tops" })).toBe(
      "/products?q=red+tee&category=tops&sort=price_low&cursor=n1",
    );
  });
});

describe("withoutCursor", () => {
  it("drops only the cursor", () => {
    expect(withoutCursor({ q: "tee", category: "tops", cursor: "n1" })).toEqual({
      q: "tee",
      category: "tops",
    });
  });
});
