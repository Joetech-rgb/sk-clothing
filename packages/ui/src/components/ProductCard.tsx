import { cn } from "../cn";
import type { LinkLike } from "./SiteHeader";

export interface ProductCardProps {
  name: string;
  href: string;
  imageUrl?: string | null;
  imageAlt?: string;
  /** The server's ready-made price text, for example "GHS 12.00". */
  priceFromDisplay?: string | null;
  inStock: boolean;
  hasWholesale?: boolean;
  linkAs?: LinkLike;
  className?: string;
}

export function ProductCard({
  name,
  href,
  imageUrl,
  imageAlt = "",
  priceFromDisplay,
  inStock,
  hasWholesale = false,
  linkAs,
  className,
}: ProductCardProps) {
  const L: LinkLike = linkAs ?? "a";
  return (
    <article className={cn("flex flex-col gap-2", className)}>
      <L
        href={href}
        className="flex flex-col gap-2 rounded-card focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
      >
        <div className="aspect-square w-full overflow-hidden rounded-card bg-surface-muted">
          {imageUrl && (
            <img
              src={imageUrl}
              alt={imageAlt}
              loading="lazy"
              decoding="async"
              className="h-full w-full object-cover"
            />
          )}
        </div>
        <h3 className="text-base font-medium text-ink">{name}</h3>
      </L>
      {priceFromDisplay && (
        <p className="text-ink">
          <span className="text-sm text-ink-muted">From </span>
          <span className="font-semibold tabular-nums">{priceFromDisplay}</span>
        </p>
      )}
      {(!inStock || hasWholesale) && (
        <p className="text-sm text-ink-muted">
          {!inStock && <span>Sold out</span>}
          {!inStock && hasWholesale && <span> · </span>}
          {hasWholesale && <span>Wholesale prices</span>}
        </p>
      )}
    </article>
  );
}

export function ProductGrid({ children, className }: { children: React.ReactNode; className?: string }) {
  return <div className={cn("grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4", className)}>{children}</div>;
}
