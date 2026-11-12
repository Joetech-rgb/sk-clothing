import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { ProductPurchase } from "../../../components/ProductPurchase";
import { getProduct } from "../../../lib/api/endpoints";
import { describeError } from "../../../lib/api/errors";
import { serverOptions } from "../../../lib/api/server";
import {
  defaultVariantId,
  tiersByVariant,
  toVariantOptions,
} from "../../../lib/catalog/view-models";

interface Props {
  params: Promise<{ slug: string }>;
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { slug } = await params;
  const result = await getProduct(slug, serverOptions);
  return { title: result.ok ? result.data.name : "Product" };
}

export default async function ProductPage({ params }: Props) {
  const { slug } = await params;
  const result = await getProduct(slug, serverOptions);

  if (!result.ok) {
    if (result.error.status === 404) notFound();
    return (
      <p role="alert" className="text-danger">
        {describeError(result.error)}
      </p>
    );
  }

  const product = result.data;
  const [first, ...rest] = product.images;

  return (
    <div className="grid gap-6 md:grid-cols-2">
      <div className="flex flex-col gap-3">
        <div className="aspect-square w-full overflow-hidden rounded-card bg-surface-muted">
          {first && (
            <img
              src={first.url}
              alt={first.alt_text}
              fetchPriority="high"
              decoding="async"
              className="h-full w-full object-cover"
            />
          )}
        </div>
        {rest.length > 0 && (
          <div className="grid grid-cols-4 gap-2">
            {rest.map((image) => (
              <div
                key={image.url}
                className="aspect-square overflow-hidden rounded-control bg-surface-muted"
              >
                <img
                  src={image.url}
                  alt={image.alt_text}
                  loading="lazy"
                  decoding="async"
                  className="h-full w-full object-cover"
                />
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="flex flex-col gap-4">
        <h1 className="text-2xl font-semibold">{product.name}</h1>
        {product.price_from && (
          <p className="text-ink">
            <span className="text-sm text-ink-muted">From </span>
            <span className="font-semibold tabular-nums">{product.price_from.display}</span>
          </p>
        )}
        {product.description && (
          <p className="whitespace-pre-line text-ink">{product.description}</p>
        )}
        <ProductPurchase
          productSlug={product.slug}
          variants={toVariantOptions(product)}
          tiersByVariant={tiersByVariant(product)}
          initialVariantId={defaultVariantId(product)}
        />
      </div>
    </div>
  );
}
