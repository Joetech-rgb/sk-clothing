import type { components } from "@sk/api-client";
import { describe, expect, it } from "vitest";
import {
  defaultVariantId,
  tiersByVariant,
  toProductCard,
  toTiers,
  toVariantOptions,
} from "./view-models";

type Schemas = components["schemas"];

const money = (pesewas: number): Schemas["Money"] => ({
  pesewas,
  display: `GHS ${(pesewas / 100).toFixed(2)}`,
});

const category: Schemas["CategoryRef"] = { id: 1, name: "Tops", slug: "tops" };

function variant(id: number, inStock: boolean, tiers: Schemas["Tier"][] = []): Schemas["Variant"] {
  return { id, sku: `SKU-${id}`, size: "M", colour: "Red", available: inStock ? 5 : 0, in_stock: inStock, tiers };
}

function detail(variants: Schemas["Variant"][]): Schemas["ProductDetail"] {
  return {
    id: 1,
    name: "Cotton tee",
    slug: "cotton-tee",
    description: "",
    category,
    images: [],
    price_from: money(1000),
    quantity_rules: [],
    variants,
  };
}

describe("toProductCard", () => {
  const item: Schemas["ProductListItem"] = {
    id: 1,
    name: "Cotton tee",
    slug: "cotton tee",
    category,
    image: { url: "https://img.example/tee.webp", alt_text: "A red tee" },
    price_from: money(1050),
    in_stock: true,
    has_wholesale: true,
  };

  it("maps the product for the card and uses the server's price text", () => {
    expect(toProductCard(item)).toEqual({
      name: "Cotton tee",
      href: "/products/cotton%20tee",
      imageUrl: "https://img.example/tee.webp",
      imageAlt: "A red tee",
      priceFromDisplay: "GHS 10.50",
      inStock: true,
      hasWholesale: true,
    });
  });

  it("copes with no image and no price", () => {
    const card = toProductCard({ ...item, image: null, price_from: null });
    expect(card.imageUrl).toBeNull();
    expect(card.imageAlt).toBe("");
    expect(card.priceFromDisplay).toBeNull();
  });
});

describe("toTiers", () => {
  it("shows only the tiers the server sent, lowest quantity first", () => {
    const v = variant(1, true, [
      { tier: "wholesale", min_quantity: 10, price: money(800) },
      { tier: "retail", min_quantity: 1, price: money(1000) },
    ]);
    expect(toTiers(v)).toEqual([
      { tier: "retail", minQuantity: 1, priceDisplay: "GHS 10.00" },
      { tier: "wholesale", minQuantity: 10, priceDisplay: "GHS 8.00" },
    ]);
  });

  it("does not change the order of the original list", () => {
    const tiers = [
      { tier: "wholesale", min_quantity: 10, price: money(800) },
      { tier: "retail", min_quantity: 1, price: money(1000) },
    ];
    toTiers(variant(1, true, tiers));
    expect(tiers[0]?.tier).toBe("wholesale");
  });

  it("is empty when no tier is filled in", () => {
    expect(toTiers(variant(1, true))).toEqual([]);
  });
});

describe("toVariantOptions and tiersByVariant", () => {
  const product = detail([
    variant(1, true, [{ tier: "retail", min_quantity: 1, price: money(1000) }]),
    variant(2, false),
  ]);

  it("maps stock to inStock", () => {
    expect(toVariantOptions(product)).toEqual([
      { id: 1, size: "M", colour: "Red", inStock: true },
      { id: 2, size: "M", colour: "Red", inStock: false },
    ]);
  });

  it("keys the tiers by variant id", () => {
    const byVariant = tiersByVariant(product);
    expect(byVariant[1]).toHaveLength(1);
    expect(byVariant[2]).toEqual([]);
  });
});

describe("defaultVariantId", () => {
  it("preselects when there is exactly one option in stock", () => {
    expect(defaultVariantId(detail([variant(1, false), variant(2, true)]))).toBe(2);
  });

  it("leaves the choice to the customer when there are several", () => {
    expect(defaultVariantId(detail([variant(1, true), variant(2, true)]))).toBeNull();
  });

  it("selects nothing when everything is sold out", () => {
    expect(defaultVariantId(detail([variant(1, false)]))).toBeNull();
  });
});
