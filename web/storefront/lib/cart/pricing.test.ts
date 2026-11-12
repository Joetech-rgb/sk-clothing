import type { components } from "@sk/api-client";
import { describe, expect, it } from "vitest";
import { parseApiError } from "../api/errors";
import type { CartLine } from "./cart";
import {
  indexPricedLines,
  lineDisplay,
  toPriceItems,
  unavailableVariantId,
} from "./pricing";

type Schemas = components["schemas"];

const money = (pesewas: number): Schemas["Money"] => ({
  pesewas,
  display: `GHS ${(pesewas / 100).toFixed(2)}`,
});

const line: CartLine = { productSlug: "cotton-tee", variantId: 7, quantity: 3 };

describe("toPriceItems", () => {
  it("sends ids and quantities only", () => {
    expect(toPriceItems([line])).toEqual([{ variant_id: 7, quantity: 3 }]);
  });

  it("is empty for an empty cart", () => {
    expect(toPriceItems([])).toEqual([]);
  });
});

describe("indexPricedLines", () => {
  it("finds each priced line by variant id", () => {
    const priced: Schemas["PricedLine"] = {
      variant_id: 7,
      quantity: 3,
      tier: "retail",
      source: "tier",
      unit_price: money(1000),
      line_total: money(3000),
      list_price: money(1000),
      tier_price: money(1000),
      discounts: [],
    };
    const index = indexPricedLines({ lines: [priced], subtotal: money(3000) });
    expect(index.get(7)?.line_total.display).toBe("GHS 30.00");
    expect(index.get(8)).toBeUndefined();
  });
});

describe("lineDisplay", () => {
  const product: Schemas["ProductDetail"] = {
    id: 1,
    name: "Cotton tee",
    slug: "cotton-tee",
    description: "",
    category: { id: 1, name: "Tops", slug: "tops" },
    images: [{ url: "https://img.example/tee.webp", alt_text: "" }],
    price_from: money(1000),
    quantity_rules: [],
    variants: [
      { id: 7, sku: "S7", size: "M", colour: "Red", available: 5, in_stock: true, tiers: [] },
    ],
  };

  it("shows the product name, the option and the first picture", () => {
    expect(lineDisplay(line, product)).toEqual({
      name: "Cotton tee",
      variant: { size: "M", colour: "Red" },
      imageUrl: "https://img.example/tee.webp",
    });
  });

  it("falls back to the slug while the product is still loading", () => {
    expect(lineDisplay(line, undefined)).toEqual({
      name: "cotton-tee",
      variant: undefined,
      imageUrl: null,
    });
  });

  it("has no option text when the variant is not in the product any more", () => {
    expect(lineDisplay({ ...line, variantId: 99 }, product).variant).toBeUndefined();
  });
});

describe("unavailableVariantId", () => {
  const envelope = (code: string, details?: unknown) =>
    parseApiError(422, { error: { code, message: "One of the items is not available.", details } });

  it("returns the variant the server says is gone", () => {
    expect(unavailableVariantId(envelope("variant_unavailable", { variant_id: 7 }))).toBe(7);
  });

  it("returns null when the server gave no variant", () => {
    expect(unavailableVariantId(envelope("variant_unavailable"))).toBeNull();
  });

  it("returns null for other errors", () => {
    expect(unavailableVariantId(envelope("insufficient_stock", { variant_id: 7 }))).toBeNull();
  });
});
