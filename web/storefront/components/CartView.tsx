"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { Button, CartLineRow, CartSummary, variantLabel } from "@sk/ui";
import type { components } from "@sk/api-client";
import { getProduct, priceCart } from "../lib/api/endpoints";
import { describeError } from "../lib/api/errors";
import { useCart } from "../lib/cart/use-cart";
import {
  indexPricedLines,
  lineDisplay,
  toPriceItems,
  unavailableVariantId,
} from "../lib/cart/pricing";

type Schemas = components["schemas"];

type Pricing =
  | { state: "idle" }
  | { state: "loading" }
  | { state: "ready"; subtotal: string; lines: Map<number, Schemas["PricedLine"]> }
  | { state: "error"; message: string; unavailableId: number | null };

const linkButton =
  "inline-flex min-h-11 items-center justify-center rounded-control px-4 text-base font-medium";

/**
 * Shows the cart. The browser keeps only which items and how many; every price shown here
 * comes from the server's price call, for all lines together (so quantity rules apply).
 */
export function CartView() {
  const { cart, setQuantity, remove } = useCart();
  const [mounted, setMounted] = useState(false);
  const [products, setProducts] = useState<Record<string, Schemas["ProductDetail"]>>({});
  const [pricing, setPricing] = useState<Pricing>({ state: "idle" });
  const loaded = useRef(new Set<string>());

  useEffect(() => {
    setMounted(true);
  }, []);

  const slugKey = useMemo(
    () => [...new Set(cart.map((line) => line.productSlug))].sort().join("|"),
    [cart],
  );

  // Names and pictures: one call per product, once.
  useEffect(() => {
    const toLoad = slugKey === "" ? [] : slugKey.split("|").filter((s) => !loaded.current.has(s));
    toLoad.forEach((slug) => loaded.current.add(slug));
    if (toLoad.length === 0) return;
    void Promise.all(
      toLoad.map(async (slug) => {
        const result = await getProduct(slug);
        return result.ok ? result.data : null;
      }),
    ).then((found) => {
      setProducts((previous) => {
        const next = { ...previous };
        for (const product of found) {
          if (product) next[product.slug] = product;
        }
        return next;
      });
    });
  }, [slugKey]);

  // Prices: whenever the cart changes, ask the server again.
  useEffect(() => {
    if (cart.length === 0) {
      setPricing({ state: "idle" });
      return;
    }
    setPricing({ state: "loading" });
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      const result = await priceCart(toPriceItems(cart), { signal: controller.signal });
      if (controller.signal.aborted) return;
      if (result.ok) {
        setPricing({
          state: "ready",
          subtotal: result.data.subtotal.display,
          lines: indexPricedLines(result.data),
        });
      } else {
        setPricing({
          state: "error",
          message: describeError(result.error),
          unavailableId: unavailableVariantId(result.error),
        });
      }
    }, 300);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [cart]);

  if (!mounted) {
    return <p className="text-ink-muted">Loading your cart.</p>;
  }

  if (cart.length === 0) {
    return (
      <div className="flex flex-col gap-3">
        <h1 className="text-2xl font-semibold">Your cart</h1>
        <p className="text-ink-muted">Your cart is empty.</p>
        <Link
          href="/products"
          className={`${linkButton} self-start border border-line text-ink hover:bg-surface-muted`}
        >
          Browse products
        </Link>
      </div>
    );
  }

  const ready = pricing.state === "ready";

  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-2xl font-semibold">Your cart</h1>

      {pricing.state === "error" && (
        <div role="alert" className="flex flex-col gap-2 text-danger">
          <p>{pricing.message}</p>
          {pricing.unavailableId !== null && (
            <Button
              variant="secondary"
              className="self-start"
              onClick={() => remove(pricing.unavailableId as number)}
            >
              Remove that item from my cart
            </Button>
          )}
        </div>
      )}

      <ul>
        {cart.map((line) => {
          const display = lineDisplay(line, products[line.productSlug]);
          const priced = pricing.state === "ready" ? pricing.lines.get(line.variantId) : undefined;
          return (
            <CartLineRow
              key={line.variantId}
              name={display.name}
              variantLabel={display.variant ? variantLabel(display.variant) : undefined}
              imageUrl={display.imageUrl}
              quantity={line.quantity}
              unitPriceDisplay={priced?.unit_price.display}
              lineTotalDisplay={priced?.line_total.display}
              onQuantityChange={(quantity) => setQuantity(line.variantId, quantity)}
              onRemove={() => remove(line.variantId)}
            />
          );
        })}
      </ul>

      <CartSummary
        subtotalDisplay={pricing.state === "ready" ? pricing.subtotal : undefined}
        note="Delivery is added at checkout."
        action={
          ready ? (
            <Link
              href="/checkout"
              className={`${linkButton} w-full bg-accent text-on-accent hover:bg-accent-hover`}
            >
              Checkout
            </Link>
          ) : (
            <Button fullWidth disabled>
              Checkout
            </Button>
          )
        }
      />
    </div>
  );
}
