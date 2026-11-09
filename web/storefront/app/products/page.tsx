import type { Metadata } from "next";
import Link from "next/link";
import { ProductCard, ProductGrid } from "@sk/ui";
import { listProducts } from "../../lib/api/endpoints";
import { describeError } from "../../lib/api/errors";
import { serverOptions } from "../../lib/api/server";
import { toProductCard } from "../../lib/catalog/view-models";

export const metadata: Metadata = { title: "Products" };

export default async function ProductsPage({
  searchParams,
}: {
  searchParams: Promise<{ cursor?: string }>;
}) {
  const { cursor } = await searchParams;
  const result = await listProducts({ cursor }, serverOptions);

  if (!result.ok) {
    return (
      <p role="alert" className="text-danger">
        {describeError(result.error)}
      </p>
    );
  }

  const { results, next_cursor } = result.data;
  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-2xl font-semibold">Products</h1>
      {results.length === 0 ? (
        <p className="text-ink-muted">There are no products to show yet.</p>
      ) : (
        <ProductGrid>
          {results.map((item) => (
            <ProductCard key={item.id} {...toProductCard(item)} linkAs={Link} />
          ))}
        </ProductGrid>
      )}
      {next_cursor && (
        <Link
          href={`/products?cursor=${encodeURIComponent(next_cursor)}`}
          className="inline-flex min-h-11 items-center self-start rounded-control border border-line px-4 text-ink hover:bg-surface-muted"
        >
          Next page
        </Link>
      )}
    </div>
  );
}
