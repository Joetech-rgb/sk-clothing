/**
 * The browser-side cart. It holds only WHICH items and HOW MANY. It never holds
 * a price, a tier, a fee or a stock figure: every price shown comes from the
 * server (CLAUDE.md section 4). All functions are pure and never mutate input.
 *
 * Identifier types are provisional until the OpenAPI snapshot arrives.
 */

export interface CartLine {
  productSlug: string;
  variantId: string;
  quantity: number;
}

export type Cart = readonly CartLine[];

export const EMPTY_CART: Cart = [];

function assertWholeNumber(quantity: number, min: number): void {
  if (!Number.isInteger(quantity) || quantity < min) {
    throw new RangeError(`Quantity must be a whole number of at least ${min}`);
  }
}

/** Add a line. The same variant is merged by adding quantities. */
export function addLine(cart: Cart, line: CartLine): Cart {
  assertWholeNumber(line.quantity, 1);
  const existing = cart.find((l) => l.variantId === line.variantId);
  if (!existing) {
    return [...cart, { ...line }];
  }
  return cart.map((l) =>
    l.variantId === line.variantId
      ? { ...l, quantity: l.quantity + line.quantity }
      : l,
  );
}

/** Set a line's quantity. Zero removes it. An unknown variant leaves the cart unchanged. */
export function setQuantity(cart: Cart, variantId: string, quantity: number): Cart {
  assertWholeNumber(quantity, 0);
  if (!cart.some((l) => l.variantId === variantId)) {
    return cart;
  }
  if (quantity === 0) {
    return removeLine(cart, variantId);
  }
  return cart.map((l) => (l.variantId === variantId ? { ...l, quantity } : l));
}

export function removeLine(cart: Cart, variantId: string): Cart {
  return cart.filter((l) => l.variantId !== variantId);
}

export function clearCart(): Cart {
  return EMPTY_CART;
}

/** Number of items for a badge. A count only, not a price or a total. */
export function totalQuantity(cart: Cart): number {
  return cart.reduce((sum, l) => sum + l.quantity, 0);
}
