import type { components } from "@sk/api-client";
import type { PriceTier, ProductCardProps, VariantOption } from "@sk/ui";

type Schemas = components["schemas"];

/** Turns an API product into the props the product card shows. Display only. */
export function toProductCard(item: Schemas["ProductListItem"]): Omit<ProductCardProps, "linkAs"> {
  return {
    name: item.name,
    href: `/products/${encodeURIComponent(item.slug)}`,
    imageUrl: item.image?.url ?? null,
    imageAlt: item.image?.alt_text ?? "",
    priceFromDisplay: item.price_from?.display ?? null,
    inStock: item.in_stock,
    hasWholesale: item.has_wholesale,
  };
}

export function toVariantOptions(product: Schemas["ProductDetail"]): VariantOption[] {
  return product.variants.map((v) => ({
    id: v.id,
    size: v.size,
    colour: v.colour,
    inStock: v.in_stock,
  }));
}

/** The tiers the server filled in for one variant, lowest quantity first. No maths here. */
export function toTiers(variant: Schemas["Variant"]): PriceTier[] {
  return [...variant.tiers]
    .sort((a, b) => a.min_quantity - b.min_quantity)
    .map((t) => ({
      tier: t.tier,
      minQuantity: t.min_quantity,
      priceDisplay: t.price.display,
    }));
}

export function tiersByVariant(product: Schemas["ProductDetail"]): Record<number, PriceTier[]> {
  const result: Record<number, PriceTier[]> = {};
  for (const variant of product.variants) {
    result[variant.id] = toTiers(variant);
  }
  return result;
}

/** Only preselects when there is exactly one option to pick; otherwise the customer chooses. */
export function defaultVariantId(product: Schemas["ProductDetail"]): number | null {
  const available = product.variants.filter((v) => v.in_stock);
  const only = available[0];
  return available.length === 1 && only ? only.id : null;
}
