"use client";

import Link from "next/link";
import { useCart } from "../lib/cart/use-cart";

/** The header's cart link, with the number of items in the browser's cart. */
export function CartLink() {
  const { count } = useCart();
  return (
    <Link
      href="/cart"
      className="inline-flex min-h-11 items-center rounded-control px-3 text-base text-ink hover:bg-surface-muted focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
    >
      {count > 0 ? `Cart (${count})` : "Cart"}
    </Link>
  );
}
