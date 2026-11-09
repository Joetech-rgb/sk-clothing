import type { components } from "@sk/api-client";
import type { ApiError } from "../api/errors";
import type { Cart, CartLine } from "./cart";

type Schemas = components["schemas"];

/** What the price endpoint wants: ids and quantities, never a price. */
export function toPriceItems(cart: Cart): Schemas["PriceItem"][] {
  return cart.map((line) => ({ variant_id: line.variantId, quantity: line.quantity }));
}

export function indexPricedLines(
  response: Schemas["PriceResponse"],
): Map<number, Schemas["PricedLine"]> {
  return new Map(response.lines.map((line) => [line.variant_id, line]));
}

export interface LineDisplay {
  name: string;
  variant: { size: string; colour: string } | undefined;
  imageUrl: string | null;
}

/** Name, option and picture for a cart line, from the product the server described. */
export function lineDisplay(
  line: CartLine,
  product: Schemas["ProductDetail"] | undefined,
): LineDisplay {
  const variant = product?.variants.find((v) => v.id === line.variantId);
  return {
    name: product?.name ?? line.productSlug,
    variant: variant ? { size: variant.size, colour: variant.colour } : undefined,
    imageUrl: product?.images[0]?.url ?? null,
  };
}

/** The variant id the server says is no longer available, if that is what went wrong. */
export function unavailableVariantId(error: ApiError): number | null {
  if (error.code !== "variant_unavailable") return null;
  const id = error.details?.variant_id;
  return typeof id === "number" ? id : null;
}
