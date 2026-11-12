"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Button, PriceTierList, QuantityInput, VariantPicker } from "@sk/ui";
import type { PriceTier, VariantOption } from "@sk/ui";
import { priceCart } from "../lib/api/endpoints";
import { describeError } from "../lib/api/errors";
import { useCart } from "../lib/cart/use-cart";

export interface ProductPurchaseProps {
  productSlug: string;
  variants: VariantOption[];
  tiersByVariant: Record<number, PriceTier[]>;
  initialVariantId: number | null;
}

interface PriceText {
  unit: string;
  total: string;
}

/**
 * Choose an option and a quantity, see the server's price for exactly that, then add it to
 * the cart or buy now. Every price shown here comes from the server; this line is priced on its
 * own, and the cart page prices all lines together.
 */
export function ProductPurchase({
  productSlug,
  variants,
  tiersByVariant,
  initialVariantId,
}: ProductPurchaseProps) {
  const router = useRouter();
  const { add } = useCart();
  const [variantId, setVariantId] = useState<number | null>(initialVariantId);
  const [quantity, setQuantity] = useState(1);
  const [price, setPrice] = useState<PriceText | null>(null);
  const [priceError, setPriceError] = useState<string | null>(null);
  const [added, setAdded] = useState(false);

  useEffect(() => {
    if (variantId === null) {
      setPrice(null);
      setPriceError(null);
      return;
    }
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      const result = await priceCart([{ variant_id: variantId, quantity }], {
        signal: controller.signal,
      });
      if (controller.signal.aborted) return;
      if (result.ok) {
        const line = result.data.lines[0];
        setPrice(line ? { unit: line.unit_price.display, total: line.line_total.display } : null);
        setPriceError(null);
      } else {
        setPrice(null);
        setPriceError(describeError(result.error));
      }
    }, 300);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [variantId, quantity]);

  function addToCart(): boolean {
    if (variantId === null) return false;
    add({ productSlug, variantId, quantity });
    return true;
  }

  const tiers = variantId === null ? [] : (tiersByVariant[variantId] ?? []);

  return (
    <div className="flex flex-col gap-4">
      <VariantPicker
        variants={variants}
        selectedId={variantId}
        onSelect={(id) => {
          setVariantId(id);
          setAdded(false);
        }}
      />

      {tiers.length > 0 && <PriceTierList tiers={tiers} />}

      <QuantityInput
        value={quantity}
        onChange={(next) => {
          setQuantity(next);
          setAdded(false);
        }}
      />

      <div aria-live="polite" className="min-h-6 text-ink">
        {variantId === null && <p className="text-ink-muted">Choose an option to see the price.</p>}
        {price && (
          <p>
            <span className="tabular-nums">{price.unit}</span>
            <span className="text-ink-muted"> each, total </span>
            <span className="font-semibold tabular-nums">{price.total}</span>
          </p>
        )}
        {priceError && (
          <p role="alert" className="text-danger">
            {priceError}
          </p>
        )}
      </div>

      <div className="flex flex-col gap-2 sm:flex-row">
        <Button
          variant="secondary"
          fullWidth
          disabled={variantId === null}
          onClick={() => setAdded(addToCart())}
        >
          Add to cart
        </Button>
        <Button
          fullWidth
          disabled={variantId === null}
          onClick={() => {
            if (addToCart()) router.push("/checkout");
          }}
        >
          Buy now
        </Button>
      </div>
      {added && (
        <p role="status" className="text-sm text-ink-muted">
          Added to your cart.
        </p>
      )}
    </div>
  );
}
